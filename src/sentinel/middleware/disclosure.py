"""Progressive disclosure over the policy documents.

Typologies, risk appetite and escalation thresholds belong in files an analyst
can edit without touching code. With policy in Python, moving a threshold is a
pull request; with policy in files, it is somebody editing a document.

Three levels:

    level 1   name + description      always in the system prompt, because it is tiny
    level 2   the full document body  loaded on demand via `load_policy`
    level 3   what the body points at only if the body's task needs it

`PolicyMiddleware` handles level 1. `load_policy` handles level 2, and records
every load in the runtime database so on-demand loading is *provable* after a run
rather than merely claimed.

The catalog is re-scanned on **every model call**, not baked into a static
prompt. That is what makes an analyst's edit take effect on the next call rather
than after a restart.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable, TypedDict

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain.messages import SystemMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from sentinel import db
from sentinel.config import POLICIES_DIR
from sentinel.middleware.state import PolicyState

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


class Policy(TypedDict):
    """One editable policy document."""

    name: str          # the load_policy argument
    description: str   # one or two sentences, shown in every system prompt
    content: str       # the full body, loaded only when asked for


def _parse(path: Path) -> Policy:
    """Split a policy file into its YAML front-matter and its body."""
    raw = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(raw)
    if not match:
        return {"name": path.stem, "description": path.stem, "content": raw}

    meta_block, body = match.groups()
    meta: dict[str, str] = {}
    for line in meta_block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return {
        "name": meta.get("name", path.stem),
        "description": meta.get("description", ""),
        "content": body.strip(),
    }


def discover_policies(directory: Path = POLICIES_DIR) -> list[Policy]:
    """Scan the policy directory fresh, so an edit takes effect immediately.

    Called on every model call. A static list read once at import time would mean
    an analyst's edit did nothing until a restart.
    """
    return [_parse(p) for p in sorted(directory.glob("*.md"))]


def policy_catalog(policies: list[Policy] | None = None) -> str:
    """The level-1 view: names and descriptions only."""
    return "\n".join(
        f"- **{p['name']}**: {p['description']}"
        for p in (policies if policies is not None else discover_policies())
    )


def disclosure_stats() -> dict:
    """How much of the corpus is absent from a prompt until it is needed.

    The claim "loaded on demand" is worth a number, and this is where it comes
    from.
    """
    policies = discover_policies()
    level_1 = len(policy_catalog(policies))
    level_2 = sum(len(p["content"]) for p in policies)
    return {
        "documents": len(policies),
        "catalog_chars": level_1,
        "body_chars": level_2,
        "withheld_pct": round(100 * level_2 / (level_1 + level_2), 1) if level_2 else 0.0,
    }


@tool
def load_policy(policy_name: str, runtime: ToolRuntime) -> Command:
    """Read a desk policy document in full before acting in the area it covers.

    The documents hold the typologies, thresholds and escalation rules this desk
    works to. You cannot infer them, so guessing instead of loading is an error.
    Load the one that fits the question in front of you, not all of them.

    Args:
        policy_name: One of the names listed under "Desk policies" in your
            system prompt, e.g. 'narrative_reading'.
    """
    for policy in discover_policies():
        if policy["name"] == policy_name:
            db.write(
                "INSERT INTO policy_loads (account_id, agent, policy, loaded_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    runtime.state.get("account_id"),
                    getattr(runtime, "agent_name", None) or "specialist",
                    policy_name,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            return Command(update={
                "messages": [ToolMessage(
                    content=f"# Policy loaded: {policy_name}\n\n{policy['content']}",
                    tool_call_id=runtime.tool_call_id,
                )],
                "policies_loaded": [policy_name],
            })

    available = ", ".join(p["name"] for p in discover_policies())
    return Command(update={"messages": [ToolMessage(
        content=f"No policy named '{policy_name}'. Available: {available}",
        tool_call_id=runtime.tool_call_id,
        status="error",
    )]})


class PolicyMiddleware(AgentMiddleware[PolicyState]):
    """Appends the policy catalog to the system prompt, freshly, every call.

    Because it runs per call rather than baking the list into a static prompt, a
    document added or edited while the process is running is visible on the very
    next model call. No rebuild, no restart, no redeploy.
    """

    state_schema = PolicyState
    tools = [load_policy]

    def __init__(self, directory: Path = POLICIES_DIR):
        super().__init__()
        self.directory = directory

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        policies = discover_policies(self.directory)
        loaded = request.state.get("policies_loaded") or []
        status = (
            f"\nAlready loaded this run: {', '.join(loaded)}."
            if loaded else "\nYou have not loaded any policy yet."
        )

        addendum = (
            "\n\n## Desk policies\n\n"
            f"{policy_catalog(policies)}\n"
            f"{status}\n\n"
            "Call `load_policy(<name>)` to read one in full before you act in the "
            "area it covers. Do not guess at policy you have not read, and do not "
            "load documents the question does not need."
        )

        base = request.system_message
        content = (list(base.content_blocks) if base else []) + [
            {"type": "text", "text": addendum}
        ]
        return handler(request.override(system_message=SystemMessage(content=content)))
