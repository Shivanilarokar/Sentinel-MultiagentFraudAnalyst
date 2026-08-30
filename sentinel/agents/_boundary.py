"""The isolation boundary, and the contract every specialist prompt ends with.

`consult` is the single most important function in this system. It invokes a
specialist on a fresh message list and returns exactly one thing: that agent's
final message. Everything else the specialist did - a dozen tool calls, each
returning hundreds of database rows - lives and dies inside `result`.

That one line is what makes four isolated specialists cheaper than one agent
holding all the tools, and `usage.record` measures the gap so the claim can be
checked rather than asserted.
"""

from __future__ import annotations

from langchain.messages import ToolMessage
from langgraph.types import Command

from sentinel import usage
from sentinel.db import actions
from sentinel.messages import final_message_text
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




def final_text(result: dict) -> str:
    """The one thing that crosses the boundary."""
    return final_message_text(result, default="(the specialist returned nothing)")


def consult(agent, name: str, account_id: str, question: str, tool_call_id: str) -> Command:
    """Run a specialist in isolation and hand back only its final message.

    The structured record of the finding rides back on the `findings` state
    key rather than in the message list, so the supervisor's model never reads
    it, but the report writer and the evidence audit can work from it later.
    """
    token = current_case.set((account_id, name))
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": f"Account {account_id}.\n\n{question}"}]}
        )
    finally:
        current_case.reset(token)

    finding = final_text(result)
    measured = usage.record(account_id, name, result)

    # Persist the finding so CASES.md can reconstruct the trail afterwards.
    # It lives in the run store, not in the supervisor's message list, so the
    # supervisor's model still never sees anything but the rendered text.
    try:
        with actions.cursor() as cur:
            cur.execute(
                "INSERT INTO findings (account_id, specialist, question, finding, "
                "chars_inside, chars_crossed) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    account_id,
                    name,
                    question,
                    finding,
                    measured["chars_inside"],
                    measured["chars_crossed"],
                ),
            )
    except Exception:
        pass

    return Command(
        update={
            "messages": [ToolMessage(content=finding, tool_call_id=tool_call_id)],
            "account_id": account_id,
            "specialists_consulted": [name],
            "findings": [
                {
                    "specialist": name,
                    "finding": finding,
                    "chars_inside": measured["chars_inside"],
                    "chars_crossed": measured["chars_crossed"],
                }
            ],
        }
    )
