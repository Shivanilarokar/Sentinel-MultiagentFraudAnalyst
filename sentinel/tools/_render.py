"""Rendering helpers shared by every tool.

Leaf tools always return a string. Structured payloads are serialised here
rather than returned as dicts, so the message list holds exactly what the model
will read and token accounting means something.

`compact` drops null and zero-ish keys before serialising. Across roughly 1,100
specialist invocations in a full sweep, empty fields are a meaningful share of
the bill and none of the meaning.
"""

from __future__ import annotations

import json
from typing import Any

DROP = (None, "", [], {})


def compact(obj: Any) -> Any:
    """Recursively drop keys whose values carry no information."""
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
