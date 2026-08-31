"""Progressive disclosure over the policy documents.

Typologies, risk appetite and escalation thresholds belong in files an analyst
can edit without touching code. With policy in Python, moving a threshold is a
pull request; with policy in files, it is somebody editing a document.

An agent loads the one it needs, when it needs it, instead of carrying all of
them in every prompt.

Three levels of disclosure, the same shape the class taught:

    level 1   name + description      always in the system prompt, because it is tiny
    level 2   the full document body  loaded on demand via `load_policy`
    level 3   what the body points at only if the body's task needs it

`PolicyMiddleware` handles level 1. `load_policy` handles level 2, and records
every load in `runtime/actions.db` so on-demand loading is *provable* after a run
rather than merely claimed.

The catalog is re-scanned on **every model call**, not baked into a static
prompt. That is what makes the requirement's demonstration work: edit
`policies/risk_appetite.md`, run the same account again, and behaviour changes
with no code change and no restart.

`PolicyGateMiddleware` is the other half. A prompt asking an agent to read the
policy is a *request*; the gate is what makes it a *rule*. It short-circuits the
tool call and returns an error the model can act on, without the tool running.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Callable, NotRequired, TypedDict

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain.messages import SystemMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from sentinel import db
from sentinel.config import POLICIES_DIR

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

    Called on every model call. That is the point: a static list read once at
    import time would mean an analyst's edit did nothing until a restart.
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

    Reported by `sentinel doctor` and quoted in the write-up, because the claim
    "loaded on demand" is worth a number.
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


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def _merge_loaded(a: list[str] | None, b: list[str] | None) -> list[str]:
    """Union that preserves order and drops duplicates."""
    return list(dict.fromkeys((a or []) + (b or [])))


class PolicyState(AgentState):
    """Agent state extended to remember which policies have been read.

    `account_id` rides along so every ledger row can be attributed to the case
    it belongs to, which is what makes the policy-load ledger auditable.
    """

    policies_loaded: NotRequired[Annotated[list[str], _merge_loaded]]
    account_id: NotRequired[str]

    # True during a queue sweep, where there is nobody to ask for approval. The
    # irreversible tools read this and QUEUE their action instead of executing
    # it. An unattended run that could block 276 cards is a worse system than
    # one that cannot.
    unattended: NotRequired[bool]


# ---------------------------------------------------------------------------
# Level 2: the load tool
# ---------------------------------------------------------------------------
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
            state = runtime.state
            db.write(
                "INSERT INTO policy_loads (account_id, agent, policy, loaded_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    state.get("account_id"),
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


# ---------------------------------------------------------------------------
# Level 1: the catalog, injected on every model call
# ---------------------------------------------------------------------------
class PolicyMiddleware(AgentMiddleware[PolicyState]):
    """Appends the policy catalog to the system prompt, freshly, every call.

    Because it runs per call rather than baking the list into a static prompt, a
    document added or edited while the process is running is visible on the very
    next model call. No rebuild, no restart, no code change.
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


class PolicyGateMiddleware(AgentMiddleware[PolicyState]):
    """Refuses to run a tool until its governing policy has actually been read.

    It applies the rule across a map of tools without touching their source,
    which matters
    because the disposition tools are shared with tests and reports that have no
    policy to obey.

        PolicyGateMiddleware({"record_disposition": "evidence_standards"})

    The refusal is returned as an error `ToolMessage` and the tool never runs, so
    a model that ignores the instruction still cannot write an undocumented
    verdict.
    """

    state_schema = PolicyState

    def __init__(self, required: dict[str, str]):
        super().__init__()
        self.required = required

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        needed = self.required.get(request.tool_call["name"])
        if needed and needed not in (request.state.get("policies_loaded") or []):
            return ToolMessage(
                content=(
                    f"BLOCKED: '{request.tool_call['name']}' cannot run until you "
                    f"have read the '{needed}' policy. Call load_policy('{needed}') "
                    f"now, follow what it says, and then try again."
                ),
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        return handler(request)


# ---------------------------------------------------------------------------
# Which tool may not run until which policy has been read
# ---------------------------------------------------------------------------
# Declared here rather than in `agents.py` so the map is next to the middleware
# that enforces it. The three tools that produce a permanent record are gated;
# the read tools are not, because looking something up is not a decision.
POLICY_GATES = {
    "record_disposition": "evidence_standards",
    "block_card": "escalation_matrix",
    "escalate_case": "escalation_matrix",
}


def main() -> None:
    """Demonstrate progressive disclosure, including the hot reload.

        python -m sentinel.policy_skills
    """
    print("\nPOLICY: PROGRESSIVE DISCLOSURE")
    print("=" * 72)

    print("\nLEVEL 1 - names and descriptions, in every system prompt:\n")
    print(policy_catalog())

    stats = disclosure_stats()
    print(f"\n{'-' * 72}")
    print(f"  {stats['documents']} documents")
    print(f"  level 1 catalog : {stats['catalog_chars']:,} chars, always present")
    print(f"  level 2 bodies  : {stats['body_chars']:,} chars, loaded only on request")
    print(f"  withheld        : {stats['withheld_pct']}% of the corpus is absent from")
    print("                    a prompt until an agent actually asks for it")

    print("\nENFORCED LOADING - these tools will not run until the policy is read:")
    for tool_name, policy_name in POLICY_GATES.items():
        print(f"  {tool_name:<20} requires  {policy_name}")

    # The requirement asks us to show that editing a file changes behaviour with
    # no code change. The catalog is re-scanned on every model call, so a file
    # written now is visible on the very next one - no restart, no rebuild.
    print(f"\n{'-' * 72}")
    print("HOT RELOAD - adding a document with the process already running:\n")
    before = {p["name"] for p in discover_policies()}
    probe = POLICIES_DIR / "_demo_probe.md"
    probe.write_text(
        "---\n"
        "name: _demo_probe\n"
        "description: A document created while this process was running.\n"
        "---\n\n"
        "If you can read this line, the catalog was re-scanned, not cached.\n",
        encoding="utf-8",
    )
    try:
        after = {p["name"] for p in discover_policies()}
        added = after - before
        print(f"  wrote {probe.name}")
        print(f"  next discover_policies() sees: {sorted(added) or 'NOTHING - cached!'}")
        body = next(p for p in discover_policies() if p["name"] == "_demo_probe")
        print(f"  load_policy would return: \"{body['content']}\"")
    finally:
        probe.unlink(missing_ok=True)
    print(f"  removed {probe.name}, catalog back to {len(discover_policies())} documents")

    print("\n" + "=" * 72)
    print("Edit any file in src/sentinel/policies/ and behaviour changes on the")
    print("next model call. No code change, no restart, no redeploy.\n")


__all__ = [
    "Policy", "PolicyState", "PolicyMiddleware", "PolicyGateMiddleware",
    "POLICY_GATES", "discover_policies", "policy_catalog", "disclosure_stats",
    "load_policy",
]


if __name__ == "__main__":
    main()
