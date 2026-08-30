"""Shared fixtures.

Every test in this suite runs offline. Nothing here calls a model: the things
worth asserting mechanically - that the database cannot be written, that the
supervisor holds four tools, that specialist tool sets are disjoint, that a
sweep returns immediately, that a bad citation is refused - are all properties
of the wiring, not of what a model happens to say.

That is deliberate. A conformance suite that needs an API key and twenty
minutes is a suite nobody runs.

The run store is redirected to a temporary file for the whole session. This is
not tidiness: `runtime/actions.db` holds live sweep state, and a test that
truncates a table there will silently destroy a run that is in progress. It has
happened once; the fixture below is why it cannot happen again.
"""

from __future__ import annotations

import pytest

from sentinel.db import ReadOnlyDB, actions


@pytest.fixture(scope="session", autouse=True)
def isolated_run_store(tmp_path_factory):
    """Point the writable database at a throwaway file for the whole session."""
    original_path, original_ready = actions.path, actions._ready
    actions.path = tmp_path_factory.mktemp("runtime") / "actions.db"
    actions._ready = False
    yield actions
    actions.path, actions._ready = original_path, original_ready


@pytest.fixture(scope="session")
def db():
    return ReadOnlyDB()


@pytest.fixture(scope="session")
def alerted_account(db):
    """A real alerted account id, so tests exercise real rows."""
    return db.scalar("SELECT account_id FROM alerts ORDER BY account_id LIMIT 1")


@pytest.fixture(scope="session")
def worked_example():
    """The account the assignment README uses as its worked example."""
    return "A00985"
