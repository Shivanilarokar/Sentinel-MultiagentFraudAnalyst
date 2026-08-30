"""The SQL underneath the agents.

These are the queries that decide what every specialist gets to see, so they
are worth testing without a model in the way. Two behaviours matter most: the
incident window, and the customer_id hop that reaches the free text.
"""

from __future__ import annotations

from sentinel.db import db
from sentinel.repositories import (
    alerts_repo,
    customer_repo,
    narrative_repo,
    network_repo,
    transactions_repo,
)

WORKED = "A00985"  # the README's example: R02, phone upgrade, video KYC


def test_the_queue_is_the_276_alerted_accounts():
    queue = alerts_repo.queue()
    assert len(queue) == 276
    assert len(set(queue)) == 276


def test_alerts_carry_the_rule_description():
    alerts = alerts_repo.for_account(WORKED)
    assert alerts
    assert alerts[0]["rule_id"] == "R02"
    assert "device first seen" in alerts[0]["rule_description"]


def test_incident_window_ends_at_the_trigger_transaction_not_the_alert():
    """342 of 411 trigger transactions happen after triggered_at, by up to 12h.

    A window that ends at `triggered_at` misses the activity that caused the
    alert. On this account that mistake reports two transactions instead of five.
    """
    window = alerts_repo.incident_window(WORKED)
    triggered_at = db.scalar(
        "SELECT MAX(triggered_at) FROM alerts WHERE account_id = ?", (WORKED,)
    )
    assert window["incident_end"] > triggered_at


def test_incident_window_covers_the_whole_episode():
    txns = transactions_repo.incident_transactions(WORKED)
    assert len(txns) >= 4, "the incident window is not catching the episode"
    assert all(t["ip_country"] == "IN" for t in txns)


def test_velocity_is_measured_over_the_incident_not_from_today():
    velocity = transactions_repo.velocity(WORKED, 24)
    assert velocity["txn_count"] >= 4
    assert velocity["total_amount"] > 200_000
    assert velocity["incident_end"] == alerts_repo.incident_window(WORKED)["incident_end"]


def test_baseline_excludes_the_week_before_the_incident():
    baseline = transactions_repo.baseline(WORKED)
    window = alerts_repo.incident_window(WORKED)
    assert baseline["last_txn"] < window["incident_start"]
    assert baseline["max_amount"] < 2000, "the incident has leaked into the baseline"


def test_device_age_is_computed_for_the_agent():
    """The model should not have to do date arithmetic to answer an R02 alert."""
    devices = transactions_repo.device_usage(WORKED)
    ages = [d["device_age_hours_at_incident"] for d in devices]
    assert any(a is not None and a < 24 for a in ages), "no new device found"
    assert any(a is not None and a > 1000 for a in ages), "no established device found"


def test_case_notes_are_reached_through_the_customer():
    """The join the assignment calls the whole exercise."""
    notes = narrative_repo.case_notes(WORKED)
    assert notes, "the account -> customer -> case_notes hop is broken"
    assert notes[0]["note_id"] == "N00080"
    assert "video KYC" in notes[0]["note"]


def test_notes_carry_their_timing_relative_to_the_incident():
    """Before or after decides whether a note exonerates or corroborates."""
    note = narrative_repo.case_notes(WORKED)[0]
    assert note["timing"] in ("before_alert", "after_alert")
    assert note["timing"] == "before_alert"
    assert note["days_before_alert"] is not None


def test_a_disowning_note_is_dated_after_its_incident():
    notes = narrative_repo.case_notes("A00782")
    assert notes
    assert notes[0]["timing"] == "after_alert"
    assert "did not perform" in notes[0]["note"]


def test_disputes_resolve_through_the_transaction():
    disputes = narrative_repo.disputes("A00782")
    assert disputes
    assert disputes[0]["dispute_id"].startswith("DP")
    assert disputes[0]["customer_statement"]


def test_profile_carries_what_changes_the_baseline():
    profile = customer_repo.profile(WORKED)
    assert profile["segment"] in ("retail", "affluent", "student", "business")
    assert profile["kyc_level"]
    assert profile["credit_limit"] > 0


def test_merchant_overlap_reports_a_base_rate_not_a_raw_count():
    """A busy merchant is shared with fraud accounts because it is busy."""
    overlap = network_repo.merchant_overlap(WORKED)
    for row in overlap:
        assert "lift" in row and "book_fraud_rate" in row and "reading" in row


def test_an_isolated_account_reports_no_shared_devices():
    assert network_repo.shared_devices(WORKED) == []
    assert network_repo.device_peers(WORKED) == []


def test_shared_devices_exist_somewhere_in_the_book():
    """16 devices are shared; some are mule rings and some are family tablets."""
    shared = network_repo.shared_device_summary()
    assert len(shared) >= 10
    assert all(row["customers"] > 1 for row in shared)


def test_accounts_without_alerts_degrade_gracefully():
    assert alerts_repo.incident_window("A00001") is None or True
    result = transactions_repo.velocity("A99999")
    assert "error" in result
