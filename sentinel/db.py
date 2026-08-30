"""Two databases, deliberately kept apart.

`ReadOnlyDB` wraps data/sentinel.db. It is opened through a `mode=ro` URI and
every connection sets `PRAGMA query_only`, so an INSERT does not get filtered
out by a pattern match, it raises. The assignment attaches a heavy penalty to a
modified source database; this makes that outcome unreachable rather than
merely unlikely.

`ActionsDB` wraps runtime/actions.db, which is the only file anything in this
system writes to. Dispositions, irreversible actions, approvals, sweep jobs and
the token ledger all live there. Nothing in the codebase opens sentinel.db
writable, and `verify_integrity()` proves it after the fact by comparing a
SHA-256 recorded at setup time.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from sentinel import config

# Second layer of defence for any tool that ever accepts free-form SQL.
# `mode=ro` already makes these impossible; this turns an exception into a
# message the model can act on.
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|attach|detach|replace|create|vacuum|reindex)\b",
    re.I,
)


class ReadOnlyDB:
    """Read-only access to the source database. Cannot write, by construction."""

    def __init__(self, path=None):
        self.path = path or config.DB_PATH
        if not self.path.exists():
            raise FileNotFoundError(
                f"{self.path} is missing. Copy it from the assignment repository "
                f"(data/sentinel.db) before running Sentinel."
            )
        # A POSIX-style URI is required even on Windows; forward slashes only.
        self.uri = f"file:{self.path.as_posix()}?mode=ro"

    def connect(self) -> sqlite3.Connection:
        """Open a read-only connection with dict-like rows."""
        conn = sqlite3.connect(self.uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = 1")
        return conn

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Run a read-only query and return every row."""
        conn = self.connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        """Run a query expected to return at most one row."""
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: tuple = ()):
        """Run a query and return the first column of the first row."""
        row = self.one(sql, params)
        return row[0] if row else None

    def sha256(self) -> str:
        """Hash the database file as it currently stands on disk."""
        digest = hashlib.sha256()
        with open(self.path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def verify_integrity(self) -> tuple[bool, str, str]:
        """Compare the file against the hash recorded at setup.

        Returns (matches, expected, actual). An absent hash file yields an
        empty `expected`, which the caller reports rather than treating as a
        failure.
        """
        actual = self.sha256()
        if not config.DB_SHA256_PATH.exists():
            return False, "", actual
        # Tolerate a stray newline, whitespace or "  filename" suffix from
        # whichever tool wrote the file; take the first 64-hex-char token.
        raw = config.DB_SHA256_PATH.read_text()
        match = re.search(r"[0-9a-fA-F]{64}", raw)
        expected = match.group(0).lower() if match else ""
        return expected == actual, expected, actual


# One shared instance. sqlite3 connections are created per query, so this is
# safe to use from the sweep's worker threads.
db = ReadOnlyDB()


# --------------------------------------------------------------------------
# The writable side
# --------------------------------------------------------------------------
ACTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS dispositions (
    account_id           TEXT PRIMARY KEY,
    verdict              TEXT NOT NULL,
    confidence           TEXT NOT NULL,
    reasoning            TEXT NOT NULL,
    action               TEXT NOT NULL,
    evidence_json        TEXT NOT NULL DEFAULT '[]',
    information_required TEXT NOT NULL DEFAULT '',
    job_id               TEXT,
    decided_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS actions (
    action_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  TEXT NOT NULL,
    action      TEXT NOT NULL,
    reason      TEXT NOT NULL,
    state       TEXT NOT NULL,
    approved_by TEXT,
    at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    total       INTEGER NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS usage (
    usage_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT NOT NULL,
    agent         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    chars_inside  INTEGER NOT NULL DEFAULT 0,
    chars_crossed INTEGER NOT NULL DEFAULT 0,
    at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT NOT NULL,
    specialist    TEXT NOT NULL,
    question      TEXT NOT NULL DEFAULT '',
    finding       TEXT NOT NULL,
    chars_inside  INTEGER NOT NULL DEFAULT 0,
    chars_crossed INTEGER NOT NULL DEFAULT 0,
    at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS policy_loads (
    load_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    agent      TEXT NOT NULL,
    policy     TEXT NOT NULL,
    at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor  TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    at     TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class ActionsDB:
    """The only writable store. Source data is never touched."""

    def __init__(self, path=None):
        self.path = path or config.ACTIONS_DB
        self._ready = False

    def _ensure(self) -> None:
        if self._ready:
            return
        config.ensure_dirs()
        conn = sqlite3.connect(self.path)
        try:
            conn.executescript(ACTIONS_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        self._ready = True

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        """Transactional cursor: commits on success, rolls back on error."""
        self._ensure()
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn.cursor()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        self._ensure()
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def log(self, actor: str, action: str, detail: str) -> None:
        """Append to the audit trail. Every side effect goes through here."""
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (actor, action, detail) VALUES (?, ?, ?)",
                (actor, action, detail),
            )

    def reset(self) -> None:
        """Drop all run state. Used by tests and by `sentinel reset`."""
        if self.path.exists():
            self.path.unlink()
        self._ready = False


actions = ActionsDB()


# --------------------------------------------------------------------------
# The token ledger
# --------------------------------------------------------------------------
# Two numbers matter for the write-up, and they are different things.
#
# **Tokens.** Summed from the model's own `usage_metadata`. Not an estimate:
# the provider's count of what it actually processed.
#
# **The boundary.** How many characters each specialist produced *inside*
# itself, against how many crossed back. The gap between those is the whole
# architectural claim, expressed as a measurement rather than an assertion.
#
# These take primitives only, so this module never imports the agent layer.


def record_usage(
    account_id: str,
    agent: str,
    input_tokens: int,
    output_tokens: int,
    chars_inside: int,
    chars_crossed: int,
) -> None:
    """Append one agent invocation to the ledger. Never fails a case."""
    try:
        with actions.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage (account_id, agent, input_tokens, output_tokens,
                                   chars_inside, chars_crossed)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (account_id, agent, input_tokens, output_tokens, chars_inside, chars_crossed),
            )
    except Exception:
        pass


def usage_totals() -> dict:
    """Everything the ledger knows, aggregated for the write-up."""
    per_agent = [dict(r) for r in actions.query(
        """
        SELECT agent,
               COUNT(*)                          AS invocations,
               SUM(input_tokens)                 AS input_tokens,
               SUM(output_tokens)                AS output_tokens,
               SUM(input_tokens + output_tokens) AS total_tokens,
               SUM(chars_inside)                 AS chars_inside,
               SUM(chars_crossed)                AS chars_crossed
        FROM usage GROUP BY agent ORDER BY total_tokens DESC
        """
    )]
    overall = dict(actions.query(
        """
        SELECT COUNT(DISTINCT account_id) AS accounts,
               COUNT(*)                   AS invocations,
               COALESCE(SUM(input_tokens), 0)  AS input_tokens,
               COALESCE(SUM(output_tokens), 0) AS output_tokens,
               COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
               COALESCE(SUM(chars_inside), 0)  AS chars_inside,
               COALESCE(SUM(chars_crossed), 0) AS chars_crossed
        FROM usage
        """
    )[0])
    inside = overall.get("chars_inside") or 0
    crossed = overall.get("chars_crossed") or 0
    overall["discarded_at_boundary_pct"] = (
        round(100 * (1 - crossed / inside), 1) if inside else None
    )
    return {"per_agent": per_agent, "overall": overall}
