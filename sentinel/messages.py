"""Small helpers for reading LangChain messages.

Lives at the package root rather than inside `agents/` because both the agent
layer and the token ledger need it, and putting it in either would make them
import each other.
"""

from __future__ import annotations


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
