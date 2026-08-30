"""The tools, and the registry that proves who holds what.

Leaf tools always return a string. Structured payloads are serialised here
rather than returned as dicts, so the message list holds exactly what the model
will read and token accounting means something.

`DOMAIN_TOOLS` at the bottom is the artifact `tests/test_architecture.py`
imports to assert the four specialist tool sets are pairwise disjoint, and that
the supervisor's set contains none of them. There is deliberately no entry for
the supervisor: its tools are the four specialist wrappers built in
`agents/supervisor.py`, and it has no access to anything in this package.
"""

from __future__ import annotations

import json
from typing import Any

# --------------------------------------------------------------------------
# Rendering helpers
#
# Defined before the tool modules are imported below, because those modules
# import these names from this package.
# --------------------------------------------------------------------------

DROP = (None, "", [], {})


def compact(obj: Any) -> Any:
    """Recursively drop keys whose values carry no information.

    Across roughly 1,100 specialist invocations in a full sweep, empty fields
    are a meaningful share of the bill and none of the meaning.
    """
    if isinstance(obj, dict):
        return {k: compact(v) for k, v in obj.items() if v not in DROP}
    if isinstance(obj, list):
        return [compact(v) for v in obj]
    return obj


def as_json(obj: Any, *, note: str | None = None) -> str:
    """Serialise a payload for a tool result, optionally with a leading note."""
    body = json.dumps(compact(obj), indent=1, default=str, ensure_ascii=False)
    return f"{note}\n{body}" if note else body


def empty(message: str) -> str:
    """A deliberate, readable 'nothing here'.

    An absence is evidence in this task - an account with no case notes is a
    different case from one whose notes explain everything - so tools say so in
    words rather than returning an empty list the model might skim past.
    """
    return f"NONE FOUND. {message}"


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------

from sentinel.tools.behaviour_tools import BEHAVIOUR_TOOLS  # noqa: E402
from sentinel.tools.context_tools import CONTEXT_TOOLS  # noqa: E402
from sentinel.tools.disposition_tools import DISPOSITION_TOOLS  # noqa: E402
from sentinel.tools.network_tools import NETWORK_TOOLS  # noqa: E402

SPECIALISTS: tuple[str, ...] = ("behaviour", "context", "network", "disposition")

DOMAIN_TOOLS: dict[str, list] = {
    "behaviour": BEHAVIOUR_TOOLS,
    "context": CONTEXT_TOOLS,
    "network": NETWORK_TOOLS,
    "disposition": DISPOSITION_TOOLS,
}


def tool_names(specialist: str) -> set[str]:
    return {t.name for t in DOMAIN_TOOLS[specialist]}


def all_leaf_tool_names() -> set[str]:
    """Every tool that touches data or takes an action, across all specialists.

    Used by the isolation test: none of these names may appear in the
    supervisor's message list.
    """
    return {t.name for tools in DOMAIN_TOOLS.values() for t in tools}


def disjointness_report() -> dict[str, object]:
    """Which tools each specialist holds, and any overlap. Used by `sentinel doctor`."""
    names = {s: tool_names(s) for s in SPECIALISTS}
    overlaps: dict[str, set[str]] = {}
    for i, a in enumerate(SPECIALISTS):
        for b in SPECIALISTS[i + 1:]:
            shared = names[a] & names[b]
            if shared:
                overlaps[f"{a}|{b}"] = shared
    return {
        "counts": {s: len(names[s]) for s in SPECIALISTS},
        "tools": {s: sorted(names[s]) for s in SPECIALISTS},
        "overlaps": overlaps,
        "disjoint": not overlaps,
    }
