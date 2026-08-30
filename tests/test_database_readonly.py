"""The source database is never modified.

The assignment deducts 20 points for a modified `data/sentinel.db`. These tests
assert that the outcome is unreachable by mechanism rather than by discipline:
the connection is opened read-only, the pragma is set, writes raise, and the
file's hash is unchanged after the whole suite has run.
"""

from __future__ import annotations

import sqlite3

import pytest

from sentinel import config
from sentinel.db import ACTIONS_SCHEMA, ReadOnlyDB


def test_connection_is_opened_read_only(db):
    assert "mode=ro" in db.uri


def test_query_only_pragma_is_set(db):
    assert db.connect().execute("PRAGMA query_only").fetchone()[0] == 1


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO alerts (alert_id) VALUES ('X')",
        "UPDATE transactions SET amount = 0",
        "DELETE FROM case_notes",
        "DROP TABLE alerts",
        "CREATE TABLE scratch (a TEXT)",
    ],
)
def test_writes_raise(db, statement):
    """Not filtered by a pattern - refused by SQLite itself."""
    with pytest.raises(sqlite3.OperationalError):
        db.connect().execute(statement)


def test_hash_matches_the_recorded_value(db):
    matches, expected, actual = db.verify_integrity()
    assert expected, "data/sentinel.db.sha256 is missing; run setup"
    assert matches, f"the source database has changed: expected {expected}, got {actual}"


def test_reads_still_work(db):
    assert db.scalar("SELECT COUNT(DISTINCT account_id) FROM alerts") == 276
    assert db.scalar("SELECT COUNT(*) FROM transactions") == 108_249


def test_nothing_writable_points_at_the_source_database():
    """The run store is a different file, and its schema never touches source tables."""
    assert config.ACTIONS_DB != config.DB_PATH
    assert config.ACTIONS_DB.parent == config.RUNTIME_DIR
    source_tables = {
        "alerts", "transactions", "case_notes", "disputes", "prior_cases",
        "customers", "accounts", "cards", "devices", "customer_devices",
        "merchants", "rules",
    }
    created = {
        line.split("IF NOT EXISTS")[1].split("(")[0].strip()
        for line in ACTIONS_SCHEMA.splitlines()
        if "CREATE TABLE IF NOT EXISTS" in line
    }
    assert not (created & source_tables), f"run store shadows source tables: {created & source_tables}"


def test_read_only_db_reports_a_missing_file_clearly(tmp_path):
    with pytest.raises(FileNotFoundError):
        ReadOnlyDB(tmp_path / "nope.db")
