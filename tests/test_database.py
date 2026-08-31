"""The source database is opened in a mode that cannot write.

This is the guarantee everything else rests on, so it is checked directly rather
than inferred from the absence of INSERT statements in the codebase.
"""

from __future__ import annotations

import sqlite3

import pytest

from sentinel import db


def test_insert_is_refused():
    """A write raises rather than being silently filtered out."""
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        with db.read_only() as conn:
            conn.execute("INSERT INTO alerts (alert_id) VALUES ('X')")


def test_update_is_refused():
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        with db.read_only() as conn:
            conn.execute("UPDATE alerts SET status = 'closed'")


def test_delete_is_refused():
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        with db.read_only() as conn:
            conn.execute("DELETE FROM alerts")


def test_query_only_pragma_is_set():
    """`mode=ro` alone would do. `query_only` is the second lock."""
    with db.read_only() as conn:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1


def test_the_queue_is_the_size_we_think_it_is():
    """If these move, every measured number in the reports is stale."""
    with db.read_only() as conn:
        assert conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 411
        assert conn.execute(
            "SELECT COUNT(DISTINCT account_id) FROM alerts").fetchone()[0] == 276
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 108_249
        assert conn.execute("SELECT COUNT(*) FROM case_notes").fetchone()[0] == 260


def test_there_is_no_fraud_label(runtime):
    """The verdict is not in the database. Nothing may quietly start reading one."""
    with db.read_only() as conn:
        for (table,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            columns = {r[1].lower() for r in conn.execute(f"PRAGMA table_info({table})")}
            assert not {"is_fraud", "fraud", "label", "ground_truth"} & columns, (
                f"{table} appears to carry a label")


def test_runtime_writes_go_somewhere_else(runtime):
    """Everything this system produces lands in a different file entirely."""
    runtime.write(
        "INSERT INTO sweep_jobs (job_id, status, total, started_at) "
        "VALUES ('t', 'running', 1, '2026-03-02')")
    assert runtime.fetch("SELECT * FROM sweep_jobs")[0]["job_id"] == "t"
    assert runtime.ACTIONS_DB != db.SOURCE_DB
