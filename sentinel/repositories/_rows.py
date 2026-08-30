"""Row helpers shared by every repository."""

from __future__ import annotations

import sqlite3


def rows(result: list[sqlite3.Row]) -> list[dict]:
    """sqlite3.Row is not JSON-serialisable. Every repository returns dicts."""
    return [dict(row) for row in result]


def row(result: sqlite3.Row | None) -> dict | None:
    return dict(result) if result is not None else None
