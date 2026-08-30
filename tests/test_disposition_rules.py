"""The hard rules a disposition must satisfy.

`policies/*.md` teaches these; `sentinel/policy.py` guarantees them. These
tests are the guarantee.
"""

from __future__ import annotations

import pytest

from sentinel.models import EvidenceRef
from sentinel.policy import check_disposition

LONG = (
    "R02 fired on a high-value transaction from a device six hours old. The case "
    "note filed before the incident records a verified phone upgrade, the spend "
    "stayed domestic and in daylight hours, and no network link exists."
)

NOTE = EvidenceRef(
    kind="case_note",
    ref_id="N00080",
    quote="Customer upgraded their phone on the 14th",
    detail="explains the device",
)
ALERT = EvidenceRef(kind="alert", ref_id="AL0170", detail="R02")


def ok(**kwargs) -> str | None:
    base = dict(
        verdict="legitimate",
        confidence="high",
        reasoning=LONG,
        action="none",
        evidence=[NOTE],
        information_required=[],
    )
    base.update(kwargs)
    return check_disposition(**base)


def test_a_well_formed_disposition_is_accepted():
    assert ok() is None


@pytest.mark.parametrize("verdict", ["guilty", "", "FRAUD "])
def test_unknown_verdicts_are_refused(verdict):
    assert "verdict must be one of" in ok(verdict=verdict)


def test_reasoning_must_be_substantial():
    assert "REFUSED" in ok(reasoning="looks fine")


def test_insufficient_evidence_must_name_what_would_resolve_it():
    """The rubric awards nine points for naming the gap. This makes it structural."""
    refusal = ok(verdict="insufficient_evidence", action="monitor", evidence=[ALERT],
                 information_required=[])
    assert "must name what would resolve it" in refusal

    assert ok(
        verdict="insufficient_evidence",
        action="monitor",
        evidence=[ALERT],
        information_required=["A case note explaining the device registered on 27 Feb."],
    ) is None


def test_blank_information_required_does_not_count():
    refusal = ok(verdict="insufficient_evidence", action="monitor", evidence=[ALERT],
                 information_required=["   ", ""])
    assert "must name what would resolve it" in refusal


def test_legitimate_must_cite_something_a_human_wrote():
    """Calling it legitimate asserts somebody explained it. Point at the text."""
    refusal = ok(evidence=[ALERT])
    assert "must cite the text that explains it" in refusal


def test_a_quote_is_required_on_narrative_evidence():
    bare = EvidenceRef(kind="case_note", ref_id="N00080", detail="a note exists")
    assert "verbatim quote" in ok(evidence=[bare])


def test_fraud_and_legitimate_must_cite_something():
    assert "must cite the records" in ok(verdict="fraud", action="monitor", evidence=[])


@pytest.mark.parametrize(
    "verdict,action",
    [
        ("legitimate", "block_card"),
        ("legitimate", "escalate_case"),
        ("insufficient_evidence", "block_card"),
        ("fraud", "none"),
    ],
)
def test_actions_must_be_proportionate_to_the_verdict(verdict, action):
    refusal = ok(
        verdict=verdict,
        action=action,
        evidence=[NOTE],
        information_required=["something specific"],
    )
    assert "is not permitted for a" in refusal


@pytest.mark.parametrize(
    "kind,bad_id",
    [
        ("alert", "ALxxxx1"),
        ("alert", "R02"),
        ("transaction", "T000"),
        ("case_note", "NOTE1"),
        ("dispute", "D0001"),
    ],
)
def test_placeholder_and_wrong_shaped_identifiers_are_refused(kind, bad_id):
    """A fabricated id looks like evidence and is not."""
    ref = EvidenceRef(kind=kind, ref_id=bad_id, quote="x" * 20, detail="d")
    refusal = ok(verdict="fraud", action="monitor", evidence=[ref])
    assert "is not a valid" in refusal


def test_empty_identifier_is_refused():
    ref = EvidenceRef(kind="transaction", ref_id="  ")
    assert "needs a real ref_id" in ok(verdict="fraud", action="monitor", evidence=[ref])
