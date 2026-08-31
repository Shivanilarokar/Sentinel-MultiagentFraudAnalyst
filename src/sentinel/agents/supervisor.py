"""The supervisor, and the boundary it cannot see past.

Four tools, and not one of them touches the database. It decides who to ask and
in what order, and assembles a verdict from what comes back.

The whole architecture is these two lines, inside `_consult`:

    result  = specialist.invoke({"messages": [{"role": "user", "content": ...}]})
    finding = result["messages"][-1].text      # everything else dies here

`result` holds the specialist's entire conversation — its tool calls, the
hundreds of database rows they returned, its reasoning. One line crosses back,
and the rest is garbage-collected when `.invoke()` returns.

Three consequences fall straight out of that:

  * the specialist gets a fresh message list every call, so its context is
    isolated and it is stateless between accounts
  * the supervisor never sees a specialist's intermediate output, so its own
    context stays small no matter how much the specialist read
  * it is an ordinary tool call, so the runtime parallelises independent ones
    for free
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from sentinel import db
from sentinel.config import date_context
from sentinel.middleware import SupervisorState

PROMPT = (
    "You are the duty analyst on Sentinel Bank's fraud desk.\n\n"
    "276 accounts were flagged over the weekend and roughly two thirds of them "
    "did nothing wrong. You do not query the database yourself — you have four "
    "specialists and you delegate:\n\n"
    "  `consult_behaviour_analyst`     is this spending normal for this customer?\n"
    "  `consult_context_specialist`    did the customer already explain it?\n"
    "  `consult_network_analyst`       is this account acting alone?\n"
    "  `consult_disposition_officer`   decide, record, and act\n\n"
    "ORDER MATTERS AND IS ENFORCED. You may consult behaviour, context and "
    "network in any order, and in the same turn if you like — they are "
    "independent and will run in parallel. But you CANNOT dispose of a case "
    "before the context specialist has reported. That call will be refused. "
    "The numbers alone reach 78% on this queue; the file is what gets you past "
    "it.\n\n"
    "Give each specialist a complete, self-contained instruction. They cannot "
    "see this conversation — they see only the string you send, plus the "
    "account id.\n\n"
    "When you brief the disposition officer, keep it SHORT — two or three "
    "sentences saying what you believe the verdict is and which single piece of "
    "evidence decides it. Every specialist's finding is attached to your brief "
    "automatically, verbatim, so do NOT repeat them: copying them back costs "
    "tokens and replaces their exact words with your paraphrase.\n\n"
    "NEVER state a fact a specialist did not report. If you did not read it in "
    "a tool result, you do not know it.\n\n"
    "Expect the specialists to disagree. Behaviour saying 'four transactions, "
    "216,000, device six hours old' and context saying 'note filed before the "
    "incident, phone upgrade verified by video KYC' is not a contradiction — it "
    "is the normal shape of a false positive. Weigh them, and say which one "
    "decided it.\n\n"
    "Finish with the verdict, the confidence, and the evidence for BOTH sides, "
    "so the next person to read the case can disagree with you on the facts.\n\n"
    + date_context()
)


def _record_usage(result: dict, agent: str, account_id: str) -> None:
    """Log what this invocation cost and how many calls it took.

    `model_calls` matters as much as the token count. `input_tokens` is a sum
    over calls that each re-sent the whole message list, so without the call
    count there is no way to recover how much content the context actually held
    — and therefore no way to model what one flat agent would have cost.
    """
    tokens_in = tokens_out = calls = tool_calls = 0
    for message in result.get("messages", []):
        usage = getattr(message, "usage_metadata", None)
        if usage:
            tokens_in += usage.get("input_tokens", 0)
            tokens_out += usage.get("output_tokens", 0)
            calls += 1
        tool_calls += len(getattr(message, "tool_calls", None) or [])

    if tokens_in or tokens_out:
        db.write(
            "INSERT INTO token_ledger (account_id, agent, input_tokens, "
            "output_tokens, model_calls, tool_calls, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (account_id, agent, tokens_in, tokens_out, calls, tool_calls, db.now()),
        )


def _record_finding(account_id: str, specialist: str, finding: str) -> None:
    """Keep the full finding on disk, even though the model's view is trimmed."""
    db.write(
        "INSERT INTO findings (account_id, specialist, finding, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (account_id, specialist, finding, db.now()),
    )


