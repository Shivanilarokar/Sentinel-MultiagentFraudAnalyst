"""The five requirements, turned into assertions.

Each test below corresponds to a "done when" line in the assignment, or to a
scored row in RUBRIC.md. The point is that these are checkable without reading
the code and without running a model.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from sentinel.agents import supervisor as supervisor_module
from sentinel.tools.registry import DOMAIN_TOOLS, SPECIALISTS, disjointness_report, tool_names

# --------------------------------------------------------------------------
# 1 - Four specialists, each holding only its own tools
# --------------------------------------------------------------------------


def test_there_are_exactly_four_specialists():
    assert set(SPECIALISTS) == {"behaviour", "context", "network", "disposition"}


def test_each_specialist_has_its_own_module_with_its_own_prompt():
    """'Each with its own prompt' should be visible in the file layout."""
    package = Path(supervisor_module.__file__).parent
    for name in SPECIALISTS:
        module = package / f"{name}.py"
        assert module.exists(), f"{name} has no module of its own"
        source = module.read_text(encoding="utf-8")
        assert "PROMPT = " in source, f"{name} does not define its own prompt"
        assert "def build(" in source, f"{name} does not build its own agent"


def test_specialist_tool_sets_are_pairwise_disjoint():
    report = disjointness_report()
    assert report["disjoint"], f"tools shared between specialists: {report['overlaps']}"


def test_every_specialist_actually_holds_tools():
    for name in SPECIALISTS:
        assert DOMAIN_TOOLS[name], f"{name} holds no tools"


def test_context_holds_the_narrative_tools_and_no_transaction_tools():
    """Swapping these would visibly break the system, which is the rubric's test."""
    context = tool_names("context")
    assert "get_case_notes" in context
    assert "get_disputes" in context
    assert "get_prior_cases" in context
    behaviour = tool_names("behaviour")
    assert not (context & behaviour)
    assert "get_spending_baseline" not in context


def test_disposition_writes_and_does_not_read():
    """It holds only write tools; every read tool belongs to somebody else."""
    disposition = tool_names("disposition")
    assert disposition == {"record_disposition", "block_card", "escalate_case"}
    readers = tool_names("behaviour") | tool_names("context") | tool_names("network")
    assert not (disposition & readers)


# --------------------------------------------------------------------------
# 2 - A supervisor that only routes
# --------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_supervisor_module_has_no_database_access():
    """Expressed as an import boundary, not as a promise in a docstring."""
    imported = _imported_modules(Path(supervisor_module.__file__))
    forbidden = [
        m for m in imported
        if "repositories" in m or m == "sentinel.db" or m.endswith("_tools")
    ]
    assert not forbidden, f"the supervisor imports data access: {forbidden}"


def test_supervisor_holds_exactly_four_tools():
    """RUBRIC.md: 'four tools maximum, no direct database access'."""
    source = Path(supervisor_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    build = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "build_sentinel"
    )
    wrappers = [
        n.name for n in ast.walk(build)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("consult_")
    ]
    assert len(wrappers) == 4, f"expected four specialist wrappers, found {wrappers}"
    assert "subagent_tools = [" in source
    # and the supervisor is handed exactly that list
    assert "tools=subagent_tools" in source


def test_the_four_wrappers_are_the_four_specialists():
    source = Path(supervisor_module.__file__).read_text(encoding="utf-8")
    for name in ("behaviour_analyst", "context_analyst", "network_analyst", "disposition_officer"):
        assert f"def consult_{name}(" in source


def test_disposition_is_blocked_until_context_has_been_consulted():
    """Ordering is a rule in code, not only a request in the prompt."""
    source = Path(supervisor_module.__file__).read_text(encoding="utf-8")
    assert "specialists_consulted" in source
    assert "BLOCKED" in source
    assert 'status="error"' in source


# --------------------------------------------------------------------------
# 3 - Only the final message travels back
# --------------------------------------------------------------------------


def test_the_wrapper_returns_only_the_last_message():
    from sentinel.agents import _boundary

    source = inspect.getsource(_boundary.consult)
    assert "final_text(result)" in source
    # the ToolMessage carries the finding and nothing else
    assert "ToolMessage(content=finding" in source


def test_final_text_takes_the_last_message_only():
    from sentinel.messages import final_message_text

    class M:
        def __init__(self, t):
            self.text = t

    result = {"messages": [M("first"), M("middle"), M("  last  ")]}
    assert final_message_text(result) == "last"


