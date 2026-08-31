"""Central configuration.

Everything a reader might want to tweak lives here: which models to use, where
the databases live, and how environment variables get loaded.

Two databases, deliberately:

    data/sentinel.db      the bank's data. Opened READ-ONLY. Never written.
    runtime/actions.db    everything this system produces. Safe to delete.

Keeping them apart is what makes "the source database is never modified" a
property of the code rather than a promise in the README.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

SOURCE_DB = PROJECT_ROOT / "data" / "sentinel.db"      # read-only, never written
RUNTIME_DIR = PROJECT_ROOT / "runtime"                 # gitignored
ACTIONS_DB = RUNTIME_DIR / "actions.db"                # everything we write
CHECKPOINT_DB = RUNTIME_DIR / "checkpoints.db"         # paused human-approval runs

POLICIES_DIR = Path(__file__).resolve().parent / "policies"

RUNTIME_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv(ENV_PATH)

# Two tiers. The specialists run four times per account across 276 accounts, so
# they carry the cheap model. The supervisor and the disposition officer weigh
# conflicting evidence and write the text that gets read, so they carry the
# better one.
SPECIALIST_MODEL = os.getenv("SENTINEL_SPECIALIST_MODEL", "gpt-4.1-mini")
SUPERVISOR_MODEL = os.getenv("SENTINEL_SUPERVISOR_MODEL", "gpt-4.1")

SWEEP_WORKERS = int(os.getenv("SENTINEL_SWEEP_WORKERS", "6"))

# Model calls per second, across the whole process.
#
# The real constraint is tokens per minute, not requests, but requests are what
# a limiter can actually pace. One specialist call costs roughly 5,000 tokens,
# so on a 200,000 TPM account about 0.65 requests per second is the sustainable
# rate. Raise it if your account allows more; the sweep will simply finish
# sooner. Set it too high and workers collide on 429s and lose whole accounts.
REQUESTS_PER_SECOND = float(os.getenv("SENTINEL_REQUESTS_PER_SECOND", "0.65"))

LANGSMITH_ENABLED = os.getenv("LANGSMITH_TRACING", "").lower() == "true"

# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------
# SCHEMA.md: "Today is 2 March 2026. Nothing is dated after it."
#
# The data is fixed in the past, so `date.today()` would put every agent months
# after the events it is reasoning about and every "how many days ago" answer
# would be wrong. One frozen clock, agreed by tools and prompts alike.
NOW = datetime(2026, 3, 2, 9, 0, 0)


def today_str() -> str:
    """The frozen 'now', as agents are told it."""
    return NOW.strftime("%A, %d %B %Y")


def date_context() -> str:
    """One sentence appended to every agent prompt. Agents cannot read a clock."""
    return (
        f"Today is {today_str()} ({NOW.date().isoformat()}). "
        f"The alert queue was generated over the preceding weekend. "
        f"Nothing in the database is dated after today."
    )


def require_openai_key() -> None:
    """Fail loudly and early if the API key is missing."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            f"OPENAI_API_KEY is not set. Add it to {ENV_PATH} and restart the kernel."
        )
