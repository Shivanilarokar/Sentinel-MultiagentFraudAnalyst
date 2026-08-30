"""The supervisor: routes, and nothing else.

    Layer 3   supervisor          decides who to ask, and in what order
    Layer 2   behaviour, context, natural language in, natural language out
              network, disposition
    Layer 1   SQLite-backed tools exact arguments, real rows

The one architectural move that creates this shape is `@tool` wrapping an
agent's `.invoke()`. Everything else is prompt and plumbing.

This module imports no repository and no database handle. Its four tools are
the four specialist wrappers, and there is nothing else it could call. That is
"the supervisor has no database access", expressed as an import boundary rather
than as a promise.

One placement here is load-bearing and easy to get backwards:

    the HITL middleware goes on the SUBAGENT   - see disposition.py, that is
                                                 where the dangerous tools live
    the checkpointer goes on the SUPERVISOR    - this is the run that has to be
                                                 frozen and thawed

Give every subagent its own checkpointer and you get nested persistence you did
not want. Give the supervisor none and the interrupt has nowhere to live.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.messages import ToolMessage
from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from langchain_core.rate_limiters import InMemoryRateLimiter

from sentinel.agents import behaviour, context, disposition, network
from sentinel.agents._boundary import consult
from sentinel.agents.state import SupervisorState
from sentinel.config import (
    MODEL_MAX_RETRIES,
    REQUESTS_PER_SECOND,
    SPECIALIST_MODEL,
    SUPERVISOR_MODEL,
    date_context,
    require_openai_key,
)

PROMPT = f"""
You are the Supervisor on Sentinel Bank's fraud operations desk.

276 accounts were flagged over the weekend and roughly two thirds of them did
nothing wrong. Your job is to work out which is which, one account at a time,
and to produce a verdict somebody could defend in a review.

**You have no database access.** You cannot read a transaction, a case note or
a device record. You have four specialists and you delegate to them:

  - `consult_behaviour_analyst`    - is this spending normal for this customer?
  - `consult_context_analyst`      - did anyone already explain it?
  - `consult_network_analyst`      - is this account acting alone?
  - `consult_disposition_officer`  - write and record the decision.

## Order matters, and it is enforced

Call them in this order: **behaviour, then context, then network, then
disposition.** You cannot dispose of a case before you have read the context;
the disposition tool will refuse if you try, because a verdict written before
anyone has looked for an explanation is exactly the failure this desk exists to
avoid.

Behaviour and context decide most cases. Network is worth asking on every case
because "isolated" is itself useful, and it is cheap.

## Rules

- **Never state a detail you were not told.** If it did not come back in a
  specialist's message, it does not exist. Do not infer an amount, a date, a
  merchant, an identifier or a customer statement. Never write a placeholder id.
- **Do not re-argue a specialist's domain.** If Behaviour says the device was
  six hours old, that is the fact. Your job is to weigh their findings against
  each other, not to second-guess them.
- **When behaviour and context conflict, that is the case, not a problem.** The
  numbers screaming fraud while a colleague's note explains the whole thing is
  the most common shape in this queue. Say both sides plainly.
- Pass a complete, self-contained instruction to each specialist. They cannot
  see this conversation - they see only the string you send and the account id.
- When you brief the Disposition Officer, hand over the findings **in full**,
  including verbatim quotes and their note ids. It has no database access and
  can only cite what you give it.

## Your answer to the analyst

Report the verdict, the confidence, and the evidence on both sides - what made
this look like fraud, and what argued against it. If the case is unresolvable,
say what is missing. If an action is waiting on human approval, say so plainly
and do not describe it as done.

