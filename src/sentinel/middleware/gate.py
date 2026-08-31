"""Refusing to run a tool until its governing policy has been read.

A prompt asking an agent to read the policy first is a *request*, and the model
mostly complies. This is what makes it a *rule*: `wrap_tool_call` returns an
error `ToolMessage` **instead of** calling the handler, so a model that ignores
the instruction still cannot file a verdict it has not read the standards for.

The map lives here rather than in `agents/`, next to the middleware that
enforces it, so the two cannot drift apart.
"""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain.messages import ToolMessage

from sentinel.middleware.state import PolicyState

# Only the tools that produce a permanent record are gated. Reading is not a
# decision, so the query tools are left alone — gating those would just make
# every specialist load a document before it could look anything up.
POLICY_GATES = {
    "record_disposition": "evidence_standards",
    "block_card": "escalation_matrix",
    "escalate_case": "escalation_matrix",
}


class PolicyGateMiddleware(AgentMiddleware[PolicyState]):
    """Blocks a tool call until the policy it depends on is in context.

    Applied as a map rather than a check inside each tool, because the
    disposition tools are also imported by the reports and the tests, which have
    no policy to obey.

        PolicyGateMiddleware({"record_disposition": "evidence_standards"})
    """

    state_schema = PolicyState

    def __init__(self, required: dict[str, str] | None = None):
        super().__init__()
        self.required = POLICY_GATES if required is None else required

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
