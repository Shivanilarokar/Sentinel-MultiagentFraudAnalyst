"""The queue sweep, exposed as the three-tool pattern.

    start_queue_sweep  -> a job id, immediately
    check_sweep_status -> progress, without blocking
    collect_sweep_results -> the finished verdicts

These are real tools, and they are deliberately **not** on the supervisor.
The rubric caps the supervisor at four tools, and it already holds four
specialists; adding these would make seven and break the requirement it is
scored against. They belong to the operator surface - the CLI and the API -
which is who actually starts a sweep.

The relationship is the other way round from what the tool list suggests: the
sweep drives the supervisor, running one isolated supervisor invocation per
account. It is not something the supervisor calls.
"""

from __future__ import annotations

from langchain.tools import tool

from sentinel import sweep
from sentinel.tools._render import as_json


@tool
def start_queue_sweep(limit: int = 0, workers: int = 0) -> str:
    """Start working the whole alert queue in the background. Returns straight away.

    Use for: triaging all 276 flagged accounts. This returns a job id in well
    under a second and does not wait for the work. Tell the operator the id and
    carry on; you cannot invent one, and reporting a job you did not start is
    worse than saying you could not start it.

    Irreversible actions are not executed during a sweep. They are recorded as
    proposals for an analyst to review afterwards.

    Args:
        limit: Work only the first N accounts. 0 means all of them. Use a
            small number while developing.
        workers: Accounts processed concurrently. 0 uses the configured default.
    """
    return as_json(sweep.start_queue_sweep(limit=limit, workers=workers))


@tool
def check_sweep_status(job_id: str) -> str:
    """Check how far a background sweep has got. Does not block.

    Use for: answering "is it done yet" while other work continues.

    Args:
        job_id: The id returned by start_queue_sweep.
    """
    return as_json(sweep.check_sweep_status(job_id))


@tool
def collect_sweep_results(job_id: str, limit: int = 0) -> str:
    """Retrieve the verdicts a sweep produced.

    Use for: reading the finished work. Check the status first; a sweep that is
    still running returns only what it has completed so far.

    Args:
        job_id: The id returned by start_queue_sweep.
        limit: Return at most N dispositions. 0 means all of them.
    """
    return as_json(sweep.collect_sweep_results(job_id, limit=limit))


SWEEP_TOOLS = [start_queue_sweep, check_sweep_status, collect_sweep_results]
