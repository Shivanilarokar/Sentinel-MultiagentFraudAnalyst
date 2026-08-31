
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from collections.abc import Generator

from sentinel.config import ACTIONS_DB, SOURCE_DB


# ===========================================================================
# The source database - read only
# ===========================================================================
@contextmanager
def read_only() -> Generator[sqlite3.Connection]:
    """Open `data/sentinel.db` in a mode that physically cannot write.

    `mode=ro` refuses at the file level; `query_only` refuses at the statement
    level. Either alone would do. Both are cheap.
    """
    conn = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
    """Run one SELECT against the source database and return all rows."""
    with read_only() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
    """Run one SELECT and return the first row, or None."""
    rows = query(sql, params)
    return rows[0] if rows else None


def source_hash() -> str:
    """SHA-256 of the source database, so `doctor` can prove it is untouched."""
    digest = hashlib.sha256()
    with open(SOURCE_DB, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ===========================================================================
# The runtime database - everything we write
# ===========================================================================
RUNTIME_SCHEMA = """
-- One row per account we reached a verdict on.
CREATE TABLE IF NOT EXISTS dispositions (
    account_id   TEXT PRIMARY KEY,
    verdict      TEXT NOT NULL,      -- fraud | legitimate | insufficient_evidence
    confidence   TEXT NOT NULL,      -- high | medium | low
    reasoning    TEXT NOT NULL,
    evidence     TEXT NOT NULL,      -- JSON list of {kind, id, quote}
    missing      TEXT,               -- what would resolve it, when insufficient
    decided_at   TEXT NOT NULL
);

-- One row per irreversible action. Queued during a sweep, executed only
-- after a human approves.
CREATE TABLE IF NOT EXISTS actions (
    action_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT NOT NULL,
    action       TEXT NOT NULL,      -- block_card | escalate_case
    target       TEXT,               -- the card id / case reference
    reason       TEXT NOT NULL,
    status       TEXT NOT NULL,      -- proposed | approved | rejected
    approved_by  TEXT,
    created_at   TEXT NOT NULL
);

-- The background queue sweep.
CREATE TABLE IF NOT EXISTS sweep_jobs (
    job_id       TEXT PRIMARY KEY,
    status       TEXT NOT NULL,      -- running | done | failed
    total        INTEGER NOT NULL,
    completed    INTEGER NOT NULL DEFAULT 0,
    failed       INTEGER NOT NULL DEFAULT 0,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    error        TEXT
);

-- Measured token cost, for WRITEUP.md. One row per model call.
CREATE TABLE IF NOT EXISTS token_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT,
    agent         TEXT NOT NULL,     -- which specialist, or the supervisor
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    recorded_at   TEXT NOT NULL
);

-- Proof that policy loading is on demand: one row every time an agent asks.
CREATE TABLE IF NOT EXISTS policy_loads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT,
    agent        TEXT,
    policy       TEXT NOT NULL,
    loaded_at    TEXT NOT NULL
);

-- Each specialist's finding, kept out of the supervisor's message list but
-- available to the report writer.
CREATE TABLE IF NOT EXISTS findings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT NOT NULL,
    specialist   TEXT NOT NULL,
    finding      TEXT NOT NULL,
    recorded_at  TEXT NOT NULL
);
"""


@contextmanager
def actions_db() -> Generator[sqlite3.Connection]:
    """Open the runtime database for reading and writing."""
    conn = sqlite3.connect(ACTIONS_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")   # sweep workers write concurrently
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_runtime() -> None:
    """Create the runtime tables. Safe to call repeatedly."""
    with actions_db() as conn:
        conn.executescript(RUNTIME_SCHEMA)


def write(sql: str, params: tuple | dict = ()) -> int:
    """Run one INSERT/UPDATE against the runtime database, return lastrowid."""
    with actions_db() as conn:
        return conn.execute(sql, params).lastrowid


def fetch(sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
    """Run one SELECT against the runtime database."""
    with actions_db() as conn:
        return conn.execute(sql, params).fetchall()


def reset_runtime() -> None:
    """Drop every runtime table and rebuild. Never touches data/sentinel.db."""
    with actions_db() as conn:
        for table in ("dispositions", "actions", "sweep_jobs",
                      "token_ledger", "policy_loads", "findings"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
    init_runtime()


def rows_to_json(rows: list[sqlite3.Row]) -> str:
    """Small helper for tools that hand a model structured text."""
    return json.dumps([dict(r) for r in rows], default=str, indent=2)


if __name__ == "__main__":
    import sys

    if "--reset" in sys.argv:
        reset_runtime()
        print(f"runtime reset : {ACTIONS_DB}")
    else:
        init_runtime()
        print(f"runtime ready : {ACTIONS_DB}")

    with read_only() as conn:
        alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        accounts = conn.execute(
            "SELECT COUNT(DISTINCT account_id) FROM alerts").fetchone()[0]
        txns = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    print(f"source db     : {alerts} alerts on {accounts} accounts, {txns:,} transactions")
    print(f"sha256        : {source_hash()[:16]}...")

    # Prove the read-only guarantee rather than asserting it in a comment.
    try:
        with read_only() as conn:
            conn.execute("INSERT INTO alerts (alert_id) VALUES ('X')")
        print("read-only     : FAILED - the source database accepted a write")
    except sqlite3.OperationalError as exc:
        print(f"read-only     : enforced ({exc})")
