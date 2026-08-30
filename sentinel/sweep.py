"""The asynchronous queue sweep: three tools, one background pool.

    start_queue_sweep     kicks the job off, returns a job id immediately
    check_sweep_status    progress, without blocking
    collect_sweep_results the finished verdicts

`start_queue_sweep` does exactly three cheap things - one
`SELECT DISTINCT account_id FROM alerts`, one row in the jobs table, one
`Thread.start()` - and returns. It is sub-second by construction, not by luck,
and `tests/test_sweep.py` asserts it.

Two decisions worth stating:

**Threads are not daemons.** A daemon worker dies the instant the launching
process exits, which makes `sentinel sweep` from a CLI a sweep that can never
finish. These are ordinary threads, and the CLI keeps the process alive.

**Irreversible actions are deferred, never executed.** A 276-account run has no
human present, so `block_card` and `escalate_case` are recorded as proposals
for an analyst to work through afterwards. An unattended run that could block
cards is a worse system than one that cannot, whatever its verdicts look like.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from uuid import uuid4

from sentinel.config import SWEEP_WORKERS
from sentinel.db import actions
from sentinel.repositories import alerts_repo

# Live job handles, so status can be answered without touching the database.
# The jobs table is the durable record; this dict is the fast path.
JOBS: dict[str, Future] = {}
_THREADS: dict[str, threading.Thread] = {}


def _new_job(total: int) -> str:
    job_id = f"job_{uuid4().hex[:8]}"
    with actions.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (job_id, status, total) VALUES (?, 'running', ?)",
            (job_id, total),
        )
    return job_id


def _bump(job_id: str, *, ok: bool) -> None:
    column = "completed" if ok else "failed"
    with actions.cursor() as cur:
        cur.execute(f"UPDATE jobs SET {column} = {column} + 1 WHERE job_id = ?", (job_id,))


def _finish(job_id: str, status: str) -> None:
    with actions.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = ?, finished_at = datetime('now') WHERE job_id = ?",
            (status, job_id),
        )


def _work_queue(job_id: str, account_ids: list[str], workers: int) -> None:
    """The background body. Each account gets its own isolated supervisor run."""
    from sentinel.case import run_case  # imported here to keep start-up cheap

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    run_case,
                    account_id,
                    human_in_the_loop=False,
                    approval_mode="defer",
                    run=job_id,
                ): account_id
                for account_id in account_ids
            }
            for future in as_completed(futures):
                account_id = futures[future]
                try:
                    result = future.result()
                    ok = result.status != "failed"
                    if not ok:
                        actions.log("sweep", "account_failed", f"{account_id}: {result.error}")
                    with actions.cursor() as cur:
                        cur.execute(
                            "UPDATE dispositions SET job_id = ? WHERE account_id = ?",
                            (job_id, account_id),
                        )
                except Exception as exc:
                    ok = False
                    actions.log("sweep", "account_failed", f"{account_id}: {exc}")
                _bump(job_id, ok=ok)
        _finish(job_id, "completed")
        actions.log("sweep", "completed", f"{job_id}: {len(account_ids)} accounts")
    except Exception as exc:
        # Without this the job would sit at 'running' forever after a top-level
        # failure, which is worse than a clear failure.
        _finish(job_id, "failed")
        actions.log("sweep", "job_failed", f"{job_id}: {exc}")


def start_queue_sweep(limit: int = 0, workers: int = 0) -> dict:
    """Start working the whole alert queue in the background. Returns immediately.

    Args:
        limit: Work only the first N accounts. 0 means all 276. Use a small
            number while developing.
        workers: Accounts processed concurrently. 0 uses the configured default.
    """
    account_ids = alerts_repo.queue()
    if limit:
        account_ids = account_ids[:limit]

    job_id = _new_job(len(account_ids))
    thread = threading.Thread(
        target=_work_queue,
        args=(job_id, account_ids, workers or SWEEP_WORKERS),
        name=f"sweep-{job_id}",
        daemon=False,
    )
    _THREADS[job_id] = thread
    thread.start()

    actions.log("sweep", "started", f"{job_id}: {len(account_ids)} accounts")
    return {"job_id": job_id, "accounts": len(account_ids), "status": "running"}


def check_sweep_status(job_id: str) -> dict:
    """Progress on a sweep, without blocking.

    Args:
        job_id: The id returned by start_queue_sweep.
    """
    rows = actions.query("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    if not rows:
        return {"error": f"No job {job_id}."}
    job = dict(rows[0])
    done = (job["completed"] or 0) + (job["failed"] or 0)
    job["progress"] = f"{done}/{job['total']}"
    job["pct"] = round(100 * done / job["total"], 1) if job["total"] else 0.0
    return job


def collect_sweep_results(job_id: str, limit: int = 0) -> dict:
    """The verdicts a sweep produced.

    Args:
        job_id: The id returned by start_queue_sweep.
        limit: Return at most N dispositions. 0 means all of them.
    """
    status = check_sweep_status(job_id)
    if "error" in status:
        return status

    sql = "SELECT * FROM dispositions WHERE job_id = ? ORDER BY account_id"
    params: tuple = (job_id,)
    if limit:
        sql += " LIMIT ?"
        params = (job_id, limit)

    dispositions = [dict(r) for r in actions.query(sql, params)]
    breakdown = {
        r["verdict"]: r["n"]
        for r in [
            dict(x)
            for x in actions.query(
                "SELECT verdict, COUNT(*) n FROM dispositions WHERE job_id = ? GROUP BY verdict",
                (job_id,),
            )
        ]
    }
    return {"job": status, "verdicts": breakdown, "dispositions": dispositions}


def wait_for(job_id: str, timeout: float | None = None, poll: float = 2.0) -> dict:
    """Block until a sweep finishes. For the CLI, never for an agent."""
    started = time.time()
    thread = _THREADS.get(job_id)
    if thread:
        thread.join(timeout)
    else:
        while True:
            status = check_sweep_status(job_id)
            if status.get("status") in ("completed", "failed"):
                break
            if timeout and time.time() - started > timeout:
                break
            time.sleep(poll)
    return check_sweep_status(job_id)


def recent_jobs(limit: int = 10) -> list[dict]:
    return [
        dict(r)
        for r in actions.query(
            "SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?", (limit,)
        )
    ]


def pending_actions() -> list[dict]:
    """Irreversible actions a sweep proposed and queued for an analyst."""
    return [
        dict(r)
        for r in actions.query(
            "SELECT * FROM actions WHERE state = 'pending_review' ORDER BY at DESC"
        )
    ]