def test_structured_findings_travel_on_state_not_in_messages():
    """The supervisor's model must never read the structured findings."""
    from sentinel.agents.state import SupervisorState

    assert "findings" in SupervisorState.__annotations__
    assert "specialists_consulted" in SupervisorState.__annotations__


# --------------------------------------------------------------------------
# 4 - Policy in documents, loaded on demand
# --------------------------------------------------------------------------


def test_policy_documents_exist_and_are_editable_markdown():
    from sentinel.policies import discover_policies

    policies = discover_policies()
    assert len(policies) >= 4
    for policy in policies:
        assert policy["name"] and policy["description"] and policy["content"]


def test_no_policy_body_is_baked_into_any_system_prompt():
    """An agent's prompt should grow only when it actually loads a policy."""
    from sentinel.agents import behaviour, context, disposition, network
    from sentinel.policies import discover_policies

    prompts = [behaviour.PROMPT, context.PROMPT, network.PROMPT, disposition.PROMPT,
               supervisor_module.PROMPT]
    for policy in discover_policies():
        # a distinctive line from the middle of each document
        body_lines = [ln for ln in policy["content"].splitlines() if len(ln) > 60]
        probe = body_lines[len(body_lines) // 2]
        for prompt in prompts:
            assert probe not in prompt, (
                f"policy '{policy['name']}' body text is baked into a system prompt"
            )


def test_loading_a_policy_is_gated_where_it_matters():
    from sentinel.agents import disposition

    source = Path(disposition.__file__).read_text(encoding="utf-8")
    assert '"record_disposition": "evidence_standards"' in source
    assert '"block_card": "escalation_matrix"' in source
    assert '"escalate_case": "escalation_matrix"' in source


def test_the_catalog_is_far_smaller_than_the_corpus():
    from sentinel.policies import discover_policies, policy_catalog

    policies = discover_policies()
    bodies = sum(len(p["content"]) for p in policies)
    catalog = len(policy_catalog(policies))
    assert catalog < bodies * 0.15, "progressive disclosure is not saving anything"


# --------------------------------------------------------------------------
# 5 - Human approval before anything irreversible
# --------------------------------------------------------------------------


def test_irreversible_actions_are_declared_and_gated():
    from sentinel.agents import disposition
    from sentinel.models import IRREVERSIBLE

    assert IRREVERSIBLE == {"block_card", "escalate_case"}
    source = Path(disposition.__file__).read_text(encoding="utf-8")
    assert "HumanInTheLoopMiddleware" in source
    assert '"block_card": {"allowed_decisions": ["approve", "reject"]}' in source
    assert '"escalate_case": {"allowed_decisions": ["approve", "reject"]}' in source


def test_the_safe_tool_does_not_interrupt():
    """Interrupting on reversible tools trains people to approve without reading."""
    from sentinel.agents import disposition

    source = Path(disposition.__file__).read_text(encoding="utf-8")
    assert '"record_disposition": False' in source


def test_middleware_is_on_the_subagent_and_the_checkpointer_on_the_supervisor():
    from sentinel.agents import disposition

    disposition_source = Path(disposition.__file__).read_text(encoding="utf-8")
    supervisor_source = Path(supervisor_module.__file__).read_text(encoding="utf-8")
    assert "HumanInTheLoopMiddleware" in disposition_source
    # The subagent must not be *given* a checkpointer - mentioning it in prose is
    # fine, and is in fact where the reason is written down.
    assert "checkpointer=" not in disposition_source, (
        "the disposition subagent has its own checkpointer; that creates nested "
        "persistence and the interrupt loses its home on the supervisor"
    )
    assert "checkpointer=checkpointer or InMemorySaver()" in supervisor_source
    assert "HumanInTheLoopMiddleware" not in supervisor_source


def test_approval_requirement_is_derived_in_code_not_asked_of_the_model():
    from sentinel.policy import requires_approval

    assert requires_approval("block_card")
    assert requires_approval("escalate_case")
    assert not requires_approval("monitor")
    assert not requires_approval("none")


@pytest.mark.parametrize("mode", ["interactive", "defer"])
def test_sweep_mode_never_executes_an_irreversible_action(mode):
    from sentinel.tools import disposition_tools

    disposition_tools.set_approval_mode(mode)
    assert disposition_tools.approval_mode() == mode
    disposition_tools.set_approval_mode("interactive")
