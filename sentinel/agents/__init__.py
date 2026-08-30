"""The agent package: four specialists and one supervisor, one module each.

    behaviour.py    reads 108,249 transactions   is this normal for this customer?
    context.py      reads 260 notes, 86 disputes did the customer already explain it?
                    and 200 prior cases
    network.py      reads devices and merchants  is this account acting alone?
                    across accounts
    disposition.py  writes, does not read        what do we do, and who approves it?
    supervisor.py   routes only, no DB access    who to ask, and in what order

Each specialist module owns its own system prompt, its own tool list and its
own middleware, so "each agent has its own prompt and only the tools for its
own domain" is visible in the file layout rather than buried in a factory.

`_boundary.py` holds the single function that isolates a specialist and returns
only its final message; `supervisor.py` holds the state schema.
"""

from __future__ import annotations

from sentinel.agents._boundary import (
    FINAL_MESSAGE_CONTRACT,
    consult,
    final_message_text,
    final_text,
    message_text,
)
from sentinel.agents.supervisor import SPECIALISTS, SupervisorState, build_sentinel

__all__ = [
    "build_sentinel",
    "SupervisorState",
    "SPECIALISTS",
    "consult",
    "final_message_text",
    "final_text",
    "message_text",
    "FINAL_MESSAGE_CONTRACT",
]
