"""The tool registry: one place that says who holds what.

This module exists so that "each specialist holds only its own tools" is a
checkable fact rather than a claim in a README. `tests/test_architecture.py`
imports `DOMAIN_TOOLS` and asserts the four sets are pairwise disjoint, and
asserts the supervisor's set contains none of them.

Note what is *not* here: there is no entry for the supervisor. The supervisor's
tools are the four specialist wrappers built in `agents.py`, and it has no
access to anything in this file. That is the requirement, expressed as an
import boundary.
"""

from __future__ import annotations

from langchain.tools import BaseTool

from sentinel.tools.behaviour_tools import BEHAVIOUR_TOOLS
from sentinel.tools.context_tools import CONTEXT_TOOLS
from sentinel.tools.disposition_tools import DISPOSITION_TOOLS
from sentinel.tools.network_tools import NETWORK_TOOLS

SPECIALISTS: tuple[str, ...] = ("behaviour", "context", "network", "disposition")

DOMAIN_TOOLS: dict[str, list[BaseTool]] = {
    "behaviour": BEHAVIOUR_TOOLS,
    "context": CONTEXT_TOOLS,
    "network": NETWORK_TOOLS,
    "disposition": DISPOSITION_TOOLS,
}


def tool_names(specialist: str) -> set[str]:
    return {t.name for t in DOMAIN_TOOLS[specialist]}


def all_leaf_tool_names() -> set[str]:
    """Every tool that touches data or takes an action, across all specialists.

    Used by the isolation test: none of these names may ever appear in the
    supervisor's message list.
    """
    return {t.name for tools in DOMAIN_TOOLS.values() for t in tools}


def disjointness_report() -> dict[str, object]:
    """Which tools each specialist holds, and any overlap. Used by `sentinel doctor`."""
    overlaps: dict[str, set[str]] = {}
    names = {s: tool_names(s) for s in SPECIALISTS}
    for i, a in enumerate(SPECIALISTS):
        for b in SPECIALISTS[i + 1 :]:
            shared = names[a] & names[b]
            if shared:
                overlaps[f"{a}|{b}"] = shared
    return {
        "counts": {s: len(names[s]) for s in SPECIALISTS},
        "tools": {s: sorted(names[s]) for s in SPECIALISTS},
        "overlaps": overlaps,
        "disjoint": not overlaps,
    }