def _consult(agent, name: str, question: str, runtime: ToolRuntime,
             extra: str = "") -> Command:
    """Invoke a specialist and return only its last message.

    This is the isolation boundary. Everything the specialist read lives in
    `result` and dies with this function.

    The finding also rides back on the `findings` state key rather than only in
    the message list, so the report writer can reproduce it verbatim while the
    supervisor's model never re-reads it on later turns.
    """
    account_id = runtime.state.get("account_id", "")
    prompt = f"Account under investigation: {account_id}\n\n{question}"
    if extra:
        prompt += f"\n\n{extra}"

    result = agent.invoke({
        "messages": [{"role": "user", "content": prompt}],
        "account_id": account_id,
        "unattended": runtime.state.get("unattended", False),
    })
    finding = result["messages"][-1].text

    _record_usage(result, name, account_id)
    _record_finding(account_id, name, finding)

    return Command(update={
        "messages": [ToolMessage(finding, tool_call_id=runtime.tool_call_id)],
        "specialists_consulted": [name],
        "findings": {name: finding},
    })


def build(model, specialists: dict, *, checkpointer=None):
    """Wrap each specialist as one tool, and hand them to the supervisor.

    Args:
        model: The chat model for the supervisor itself.
        specialists: `{"behaviour": agent, "context": agent, ...}`.
        checkpointer: Where a paused run lives. It belongs here, on the
            supervisor, because this is the run that freezes when the approval
            gate fires three layers down.

    Returns:
        `(supervisor, tools)`.
    """

    @tool
    def consult_behaviour_analyst(question: str, runtime: ToolRuntime) -> Command:
        """Ask whether the flagged activity is normal for this customer.

        Reads transactions, devices, geography, merchant risk and limit use, and
        compares the incident against this customer's own 90-day baseline.

        Args:
            question: What you want established, in full. For example: 'What
                fired, and how does the flagged activity compare with this
                customer's normal spending, devices and geography?'
        """
        return _consult(specialists["behaviour"], "behaviour", question, runtime)

    @tool
    def consult_context_specialist(question: str, runtime: ToolRuntime) -> Command:
        """Ask whether anyone on file already explained this activity.

        Reads case notes, disputes and prior investigations, and judges each on
        timing, subject and specificity. Consult this BEFORE disposing of any
        case — it is the difference between 78% and 92% on this queue.

        Args:
            question: What you need explained. Include what the behaviour analyst
                found, so the specialist knows which activity a note would have
                to cover.
        """
        return _consult(specialists["context"], "context", question, runtime)

    @tool
    def consult_network_analyst(question: str, runtime: ToolRuntime) -> Command:
        """Ask whether this account is linked to others.

        Reads shared devices, the peers on them, and merchant overlap with other
        flagged accounts.

        Args:
            question: What you want checked, e.g. 'Is this account linked to
                other flagged accounts by device or merchant?'
        """
        return _consult(specialists["network"], "network", question, runtime)

    @tool
    def consult_disposition_officer(instruction: str, runtime: ToolRuntime) -> Command:
        """Hand the case over to be decided, recorded and acted on.

        REFUSED until the context specialist has reported. The disposition
        officer holds no database tools, so every finding is attached to your
        instruction automatically and verbatim.

        Args:
            instruction: A SHORT brief, two or three sentences: what you believe
                the verdict is and which single piece of evidence decides it. Do
                not restate the specialists' findings — they are attached to this
                call already, and your paraphrase would replace their exact words
                with a lossy copy.
        """
        if "context" not in (runtime.state.get("specialists_consulted") or []):
            return Command(update={"messages": [ToolMessage(
                content=(
                    "REFUSED: you cannot dispose of a case before reading the "
                    "file. Call consult_context_specialist first. The numbers "
                    "alone reach 78% on this queue and this account may well be "
                    "one of the two thirds that did nothing wrong."
                ),
                tool_call_id=runtime.tool_call_id,
                status="error",
            )]})

        findings = runtime.state.get("findings") or {}
        gathered = "\n\n".join(
            f"### Finding from the {name} specialist\n{text}"
            for name, text in findings.items()
        )
        return _consult(
            specialists["disposition"], "disposition", instruction, runtime,
            extra=f"## The specialists reported:\n\n{gathered}",
        )

    tools = [
        consult_behaviour_analyst,
        consult_context_specialist,
        consult_network_analyst,
        consult_disposition_officer,
    ]

    supervisor = create_agent(
        model,
        tools=tools,
        system_prompt=PROMPT,
        state_schema=SupervisorState,
        checkpointer=checkpointer,
    )
    return supervisor, tools
