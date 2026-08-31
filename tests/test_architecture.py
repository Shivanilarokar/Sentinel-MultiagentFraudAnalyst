"""The structural properties: who holds which tools, and who can reach the database.

These are the claims that are easiest to make and easiest to lose silently, so
they are asserted rather than described.
"""

from __future__ import annotations

import ast
from pathlib import Path

import sentinel.tools as T

SRC = Path(__file__).resolve().parents[1] / "src" / "sentinel"


def test_the_four_toolsets_are_pairwise_disjoint():
    assert T.check_isolation() == []


def test_each_domain_holds_the_tools_it_should():
    assert len(T.TOOLSETS["behaviour"]) == 7
    assert len(T.TOOLSETS["context"]) == 4
    assert len(T.TOOLSETS["network"]) == 3
    assert len(T.TOOLSETS["disposition"]) == 3


def test_the_disposition_officer_holds_no_read_tool():
    """It writes; it does not read.

    An officer that could look things up would quietly paper over a supervisor
    that forgot to consult the file, and the routing order would stop meaning
    anything.
    """
    assert not T.names(T.DISPOSITION_TOOLS) & T.names(T.READ_TOOLS)


def test_the_context_specialist_owns_the_narrative():
    """The free text is exactly one specialist's job."""
    context = T.names(T.TOOLSETS["context"])
    assert {"get_case_notes", "get_disputes", "get_prior_cases"} <= context
    for other in ("behaviour", "network", "disposition"):
        assert not T.names(T.TOOLSETS[other]) & {"get_case_notes", "get_disputes"}


def _imported_modules(path: Path) -> set[str]:
    """Every module name a file imports, from its AST rather than a text search."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def test_the_supervisor_module_cannot_reach_the_database():
    """Parsed, not grepped: no import path from the supervisor to any query."""
    imports = _imported_modules(SRC / "agents" / "supervisor.py")
    assert "sentinel.queries" not in imports

    # It may reach the queue tools, which schedule work rather than read rows.
    # It may not reach any toolset that touches the bank's data.
    for domain in ("behaviour_tools", "context_tools", "network_tools",
                   "disposition_tools"):
        assert not any(domain in i for i in imports), imports


def _supervisor_tools():
    from sentinel.agents.supervisor import build

    class _FakeAgent:
        def invoke(self, *_a, **_k):
            raise AssertionError("should not be called")

    specialists = {n: _FakeAgent() for n in
                   ("behaviour", "context", "network", "disposition")}
    _, tools = build(model=None, specialists=specialists)
    return tools


def test_the_supervisor_holds_one_tool_per_specialist():
    assert {t.name for t in _supervisor_tools()} >= {
        "consult_behaviour_analyst", "consult_context_specialist",
        "consult_network_analyst", "consult_disposition_officer",
    }


def test_the_supervisor_also_drives_the_queue():
    """The sweep is something the supervisor starts, not something that calls it."""
    assert {t.name for t in _supervisor_tools()} >= {
        "start_queue_sweep", "check_sweep_status", "collect_sweep_results",
    }


def test_the_supervisor_holds_nothing_else():
    assert len(_supervisor_tools()) == 7


def test_a_sweep_cannot_start_another_sweep():
    """Every account inside a sweep runs its own supervisor, which holds these
    tools too. Without the guard the first sweep forks a second."""
    from sentinel.tools.queue_tools import QUEUE_TOOLS

    class _Runtime:
        state = {"unattended": True}
        tool_call_id = "x"

    for tool in QUEUE_TOOLS:
        args = (_Runtime(), 0) if tool.name == "start_queue_sweep" else ("job-1", _Runtime())
        assert "REFUSED" in tool.func(*args)


def test_every_specialist_lives_in_its_own_module():
    for name in ("behaviour", "context", "network", "disposition", "supervisor"):
        assert (SRC / "agents" / f"{name}.py").exists()


def test_each_specialist_prompt_is_distinct():
    """Swapping two prompts should visibly break the system, so they must differ."""
    from sentinel.agents import behaviour, context, disposition, network

    prompts = {
        "behaviour": behaviour.PROMPT,
        "context": context.PROMPT,
        "network": network.PROMPT,
        "disposition": disposition.PROMPT,
    }
    assert len(set(prompts.values())) == 4

    # And each names its own domain's concern.
    assert "normal for THIS" in prompts["behaviour"]
    assert "TIMING" in prompts["context"] and "SUBJECT" in prompts["context"]
    assert "acting alone" in prompts["network"]
    assert "insufficient_evidence" in prompts["disposition"]


def test_specialists_are_told_their_last_message_is_the_interface():
    from sentinel.agents import behaviour, context, network

    for prompt in (behaviour.PROMPT, context.PROMPT, network.PROMPT):
        assert "ONLY THING THAT REACHES THE SUPERVISOR" in prompt
