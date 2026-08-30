"""The asynchronous queue sweep.

The requirement is that starting a sweep returns straight away. RUBRIC.md
allows five seconds; the assignment README says under one. This asserts the
stricter figure, and it asserts it without calling a model - the sweep's
start path does one query, one insert and one thread start, so it is fast by
construction rather than by luck.
"""

from __future__ import annotations

import time

import pytest

from sentinel import sweep
from sentinel.db import actions


@pytest.fixture
def clean_jobs():
    with actions.cursor() as cur:
        cur.execute("DELETE FROM jobs")
    yield
    with actions.cursor() as cur:
        cur.execute("DELETE FROM jobs")


def test_starting_a_sweep_returns_in_under_a_second(monkeypatch, clean_jobs):
    """The account work must not happen on the calling thread."""
    # Replace the worker so the test measures the start path, not the agents.
    monkeypatch.setattr(sweep, "_work_queue", lambda *a, **k: None)

    started = time.time()
    job = sweep.start_queue_sweep(limit=0)
    elapsed = time.time() - started

    assert elapsed < 1.0, f"start_queue_sweep took {elapsed:.3f}s"
    assert job["job_id"].startswith("job_")
    assert job["accounts"] == 276
    assert job["status"] == "running"


def test_the_job_is_recorded_so_status_survives_a_restart(monkeypatch, clean_jobs):
    monkeypatch.setattr(sweep, "_work_queue", lambda *a, **k: None)
    job = sweep.start_queue_sweep(limit=5)

    status = sweep.check_sweep_status(job["job_id"])
    assert status["total"] == 5
    assert status["progress"] == "0/5"
    assert status["status"] == "running"


def test_status_of_an_unknown_job_is_reported_not_raised():
    assert "error" in sweep.check_sweep_status("job_nope")
    assert "error" in sweep.collect_sweep_results("job_nope")


def test_limit_restricts_the_work_list(monkeypatch, clean_jobs):
    captured = {}

    def fake(job_id, account_ids, workers):
        captured["accounts"] = account_ids
        captured["workers"] = workers

    monkeypatch.setattr(sweep, "_work_queue", fake)
    sweep.start_queue_sweep(limit=7, workers=2)
    time.sleep(0.3)
    assert len(captured["accounts"]) == 7
    assert captured["workers"] == 2


def test_each_account_gets_its_own_thread_id(monkeypatch, clean_jobs):
    """Isolated contexts: two accounts must never share a conversation."""
    from sentinel.sweep import thread_for

    assert thread_for("A00001", "job_x") != thread_for("A00002", "job_x")
    assert thread_for("A00001", "job_x") != thread_for("A00001", "job_y")


def test_the_worker_thread_is_not_a_daemon(monkeypatch, clean_jobs):
    """A daemon thread dies when the CLI exits, so the sweep could never finish."""
    monkeypatch.setattr(sweep, "_work_queue", lambda *a, **k: time.sleep(0.5))
    job = sweep.start_queue_sweep(limit=1)
    thread = sweep._THREADS[job["job_id"]]
    assert not thread.daemon


def test_a_failing_account_does_not_abort_the_job(clean_jobs, monkeypatch):
    """One bad account must not take the queue down with it."""
    calls = []

    def flaky(account_id, **kwargs):
        calls.append(account_id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return sweep.CaseResult(account_id=account_id, status="completed")

    monkeypatch.setattr(sweep, "run_case", flaky)
    job_id = sweep._new_job(3)
    sweep._work_queue(job_id, ["A00000", "A00001", "A00002"], workers=1)

    status = sweep.check_sweep_status(job_id)
    assert status["status"] == "completed"
    assert status["failed"] >= 1
    assert status["completed"] + status["failed"] == 3
