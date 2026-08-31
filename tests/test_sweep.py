"""The sweep contract, and what the irreversible tools do with nobody watching.

Neither needs a model: starting a sweep is three cheap statements, and whether
an action is executed or queued is decided before any tool body runs.
"""

from __future__ import annotations

import time

import pytest

from sentinel import sweep
from sentinel.tools import disposition_tools


def test_starting_a_sweep_returns_immediately(runtime, monkeypatch):
    """Three statements: one SELECT DISTINCT, one job row, one Thread.start().

    Budget is five seconds. If this ever creeps up it means work has leaked into
    the call that starts the job, which is the one thing the three-tool split
    exists to prevent.
    """
    started = []
    monkeypatch.setattr(sweep.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda s: started.append(1)})())

    t0 = time.perf_counter()
    job_id = sweep.start_queue_sweep(limit=None)
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.0, f"took {elapsed:.3f}s"
    assert job_id.startswith("sweep-")
    assert started, "the worker thread was never started"


def test_status_is_readable_while_the_job_runs(runtime, monkeypatch):
    monkeypatch.setattr(sweep.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda s: None})())
    job_id = sweep.start_queue_sweep(limit=10)

    status = sweep.check_sweep_status(job_id)
    assert status["status"] == "running"
    assert status["total"] == 10
    assert status["progress_pct"] == 0.0
    assert status["remaining"] == 10


def test_an_unknown_job_is_reported_without_pretending_to_be_a_job(runtime):
    """`sweep_jobs` has an `error` COLUMN, so every real row already has that key.

    A guard written as `if "error" in status` is therefore always true. This is
    the regression test for that: a missing job is signalled by the absence of
    `status`, not the presence of `error`.
    """
    result = sweep.check_sweep_status("sweep-nope")
    assert "status" not in result
    assert result["unknown_job"] == "sweep-nope"

    collected = sweep.collect_sweep_results("sweep-nope")
    assert "dispositions" not in collected


def test_a_resumed_sweep_skips_what_is_already_decided(runtime, monkeypatch):
    """A sweep should be re-runnable to pick up whatever the last one dropped."""
    monkeypatch.setattr(sweep.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda s: None})())
    runtime.write(
        "INSERT INTO dispositions (account_id, verdict, confidence, reasoning, "
        "evidence, missing, decided_at) VALUES "
        "('A00000', 'fraud', 'high', 'x', '[]', '', '2026-03-02')")

    everything = sweep.check_sweep_status(sweep.start_queue_sweep(skip_done=False))["total"]
    remaining = sweep.check_sweep_status(sweep.start_queue_sweep(skip_done=True))["total"]
    assert remaining == everything - 1


# ---------------------------------------------------------------------------
# Unattended behaviour
# ---------------------------------------------------------------------------
class _Runtime:
    def __init__(self, unattended: bool):
        self.state = {"unattended": unattended}


@pytest.fixture()
def with_verdict(runtime):
    runtime.write(
        "INSERT INTO dispositions (account_id, verdict, confidence, reasoning, "
        "evidence, missing, decided_at) VALUES "
        "('A00008', 'fraud', 'high', 'x', '[]', '', '2026-03-02')")
    return runtime


def test_an_unattended_run_queues_rather_than_executes(with_verdict):
    """An unattended run that could block 276 cards is worse than one that cannot."""
    out = disposition_tools._file_action(
        "A00008", "block_card", "K000080", "money still moving", _Runtime(True))
    assert "QUEUED" in out and "not executed" in out

    row = with_verdict.fetch("SELECT * FROM actions")[0]
    assert row["status"] == "proposed"
    assert row["approved_by"] is None


def test_an_attended_run_executes_because_approval_already_happened(with_verdict):
    """By the time the tool body runs, the middleware has been approved."""
    out = disposition_tools._file_action(
        "A00008", "block_card", "K000080", "money still moving", _Runtime(False))
    assert "EXECUTED" in out

    row = with_verdict.fetch("SELECT * FROM actions")[0]
    assert row["status"] == "approved"
    assert row["approved_by"] == "analyst"


def test_an_action_without_a_verdict_is_refused(runtime):
    out = disposition_tools._file_action(
        "A00013", "block_card", "K000130", "hunch", _Runtime(False))
    assert "REFUSED" in out
    assert runtime.fetch("SELECT * FROM actions") == []


def test_an_action_contradicting_its_verdict_is_refused(runtime):
    runtime.write(
        "INSERT INTO dispositions (account_id, verdict, confidence, reasoning, "
        "evidence, missing, decided_at) VALUES "
        "('A00013', 'legitimate', 'high', 'x', '[]', '', '2026-03-02')")
    out = disposition_tools._file_action(
        "A00013", "block_card", "K000130", "just in case", _Runtime(False))
    assert "REFUSED" in out
    assert runtime.fetch("SELECT * FROM actions") == []
