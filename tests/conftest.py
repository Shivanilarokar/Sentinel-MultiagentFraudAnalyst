"""Shared fixtures.

Every test here runs offline. None of them needs an API key, because the things
worth asserting — that the source database refuses writes, that the toolsets are
disjoint, that a citation is checked against a real row — are all properties of
the code rather than of any model's output.

A test suite that needs a network call to run is a test suite nobody runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def source_sha() -> str:
    """The hash of data/sentinel.db before any test touches anything."""
    from sentinel.db import source_hash
    return source_hash()


@pytest.fixture(scope="session", autouse=True)
def database_is_never_modified(source_sha):
    """Fail the whole run if the source database changed while tests ran.

    This is the one guarantee worth checking twice: once by the read-only
    connection, and once by comparing the file against itself afterwards.
    """
    yield
    from sentinel.db import source_hash
    assert source_hash() == source_sha, "data/sentinel.db was modified during the test run"


@pytest.fixture(scope="session")
def alerted() -> list[str]:
    from sentinel.queries import alerted_accounts
    return alerted_accounts()


@pytest.fixture()
def runtime(tmp_path, monkeypatch):
    """A throwaway runtime database, so tests never touch a real run's results."""
    import sentinel.config as config
    import sentinel.db as db

    monkeypatch.setattr(config, "ACTIONS_DB", tmp_path / "actions.db")
    monkeypatch.setattr(db, "ACTIONS_DB", tmp_path / "actions.db")
    db.init_runtime()
    return db
