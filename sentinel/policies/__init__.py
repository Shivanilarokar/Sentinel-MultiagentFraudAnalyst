"""Policy documents, disclosed progressively.

Fraud typologies, risk appetite and escalation thresholds belong in files an
analyst can edit without touching Python. They are stored as Markdown with YAML
front-matter, and an agent loads the one it needs, when it needs it, instead of
carrying all of them in every prompt.

Three levels of disclosure:

    level 1   name + description      injected into the system prompt (cheap)
    level 2   the full document       loaded on demand via `load_policy`
    level 3   anything it references  fetched later, if at all

`PolicyCatalogMiddleware` handles level 1 and re-scans the directory on every
model call, so editing a `.md` changes behaviour with no code change and no
rebuild. `load_policy` handles level 2 and records what it loaded in agent
state, which lets `PolicyGateMiddleware` refuse a tool until its governing
document has actually been read.

That last part matters. A prompt asking an agent to read the policy is a
request. The gate is what makes it a rule.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
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

POLICY_DIR = Path(__file__).resolve().parent
FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)

# Set by the case runner so a policy load can be attributed to an account and
# an agent in the ledger. Absent outside a case (tests, doctor), which is fine.
current_case: ContextVar[tuple[str, str] | None] = ContextVar("current_case", default=None)


class Policy(TypedDict):
    """One editable unit of fraud-desk doctrine."""

    name: str  # unique id, and the argument to load_policy
    description: str  # one or two sentences, shown in the system prompt
    content: str  # the full body, loaded only when asked for


def _parse(path: Path) -> Policy:
    """Split a policy file into front-matter metadata and body."""
    raw = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(raw)
    if not match:
        return {"name": path.stem, "description": path.stem, "content": raw.strip()}

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


def discover_policies(directory: Path = POLICY_DIR) -> list[Policy]:
    """Scan the policy directory. Called fresh so edits take effect immediately."""
    return [_parse(p) for p in sorted(directory.glob("*.md"))]


POLICIES: list[Policy] = discover_policies()


def policy_catalog(policies: list[Policy] | None = None) -> str:
    """The level-1 view: names and descriptions only."""
    return "\n".join(f"- **{p['name']}**: {p['description']}" for p in (policies or POLICIES))


def _record_load(policy_name: str) -> None:
    """Append to the policy ledger, so on-demand loading is provable after a run."""
    case = current_case.get()
    if case is None:
        return
    account_id, agent = case
    try:
        from sentinel.db import actions

        with actions.cursor() as cur:
            cur.execute(
                "INSERT INTO policy_loads (account_id, agent, policy) VALUES (?, ?, ?)",
                (account_id, agent, policy_name),
            )
    except Exception:
        # The ledger is observability, not correctness. Never fail a case for it.
        pass


class PolicyState(AgentState):
    """Agent state extended to remember which policies have been read."""

    policies_loaded: NotRequired[
        Annotated[list[str], lambda a, b: list(dict.fromkeys((a or []) + (b or [])))]
    ]


@tool
def load_policy(policy_names: list[str], runtime: ToolRuntime) -> Command:
    """Load one or more fraud-desk policy documents into your context.

    Call this BEFORE deciding anything the documents govern. These files carry
    the desk's current thresholds, typologies and evidence standards. You
    cannot infer them from the data, so guessing instead of loading is an
    error that will show up in your reasoning.

    **Ask for every document you expect to need in a single call.** Each
    separate call re-sends everything already in your context, so loading four
    documents one at a time costs several times what loading them together
    does. `load_policy(["evidence_standards", "risk_appetite"])` is one round
    trip; two calls are two.

    Args:
        policy_names: Names from "Available policy documents". Pass a list even
            for one, e.g. ["evidence_standards"].
    """
    if isinstance(policy_names, str):  # tolerate a bare name
        policy_names = [policy_names]

    available = {p["name"]: p for p in discover_policies()}
    sections: list[str] = []
    loaded: list[str] = []
    missing: list[str] = []

    for name in policy_names:
        policy = available.get(name)
        if policy is None:
            missing.append(name)
            continue
        _record_load(name)
        loaded.append(name)
        sections.append(f"# Policy loaded: {name}\n\n{policy['content']}")

    if missing:
        sections.append(
            f"No policy named {', '.join(repr(m) for m in missing)}. "
            f"Available: {', '.join(available)}"
        )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content="\n\n---\n\n".join(sections)
                    or f"Nothing loaded. Available: {', '.join(available)}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
            "policies_loaded": loaded,
        }
    )


def requires_policy(policy_name: str, runtime: ToolRuntime) -> str | None:
    """Guard helper: returns an error string if `policy_name` has not been read.

    Use inside a tool to enforce ordering a prompt alone cannot:

        if err := requires_policy("evidence_standards", runtime):
            return err
    """
    loaded = runtime.state.get("policies_loaded") or []
    if policy_name in loaded:
        return None
    return (
        f"Blocked: call load_policy('{policy_name}') before using this tool, "
        f"so that your decision follows the current desk policy."
    )


class PolicyCatalogMiddleware(AgentMiddleware[PolicyState]):
    """Injects the policy catalog into the system prompt on every model call.

    Running per call rather than baking the list into a static prompt means a
    document added to the directory at runtime becomes visible immediately.
    It also keeps the base prompt free of policy *content*, which is the whole
    point of loading on demand.
    """

    state_schema = PolicyState
    tools = [load_policy]

    def __init__(self, directory: Path = POLICY_DIR):
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
            f"\nAlready loaded this case: {', '.join(loaded)}."
            if loaded
            else "\nNo policy documents loaded yet."
        )
        addendum = (
            "\n\n## Available policy documents\n\n"
            f"{policy_catalog(policies)}\n"
            f"{status}\n\n"
            "Call `load_policy([names])` to read them in full before you rely on "
            "what they cover. Ask for every document you expect to need in ONE "
            "call - separate calls re-send your whole context each time. "
            "Do not guess at policy you have not read."
        )
        base = request.system_message
        content = (list(base.content_blocks) if base else []) + [
            {"type": "text", "text": addendum}
        ]
        return handler(request.override(system_message=SystemMessage(content=content)))


class PolicyGateMiddleware(AgentMiddleware[PolicyState]):
    """Refuses to run a tool until its governing policy has been read.

        PolicyGateMiddleware({"record_disposition": "evidence_standards"})

    `requires_policy` lets a single tool check for itself. This applies the
    same rule across a map of tools without touching their source, and it
    returns an error ToolMessage without ever calling the handler, so the tool
    genuinely does not run.
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
                    f"BLOCKED: '{request.tool_call['name']}' cannot run until you have "
                    f"read the '{needed}' policy. Call load_policy('{needed}') now, "
                    f"follow what it says, then try again."
                ),
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        return handler(request)


__all__ = [
    "Policy",
    "POLICIES",
    "POLICY_DIR",
    "PolicyState",
    "PolicyCatalogMiddleware",
    "PolicyGateMiddleware",
    "current_case",
    "discover_policies",
    "load_policy",
    "policy_catalog",
    "requires_policy",
]
