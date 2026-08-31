"""Progressive disclosure, the policy gate, and the approval gate.

None of these needs a model. What matters is what is *withheld* from a prompt and
what is *refused* before a tool runs, and both are decidable without one.
"""

from __future__ import annotations

import pytest

from sentinel import middleware
from sentinel.config import POLICIES_DIR
from sentinel.tools.disposition_tools import IRREVERSIBLE

EXPECTED = {"fraud_typologies", "narrative_reading", "risk_appetite",
            "escalation_matrix", "evidence_standards"}


def test_every_policy_document_parses():
    policies = middleware.discover_policies()
    assert {p["name"] for p in policies} == EXPECTED
    for p in policies:
        assert p["description"], f"{p['name']} has no description"
        assert len(p["content"]) > 500, f"{p['name']} looks empty"


def test_the_catalog_is_only_names_and_descriptions():
    """Level 1 must stay small enough to sit in every prompt."""
    catalog = middleware.policy_catalog()
    assert len(catalog) < 2000
    for name in EXPECTED:
        assert name in catalog


def test_no_policy_body_is_baked_into_the_catalog():
    """Take a line from the middle of each document; none may appear at level 1."""
    catalog = middleware.policy_catalog()
    for policy in middleware.discover_policies():
        lines = [line for line in policy["content"].splitlines() if len(line) > 60]
        probe = lines[len(lines) // 2]
        assert probe not in catalog, f"{policy['name']} body leaked into the catalog"


def test_most_of_the_corpus_is_withheld():
    stats = middleware.disclosure_stats()
    assert stats["documents"] == 5
    assert stats["withheld_pct"] > 90, stats


def test_the_catalog_is_rescanned_not_cached():
    """An analyst's edit has to take effect without a restart."""
    before = {p["name"] for p in middleware.discover_policies()}
    probe = POLICIES_DIR / "_pytest_probe.md"
    probe.write_text(
        "---\nname: _pytest_probe\ndescription: written during the test run.\n---\n\nbody\n",
        encoding="utf-8")
    try:
        after = {p["name"] for p in middleware.discover_policies()}
        assert "_pytest_probe" in after - before
    finally:
        probe.unlink(missing_ok=True)
    assert {p["name"] for p in middleware.discover_policies()} == before


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
class _Request:
    """The smallest thing `wrap_tool_call` needs."""

    def __init__(self, name: str, loaded: list[str]):
        self.tool_call = {"name": name, "id": "call-1"}
        self.state = {"policies_loaded": loaded}


def _handler(_request):
    return "THE TOOL RAN"


@pytest.mark.parametrize("tool_name,needed", middleware.POLICY_GATES.items())
def test_a_gated_tool_is_refused_until_its_policy_is_read(tool_name, needed):
    gate = middleware.PolicyGateMiddleware()
    result = gate.wrap_tool_call(_Request(tool_name, loaded=[]), _handler)
    assert result != "THE TOOL RAN"
    assert result.status == "error"
    assert needed in result.content


@pytest.mark.parametrize("tool_name,needed", middleware.POLICY_GATES.items())
def test_a_gated_tool_runs_once_its_policy_is_read(tool_name, needed):
    gate = middleware.PolicyGateMiddleware()
    assert gate.wrap_tool_call(_Request(tool_name, loaded=[needed]), _handler) == "THE TOOL RAN"


def test_reading_tools_are_not_gated():
    """Looking something up is not a decision."""
    gate = middleware.PolicyGateMiddleware()
    assert gate.wrap_tool_call(_Request("get_case_notes", loaded=[]), _handler) == "THE TOOL RAN"


def test_the_wrong_policy_does_not_unlock_a_tool():
    gate = middleware.PolicyGateMiddleware()
    result = gate.wrap_tool_call(
        _Request("record_disposition", loaded=["fraud_typologies"]), _handler)
    assert result != "THE TOOL RAN"


# ---------------------------------------------------------------------------
# The approval gate
# ---------------------------------------------------------------------------
def test_only_irreversible_tools_interrupt():
    gate = middleware.approval_middleware()
    assert set(gate.interrupt_on) == set(IRREVERSIBLE)
    assert "record_disposition" not in gate.interrupt_on


def test_edit_is_not_an_allowed_decision():
    """Rewriting WHICH card gets blocked is the failure the gate exists to stop."""
    gate = middleware.approval_middleware()
    for config in gate.interrupt_on.values():
        assert set(config["allowed_decisions"]) == {"approve", "reject"}
