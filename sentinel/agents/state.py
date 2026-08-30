"""The supervisor's state schema."""

from __future__ import annotations

from typing import Annotated, NotRequired

from langchain.agents.middleware import AgentState


def _dedupe(a: list | None, b: list | None) -> list:
    """Union preserving first-seen order. Consulting twice records once."""
    return list(dict.fromkeys((a or []) + (b or [])))


def _extend(a: list | None, b: list | None) -> list:
    return (a or []) + (b or [])


def _keep_latest(a: str | None, b: str | None) -> str | None:
    """Last writer wins, ignoring blanks.

    Every specialist wrapper stamps `account_id` onto state. When the
    supervisor issues two consult calls in the same turn - which it is
    entitled to do, and does - both Commands write this key in one step.
    Without a reducer LangGraph raises InvalidUpdateError, the step is
    rejected, and the assistant message is left holding tool_calls with no
    matching tool messages; the next model call then fails with a 400. Six
    accounts were lost to that chain in the first full sweep.

    The value is the same string in every writer, so any merge rule is
    correct. What matters is that one exists.
    """
    return b or a


class SupervisorState(AgentState):
    """State carried by the supervisor across one case.

    `findings` holds each specialist's report as structured data. It is a state
    key, not a message, so the supervisor's model never reads it - only the
    rendered final message reaches the conversation. It exists so the report
    writer and the evidence audit can work from identifiers rather than
    re-parsing prose.

    `specialists_consulted` is what turns ordering from a request into a rule:
    the disposition wrapper refuses while 'context' is absent.
    """

    account_id: NotRequired[Annotated[str, _keep_latest]]
    findings: NotRequired[Annotated[list[dict], _extend]]
    specialists_consulted: NotRequired[Annotated[list[str], _dedupe]]