{date_context()}
""".strip()


def build_sentinel(
    *,
    human_in_the_loop: bool = True,
    checkpointer: object | None = None,
    specialist_model: str | None = None,
    supervisor_model: str | None = None,
):
    """Assemble the full system and return `(supervisor, parts)`."""
    require_openai_key()

    # One shared limiter across every agent in the process. A sweep runs six
    # accounts at a time, each fanning out to four specialists, so without this
    # the burst rate is set by whatever the thread pool happens to do. Sharing
    # one limiter makes the request rate a property of configuration rather
    # than of scheduling luck.
    limiter = (
        InMemoryRateLimiter(
            requests_per_second=REQUESTS_PER_SECOND,
            check_every_n_seconds=0.05,
            max_bucket_size=int(max(REQUESTS_PER_SECOND, 1)),
        )
        if REQUESTS_PER_SECOND > 0
        else None
    )
    model_kwargs = {"max_retries": MODEL_MAX_RETRIES, "rate_limiter": limiter}

    specialist_llm = init_chat_model(specialist_model or SPECIALIST_MODEL, **model_kwargs)
    supervisor_llm = init_chat_model(supervisor_model or SUPERVISOR_MODEL, **model_kwargs)

    # ---- Layer 2: the four specialists --------------------------------
    behaviour_agent = behaviour.build(specialist_llm)
    context_agent = context.build(specialist_llm)
    network_agent = network.build(specialist_llm)
    disposition_agent = disposition.build(supervisor_llm, human_in_the_loop=human_in_the_loop)

    # ---- Layer 3: wrap each specialist as exactly one tool ------------
    @tool
    def consult_behaviour_analyst(
        account_id: str,
        question: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Ask whether an account's spending is normal for that customer.

        Use for: velocity, amounts against the customer's own baseline, device
        age, geography, time of day, high-risk merchant categories, credit
        limit utilisation. The analyst reads transaction history only, so do
        not ask it about case notes or other accounts.

        Args:
            account_id: The flagged account, e.g. 'A00985'.
            question: A complete, self-contained instruction. The analyst
                cannot see this conversation, so say what you need decided.
        """
        return consult(behaviour_agent, behaviour.NAME, account_id, question, tool_call_id)

    @tool
    def consult_context_analyst(
        account_id: str,
        question: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Ask whether anyone has already explained an account's activity.

        Use for: case notes, disputes, prior investigations, customer segment
        and KYC level. This specialist decides roughly a third of this queue,
        so ask it on every case, including ones where the numbers look
        conclusive. Ask it to quote what it finds verbatim.

        Args:
            account_id: The flagged account.
            question: A complete, self-contained instruction. Include what the
                behaviour analyst found that needs explaining, so it knows
                which records would count as an explanation.
        """
        return consult(context_agent, context.NAME, account_id, question, tool_call_id)

    @tool
    def consult_network_analyst(
        account_id: str,
        question: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Ask whether an account is linked to others by devices or merchants.

        Use for: shared devices, the history of the accounts sharing them, and
        high-risk merchant overlap against the fraud base rate. A reply of
        'isolated' is useful, not a failure.

        Args:
            account_id: The flagged account.
            question: A complete, self-contained instruction.
        """
        return consult(network_agent, network.NAME, account_id, question, tool_call_id)

    @tool
    def consult_disposition_officer(
        account_id: str,
        brief: str,
        runtime: ToolRuntime,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Hand over the findings and have the decision written and recorded.

        Call this last, once you have the behaviour and context findings. The
        officer has no database access, so the brief must contain everything it
        needs - including verbatim quotes with their note ids.

        Args:
            account_id: The account being disposed of.
            brief: The full findings from every specialist you consulted,
                quoted rather than summarised away. State plainly where they
                agree and where they conflict.
        """
        # Ordering as a rule, not a request. The prompt asks for context before
        # disposition; this is what happens when it does not.
        consulted = runtime.state.get("specialists_consulted") or []
        if context.NAME not in consulted:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                "BLOCKED: you have not consulted the context analyst on "
                                f"{account_id}. A verdict written before anyone has looked "
                                "for an explanation is the exact failure this desk exists "
                                "to prevent. Call consult_context_analyst first, then "
                                "come back."
                            ),
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ]
                }
            )
        return consult(disposition_agent, disposition.NAME, account_id, brief, tool_call_id)

    subagent_tools = [
        consult_behaviour_analyst,
        consult_context_analyst,
        consult_network_analyst,
        consult_disposition_officer,
    ]

    # ---- Layer 3: the supervisor --------------------------------------
    # Exactly four tools, and not one of them touches the database.
    supervisor = create_agent(
        supervisor_llm,
        tools=subagent_tools,
        system_prompt=PROMPT,
        state_schema=SupervisorState,
        checkpointer=checkpointer or InMemorySaver(),
    )

    parts = {
        "specialist_model": specialist_model or SPECIALIST_MODEL,
        "supervisor_model": supervisor_model or SUPERVISOR_MODEL,
        "behaviour_agent": behaviour_agent,
        "context_agent": context_agent,
        "network_agent": network_agent,
        "disposition_agent": disposition_agent,
        "tools": subagent_tools,
        "human_in_the_loop": human_in_the_loop,
    }
    return supervisor, parts
