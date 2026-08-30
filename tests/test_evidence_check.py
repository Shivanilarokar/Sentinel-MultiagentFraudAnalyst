"""Citations must resolve to real rows belonging to the right account.

A specialist's final message is a claim. These tests cover the code that tells
a claim from a fact.
"""

from __future__ import annotations

from sentinel.analysis.evidence_check import check_ref, refusal_for
from sentinel.models import EvidenceRef

REAL_NOTE = "N00080"          # belongs to the customer behind A00985
REAL_ALERT_985 = "AL0170"     # A00985's alert
REAL_ALERT_782 = "AL0009"     # A00782's alert


def test_a_correct_citation_passes():
    ref = EvidenceRef(kind="alert", ref_id=REAL_ALERT_985)
    assert check_ref("A00985", ref).ok


def test_a_nonexistent_identifier_is_caught():
    check = check_ref("A00985", EvidenceRef(kind="alert", ref_id="AL9999"))
    assert not check.ok
    assert "does not exist" in check.problem


def test_a_real_identifier_on_the_wrong_account_is_caught():
    """The dangerous one: well-formed, real, and pointing at somebody else."""
    check = check_ref("A00782", EvidenceRef(kind="alert", ref_id=REAL_ALERT_985))
    assert not check.ok
    assert "belongs to A00985" in check.problem


def test_case_notes_resolve_through_the_customer():
    """Notes are keyed on customer_id; the check has to make that hop too."""
    ref = EvidenceRef(
        kind="case_note",
        ref_id=REAL_NOTE,
        quote="Customer upgraded their phone on the 14th",
    )
    assert check_ref("A00985", ref).ok


def test_a_fabricated_quote_is_caught():
    ref = EvidenceRef(
        kind="case_note",
        ref_id=REAL_NOTE,
        quote="Customer confirmed they were on holiday in Dubai for three weeks",
    )
    check = check_ref("A00985", ref)
    assert not check.ok
    assert "is not in that record" in check.problem


def test_quoting_a_fragment_is_allowed():
    """A specialist may quote part of a long note, but it must be part of it."""
    ref = EvidenceRef(kind="case_note", ref_id=REAL_NOTE, quote="Verified with video KYC")
    assert check_ref("A00985", ref).ok


def test_quote_matching_ignores_whitespace_and_case():
    ref = EvidenceRef(
        kind="case_note",
        ref_id=REAL_NOTE,
        quote="  customer   UPGRADED their phone on the 14th ",
    )
    assert check_ref("A00985", ref).ok


def test_refusal_message_lists_every_problem():
    refs = [
        EvidenceRef(kind="alert", ref_id="AL9999"),
        EvidenceRef(kind="alert", ref_id=REAL_ALERT_782),
    ]
    refusal = refusal_for("A00985", refs)
    assert refusal is not None
    assert "2 citation(s)" in refusal
    assert "does not exist" in refusal
    assert "belongs to" in refusal


def test_no_refusal_when_everything_checks_out():
    refs = [
        EvidenceRef(kind="alert", ref_id=REAL_ALERT_985),
        EvidenceRef(kind="case_note", ref_id=REAL_NOTE, quote="Verified with video KYC"),
    ]
    assert refusal_for("A00985", refs) is None
