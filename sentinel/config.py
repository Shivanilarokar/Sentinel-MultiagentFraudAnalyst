"""Paths, model selection and environment.

One module owns every piece of configuration, so a reader can answer "which
model runs the specialists?" or "where do writes go?" without grepping.

Two rules encoded here are load-bearing for the rest of the system:

    DB_PATH        is only ever opened read-only (see db.ReadOnlyDB)
    ACTIONS_DB     is the only database anything is allowed to write to

Keeping those on separate paths is what makes "do not modify data/sentinel.db"
a property of the architecture rather than a promise in a README.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "sentinel.db"            # read-only, never written
DB_SHA256_PATH = DATA_DIR / "sentinel.db.sha256"

RUNTIME_DIR = PROJECT_ROOT / "runtime"        # everything we write lives here
ACTIONS_DB = RUNTIME_DIR / "actions.db"       # dispositions, actions, jobs, usage
CHECKPOINT_DB = RUNTIME_DIR / "checkpoints.db"  # LangGraph HITL state

POLICY_DIR = Path(__file__).resolve().parent / "policies"

# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------
load_dotenv(ENV_PATH)


def _first_env(*names: str) -> str | None:
    """Return the first environment variable that is actually set.

    The checked-in .env for this project spells the keys OPEN_AI_API_KEY and
    Langsmith_api_key. The SDKs look for OPENAI_API_KEY and LANGSMITH_API_KEY.
    Rather than ask anyone to rewrite their secrets file, we accept both and
    normalise below.
    """
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _normalise_env() -> None:
    """Copy tolerated key spellings onto the names the SDKs read."""
    if key := _first_env("OPENAI_API_KEY", "OPEN_AI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = key
    if key := _first_env("LANGSMITH_API_KEY", "Langsmith_api_key", "LANGCHAIN_API_KEY"):
        os.environ["LANGSMITH_API_KEY"] = key


_normalise_env()

# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
# The specialists run once per account per domain - roughly 1,100 invocations
# across a full sweep - and the supervisor and disposition officer add two
# more. Both default to gpt-4.1-mini.
#
# A word on why, because the obvious choice is a stronger model for the two
# agents that do the weighing. Measured on this account's key: gpt-4.1 is
# capped at 30,000 tokens per minute, while gpt-4.1-mini has 200,000. One case
# costs roughly 22,000 tokens through the disposition officer alone, so a
# two-tier configuration cannot sustain a 276-account sweep - it rate-limits
# after the first case and takes hours. The tier is still available for a
# single deep-dive: `sentinel case A00985 --supervisor-model gpt-4.1`.
SPECIALIST_MODEL = os.getenv("SENTINEL_SPECIALIST_MODEL", "gpt-4.1-mini")
SUPERVISOR_MODEL = os.getenv("SENTINEL_SUPERVISOR_MODEL", "gpt-4.1-mini")

# Transient 429s are normal at any concurrency worth using. Retry with the
# SDK's exponential backoff rather than failing an account.
MODEL_MAX_RETRIES = int(os.getenv("SENTINEL_MODEL_MAX_RETRIES", "12"))

# Requests per second across the whole process, shared by every agent. Set to
# 0 to disable.
#
# Note what this does and does not solve. The provider's binding constraint
# is tokens per minute, not requests per second, and a request's token cost
# is not known until it is made. So this limiter smooths the burst rate, the
# SDK's backoff absorbs the rest, and `run_case` retries a whole account if
# it still loses. Measured: gpt-4.1-mini allows 200,000 TPM on this key, and
# a single account costs 20,000-60,000 tokens, so three concurrent accounts
# is the honest ceiling.
REQUESTS_PER_SECOND = float(os.getenv("SENTINEL_REQUESTS_PER_SECOND", "3"))

# --------------------------------------------------------------------------
# Sweep
# --------------------------------------------------------------------------
SWEEP_WORKERS = int(os.getenv("SENTINEL_SWEEP_WORKERS", "3"))

# --------------------------------------------------------------------------
# Observability
# --------------------------------------------------------------------------
# Opt-in, so the repository runs for anyone holding only an OpenAI key.
LANGSMITH_ENABLED = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
if LANGSMITH_ENABLED:
    os.environ.setdefault("LANGSMITH_PROJECT", "sentinel-fraud-triage")

# --------------------------------------------------------------------------
# The clock
# --------------------------------------------------------------------------
# The dataset is frozen: nothing is dated after 2 March 2026 and the queue was
# generated over the preceding weekend. Agents cannot read a clock, and a real
# one would be wrong here anyway, so "now" is pinned to the dataset.
TODAY = "2026-03-02"


def date_context() -> str:
    """Ground every agent in the same 'now'. Appended to each system prompt."""
    return (
        f"Today is Monday, {TODAY}. The alert queue was generated over the "
        f"preceding weekend (27 Feb - 1 Mar 2026). Transaction history runs "
        f"from 2 Nov 2025 to 2 Mar 2026. Nothing in the database is dated "
        f"after today, so treat any date you read as being in the past."
    )


def require_openai_key() -> None:
    """Fail loudly and early if the API key is missing."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            f"OPENAI_API_KEY is not set. Add it to {ENV_PATH} "
            f"(OPEN_AI_API_KEY is also accepted) and re-run."
        )


def ensure_dirs() -> None:
    """Create the writable directory. Never touches DATA_DIR."""
    RUNTIME_DIR.mkdir(exist_ok=True)
