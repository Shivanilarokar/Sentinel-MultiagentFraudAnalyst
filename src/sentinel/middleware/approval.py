"""The human approval gate.

Two rules people get wrong, so they are stated here rather than left implicit in
whichever module happens to assemble the agents:

    the middleware  goes on the disposition SUBAGENT, because that is where the
                    irreversible tools live
    the checkpointer goes on the SUPERVISOR, because that is the run being
                    frozen and thawed

Put them the other way round and you get nested persistence and an interrupt
with nowhere to live.

The interrupt fires inside a subagent invoked within a supervisor tool and
propagates all the way up, so the whole run — supervisor, specialists, findings —
freezes together.
"""

from __future__ import annotations

from langchain.agents.middleware import HumanInTheLoopMiddleware

from sentinel.tools.disposition_tools import IRREVERSIBLE

DESCRIPTION_PREFIX = "IRREVERSIBLE ACTION pending analyst approval"


def approval_middleware(tool_names: list[str] | None = None) -> HumanInTheLoopMiddleware:
    """Pause before any tool that cannot be undone.

    Approve and reject only — deliberately no `edit`. Letting a reviewer silently
    rewrite *which* card gets blocked is precisely the failure an approval gate
    exists to prevent: the analyst would be signing off on one action and a
    different one would run.

    `record_disposition` is absent from the list on purpose. Writing a verdict is
    reversible — it can be corrected — so interrupting on it would train whoever
    is reviewing to click approve without reading, which is worse than not
    asking.

    Args:
        tool_names: Which tools to gate. Defaults to the irreversible set
            declared alongside the tools themselves, so the gate and the tools
            cannot drift apart.
    """
    return HumanInTheLoopMiddleware(
        interrupt_on={
            name: {"allowed_decisions": ["approve", "reject"]}
            for name in (tool_names or IRREVERSIBLE)
        },
        description_prefix=DESCRIPTION_PREFIX,
    )
