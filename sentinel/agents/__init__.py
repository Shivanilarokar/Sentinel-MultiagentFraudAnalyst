"""The agent package: four specialists and one supervisor.

    behaviour.py    reads 108,249 transactions   is this normal for this customer?
    context.py      reads 260 notes, 86 disputes did the customer already explain it?
                    and 200 prior cases
    network.py      reads devices and merchants  is this account acting alone?
                    across accounts
    disposition.py  writes, does not read        what do we do, and who approves it?
    supervisor.py   routes only, no DB access    who to ask, and in what order

Each specialist module owns its own system prompt, its own tool list and its
own middleware, so "four agents, each with its own prompt and only the tools
for its own domain" is visible in the file layout rather than buried in a
factory.

This file holds the one function they all pass through: `consult`. It invokes a
specialist on a fresh message list and returns exactly one thing - that agent's
final message. Everything else the specialist did, a dozen tool calls each
returning hundreds of database rows, lives and dies inside `result`.

That single line is what makes four isolated specialists cheaper than one agent
holding every tool, and the usage ledger measures the gap so the claim can be
checked rather than asserted.
"""

from __future__ import annotations

from langchain.messages import ToolMessage
from langgraph.types import Command

from sentinel.db import actions, record_usage
from sentinel.policies import current_case

FINAL_MESSAGE_CONTRACT = """
## Your final message is the entire interface

The supervisor cannot see your tool calls, your intermediate reasoning, or any
row you fetched. It sees one thing: your last message. Anything you discovered
and did not write down is lost, and the case will be decided without it.

So write findings, not a description of work. "I examined the transaction
history and the case notes" tells the supervisor nothing. State what you found,
with the identifiers, and quote any human-written text exactly as it appears.

Cite as you go, inline, using the real ids exactly as they appear in the tool
results: note_id (N00080), txn_id (T0107306), dispute_id (DP0012), alert_id
(AL0170), device_id (DX01444), case_id (PC0044).

**Never write a placeholder.** If you did not read an identifier in a tool
result, do not write one - not `ALxxxx1`, not `T000000`, not a rule id where an
alert id belongs. An invented identifier is worse than a missing one, because
it looks like evidence and is not. Omit the citation instead.

Be concise. Six to twelve lines is usually right. Length is not evidence.
"""


def message_text(message) -> str:
    """The text of a message, without tripping the deprecation on `.text()`.

    langchain-core returns a `TextAccessor` from `.text`, which is both a
    string and callable for backward compatibility. Calling it warns; `str()`
    on it does not.
    """
    accessor = getattr(message, "text", None)
    if accessor is not None:
        return str(accessor)
    return str(getattr(message, "content", "") or "")


def final_message_text(result: dict, default: str = "") -> str:
    """The last message of an agent result: the only thing that crosses a boundary."""
    messages = result.get("messages", [])
    return message_text(messages[-1]).strip() if messages else default


def final_text(result: dict) -> str:
    """The one thing that crosses the boundary."""
    return final_message_text(result, default="(the specialist returned nothing)")


def _measure(result: dict) -> dict[str, int]:
    """Tokens the provider counted, and characters either side of the boundary.

    An agent run makes several model calls - one per tool-use turn - and each
    carries its own usage. Taking only the final message, as is tempting,
    undercounts a multi-step specialist by most of its actual cost.
    """
    messages = result.get("messages", [])
    input_tokens = output_tokens = 0
    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if usage:
            input_tokens += usage.get("input_tokens", 0) or 0
            output_tokens += usage.get("output_tokens", 0) or 0
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        # Everything produced inside, against the one message that escapes.
        "chars_inside": sum(len(message_text(m)) for m in messages),
        "chars_crossed": len(message_text(messages[-1])) if messages else 0,
    }


def consult(agent, name: str, account_id: str, question: str, tool_call_id: str) -> Command:
    """Run a specialist in isolation and hand back only its final message.

    The structured record of the finding rides back on the `findings` state key
    rather than in the message list, so the supervisor's model never reads it,
    but the report writer and the evidence audit can work from it later.
    """
    token = current_case.set((account_id, name))
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": f"Account {account_id}.\n\n{question}"}]}
        )
    finally:
        current_case.reset(token)

    finding = final_text(result)
    measured = _measure(result)
    record_usage(account_id, name, **measured)

    # Persist the finding so CASES.md can reconstruct the trail afterwards. It
    # lives in the run store, not in the supervisor's message list, so the
    # supervisor's model still never sees anything but the rendered text.
    try:
        with actions.cursor() as cur:
            cur.execute(
                "INSERT INTO findings (account_id, specialist, question, finding, "
                "chars_inside, chars_crossed) VALUES (?, ?, ?, ?, ?, ?)",
                (account_id, name, question, finding,
                 measured["chars_inside"], measured["chars_crossed"]),
            )
    except Exception:
        pass

    return Command(
        update={
            "messages": [ToolMessage(content=finding, tool_call_id=tool_call_id)],
            "account_id": account_id,
            "specialists_consulted": [name],
            "findings": [{
                "specialist": name,
                "finding": finding,
                "chars_inside": measured["chars_inside"],
                "chars_crossed": measured["chars_crossed"],
            }],
        }
    )


# Imported last, on purpose. `supervisor` imports `consult` from this package,
# so the name has to exist before that import runs.
from sentinel.agents.supervisor import (  # noqa: E402
    SPECIALISTS,
    SupervisorState,
    build_sentinel,
)

__all__ = [
    "build_sentinel",
    "SupervisorState",
    "SPECIALISTS",
    "consult",
    "final_text",
    "final_message_text",
    "message_text",
    "FINAL_MESSAGE_CONTRACT",
]
