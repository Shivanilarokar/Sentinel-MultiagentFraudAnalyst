"""The deterministic layer.

Both bugs these tests guard against return **zero rows** rather than raising, so
nothing would tell you they were broken except a check on the numbers.
"""

from __future__ import annotations

import pytest

from sentinel import queries

SAMPLE = "A00985"


def test_incident_window_uses_the_column_separator():
    """SQLite's datetime() returns a space; the `ts` column uses a 'T'.

    Mixing them is a string comparison that quietly matches nothing:

        '2026-02-27T12:46:44' > '2026-02-27 17:46:44'   because 'T' > ' '
    """
    lo, hi = queries.incident_window(SAMPLE)
    assert "T" in lo and "T" in hi, "window bounds must match the ts format"
    assert " " not in lo and " " not in hi


def test_incident_window_spans_the_trigger_transaction():
    """In 342 of 411 alerts the trigger lands AFTER triggered_at.

    A window measured backwards from the alert therefore misses the episode.
    """
    lo, hi = queries.incident_window(SAMPLE)
    alerts = queries.get_alerts(SAMPLE)
    for a in alerts:
        assert lo <= a["triggered_at"] <= hi
        if a["trigger_txn_ts"]:
            assert lo <= a["trigger_txn_ts"] <= hi


def test_incident_activity_finds_the_whole_episode():
    """On A00985 a backward window sees one transaction; the real episode is four."""
    episode = queries.get_incident_activity(SAMPLE)
    assert len(episode) == 4
    assert round(sum(t["amount"] for t in episode)) == 216_091


@pytest.mark.parametrize("account_id", ["A00985", "A00008", "A00013"])
def test_every_alerted_account_has_a_window(account_id):
    lo, hi = queries.incident_window(account_id)
    assert lo and hi and lo < hi


def test_case_notes_carry_a_timing_label():
    """Whether a note came before or after the incident decides what it means."""
    notes = queries.get_case_notes(SAMPLE)
    assert notes, "A00985 has a note; if this fails the join is broken"
    for n in notes:
        assert n["timing"] in ("before_incident", "during_incident", "after_incident")
        assert n["days_before_alert"] is not None


def test_the_deciding_note_is_labelled_before_the_incident():
    """N00080 was filed five hours before the alert. That is the whole case."""
    notes = {n["note_id"]: n for n in queries.get_case_notes(SAMPLE)}
    assert notes["N00080"]["timing"] == "before_incident"
    assert "video KYC" in notes["N00080"]["note"]


def test_the_work_list_is_the_whole_queue(alerted):
    assert len(alerted) == 276
    assert alerted == sorted(alerted)


def test_baseline_precedes_the_incident():
    """A baseline that included the incident would define the anomaly as normal."""
    baseline = queries.get_spending_baseline(SAMPLE)
    lo, _ = queries.incident_window(SAMPLE)
    assert baseline["window_start"] == lo
    assert baseline["txn_count"] > 0


def test_no_query_returns_rows_for_an_unknown_account():
    for fn in (queries.get_alerts, queries.get_incident_activity,
               queries.get_case_notes, queries.get_disputes,
               queries.get_prior_cases, queries.get_shared_devices):
        assert fn("A99999") == []
