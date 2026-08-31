"""The rules that are checked in code rather than taught in a prompt.

The documents in `policies/` are advisory: the model reads them and mostly
complies. These are the ones that hold every time.
"""

from __future__ import annotations

import pytest

from sentinel import validation

ACCOUNT = "A00985"
REAL_ALERT = "AL0170"
REAL_NOTE = "N00080"
QUOTE = "Verified with video KYC"


# ---------------------------------------------------------------------------
# Layer 1: shape
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind,ref", [
    ("alert", "ALxxxx1"),        # a placeholder
    ("alert", "R02"),            # a rule id where an alert id belongs
    ("note", "N80"),             # truncated
    ("transaction", "T123"),     # too short
    ("note", ""),
])
def test_bad_shapes_are_refused(kind, ref):
    assert validation.check_shape(kind, ref) is not None


def test_good_shapes_pass():
    assert validation.check_shape("alert", REAL_ALERT) is None
    assert validation.check_shape("note", REAL_NOTE) is None


def test_an_unknown_kind_cannot_be_cited():
    assert validation.check_shape("hunch", "H0001") is not None


# ---------------------------------------------------------------------------
# Layer 2: ownership
# ---------------------------------------------------------------------------
def test_a_real_id_belonging_to_another_account_is_refused():
    """AL0001 is a perfectly valid alert. It is not this account's."""
    assert validation.check_ownership("alert", "AL0001", ACCOUNT) is not None


def test_an_id_that_does_not_exist_is_refused():
    assert validation.check_ownership("note", "N99999", ACCOUNT) is not None


def test_this_accounts_own_records_pass():
    assert validation.check_ownership("alert", REAL_ALERT, ACCOUNT) is None
    assert validation.check_ownership("note", REAL_NOTE, ACCOUNT) is None


# ---------------------------------------------------------------------------
# Layer 3: quotes
# ---------------------------------------------------------------------------
def test_invented_words_are_refused():
    assert validation.check_quote(
        "note", REAL_NOTE, "the customer admitted making the transfers") is not None


def test_real_words_pass_regardless_of_case_and_spacing():
    assert validation.check_quote("note", REAL_NOTE, QUOTE) is None
    assert validation.check_quote("note", REAL_NOTE, "  verified   with VIDEO kyc ") is None


# ---------------------------------------------------------------------------
# The verdict rules
# ---------------------------------------------------------------------------
def _disposition(**kw):
    base = dict(
        account_id=ACCOUNT, verdict="fraud", confidence="high",
        reasoning="Five transactions in forty minutes from a device first seen "
                  "that morning, escalating in value, with no explanation on file.",
        evidence=[validation.EvidenceRef("alert", REAL_ALERT)],
        missing="",
    )
    return validation.Disposition(**{**base, **kw})


def test_a_legitimate_verdict_cannot_rest_on_numbers_alone():
    """Only something a human wrote can explain an alert away."""
    problems = validation.validate(_disposition(verdict="legitimate"))
    assert any("human wrote" in p for p in problems)


def test_a_legitimate_verdict_citing_a_note_is_accepted():
    d = _disposition(
        verdict="legitimate",
        evidence=[validation.EvidenceRef("alert", REAL_ALERT),
                  validation.EvidenceRef("note", REAL_NOTE, QUOTE)],
    )
    assert validation.validate(d) == []


def test_insufficient_evidence_must_name_what_would_settle_it():
    problems = validation.validate(_disposition(verdict="insufficient_evidence"))
    assert any("name what would resolve it" in p for p in problems)


def test_insufficient_evidence_with_a_named_gap_is_accepted():
    d = _disposition(
        verdict="insufficient_evidence",
        missing="a customer callback confirming the 27 February transfers",
    )
    assert validation.validate(d) == []


@pytest.mark.parametrize("verdict", ["guilty", "maybe", "FRAUD", ""])
def test_verdicts_outside_the_vocabulary_are_refused(verdict):
    assert any("verdict must be one of" in p
               for p in validation.validate(_disposition(verdict=verdict)))


def test_reasoning_must_be_long_enough_to_defend():
    assert any("too short" in p
               for p in validation.validate(_disposition(reasoning="Looks bad.")))


# ---------------------------------------------------------------------------
# Actions may not contradict their verdict
# ---------------------------------------------------------------------------
def test_blocking_a_card_on_a_legitimate_verdict_is_refused():
    assert validation.check_action("block_card", "legitimate") is not None


def test_escalating_a_legitimate_verdict_is_refused():
    assert validation.check_action("escalate_case", "legitimate") is not None


def test_blocking_on_an_unresolved_case_is_refused():
    """You do not stop someone's card on a case you cannot make."""
    assert validation.check_action("block_card", "insufficient_evidence") is not None


def test_escalating_an_unresolved_case_is_allowed():
    """That is precisely what escalation is for."""
    assert validation.check_action("escalate_case", "insufficient_evidence") is None


def test_blocking_on_confirmed_fraud_is_allowed():
    assert validation.check_action("block_card", "fraud") is None
