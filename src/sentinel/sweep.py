"""Running cases: one at a time with a human, or all 276 in the background.

Two modes.

**Single case.** `run_case` works one account with the approval gate live. If the
disposition officer reaches for `block_card` or `escalate_case`, the whole run
freezes in the checkpointer and returns `awaiting_approval` with the proposed
action. `resume_case` thaws it, on approval or on rejection.

**Queue sweep.** Three tools, so that starting the work and waiting for it are
separate decisions:

    start_queue_sweep      returns a job id immediately
    check_sweep_status     progress, without blocking
    collect_sweep_results  the verdicts, once they exist

Starting a sweep does three cheap things — one SELECT DISTINCT, one job row, one
Thread.start() — and returns. It does not wait for a single account.

The sweep runs **unattended**: there is no human to approve anything, so
irreversible actions are proposed and queued rather than executed. An
unattended run that could block 276 cards is a worse system than one that
cannot.

Each account gets its own supervisor invocation with its own message list. They
share the database and nothing else.
"""

from __future__ import annotations

import sqlite3
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from sentinel import db, queries
from sentinel.agents import build_system
from sentinel.config import CHECKPOINT_DB, SWEEP_WORKERS


def _checkpointer() -> SqliteSaver:
    """Where a paused run lives while it waits for a person.

    `check_same_thread=False` because the sweep hands connections between
    worker threads; SQLite serialises the writes itself.
    """
    CHECKPOINT_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


TASK = (
    "Work account {account_id}.\n\n"
    "Establish what the alerts are about, whether the behaviour is unusual for "
    "this customer, whether anything on file explains it, and whether the "
    "account is linked to others. Then reach a verdict and record it with the "
    "evidence that decided it."
)


# ===========================================================================
# One case
# ===========================================================================
def run_case(account_id: str, *, auto: bool = False, thread_id: str | None = None,
             task: str | None = None) -> dict:
    """Work a single account end to end.

    Args:
        account_id: The account to investigate, e.g. 'A00985'.
        auto: When True the approval gate is off and irreversible actions are
            queued rather than executed. This is what the sweep uses.
        thread_id: Overrides the checkpoint thread, so the same account can be
            re-run without resuming the previous attempt. An abandoned run
            leaves a checkpoint whose tool calls were never answered, and
            resuming into that is rejected by the API, so anything that may be
            interrupted should pass a fresh id.
        task: Overrides the instruction sent to the supervisor.

    Returns:
        A dict with `status` of either `done` or `awaiting_approval`. When it is
        awaiting approval, `action_requests` describes what the disposition
        officer wants to do and `thread_id` is what `resume_case` needs.
    """
    thread_id = thread_id or f"case-{account_id}-{uuid.uuid4().hex[:8]}"
    supervisor, _ = build_system(
        human_in_the_loop=not auto,
        checkpointer=_checkpointer(),
    )
    config = {"configurable": {"thread_id": thread_id}}

    result = supervisor.invoke(
        {
            "messages": [{"role": "user",
                          "content": (task or TASK).format(account_id=account_id)}],
            "account_id": account_id,
            "unattended": auto,
        },
        config=config,
    )
    return _shape(result, account_id, thread_id)


def resume_case(thread_id: str, *, approve: bool, message: str = "") -> dict:
    """Thaw a paused run with a decision.

    Args:
        thread_id: From the `run_case` result that paused.
        approve: True to let the action run, False to refuse it.
        message: When refusing, why. The disposition officer reads this and is
            expected to record the refusal rather than retry the action.

    A rejection is not a retry. The officer is told the action was refused and
    must proceed without it. A rejection the model works around is not an
    approval gate, it is a speed bump.
    """
    decision = (
        {"type": "approve"} if approve
        else {"type": "reject",
              "message": message or "Refused by the analyst. Do not retry this "
                                    "action. Record the case without it and note "
                                    "that the action was declined."}
    )

    supervisor, _ = build_system(human_in_the_loop=True, checkpointer=_checkpointer())
    config = {"configurable": {"thread_id": thread_id}}
    result = supervisor.invoke(Command(resume={"decisions": [decision]}), config=config)

    account_id = (result.get("account_id")
                  or thread_id.replace("case-", "").split("-")[0])
    return _shape(result, account_id, thread_id)


def _shape(result: dict, account_id: str, thread_id: str) -> dict:
    """Turn a graph result into something a CLI or a notebook can print."""
    interrupts = result.get("__interrupt__") or []
    if interrupts:
        requests = []
        for item in interrupts:
            value = getattr(item, "value", item)
            requests.extend(value if isinstance(value, list) else [value])
        return {
            "status": "awaiting_approval",
            "account_id": account_id,
            "thread_id": thread_id,
            "action_requests": requests,
            "findings": result.get("findings", {}),
        }

    verdict = db.fetch(
        "SELECT verdict, confidence, reasoning, evidence, missing "
        "FROM dispositions WHERE account_id = ?", (account_id,))
    messages = result.get("messages", [])
    return {
        "status": "done",
        "account_id": account_id,
        "thread_id": thread_id,
        "verdict": dict(verdict[0]) if verdict else None,
        "findings": result.get("findings", {}),
        "specialists_consulted": result.get("specialists_consulted", []),
        "summary": messages[-1].text if messages else "",
    }


# ===========================================================================
# The queue sweep: three tools
# ===========================================================================
def start_queue_sweep(limit: int | None = None, workers: int | None = None,
                      skip_done: bool = True) -> str:
    """Start working the whole queue in the background. Returns a job id at once.

    This function does three cheap things and returns: one SELECT DISTINCT for
    the work list, one INSERT for the job row, one Thread.start(). It does not
    wait for a single account, so it comes back in milliseconds while 276
    accounts are still to be worked.

    Args:
        limit: Work only the first N accounts. Use this while developing.
        workers: How many accounts to run concurrently. Each gets its own
            supervisor invocation and its own message list; they share nothing.
        skip_done: Work only accounts with no verdict yet, so a sweep can be
            re-run to pick up whatever the last one dropped. Set False to redo
            the whole queue from scratch.

    Returns:
        The job id, to pass to `check_sweep_status` and `collect_sweep_results`.
    """
    accounts = queries.alerted_accounts()
    if limit:
        accounts = accounts[:limit]

    if skip_done:
        # A sweep over hundreds of accounts will lose some to a rate limit or a
        # transient API error. Re-running the whole queue to recover a handful
        # costs the same as the first run, so by default we work only what has
        # no verdict yet. Pass skip_done=False to redo everything.
        done = {r["account_id"] for r in db.fetch("SELECT account_id FROM dispositions")}
        accounts = [a for a in accounts if a not in done]

    job_id = f"sweep-{uuid.uuid4().hex[:12]}"
    db.write(
        "INSERT INTO sweep_jobs (job_id, status, total, started_at) "
        "VALUES (?, 'running', ?, ?)",
        (job_id, len(accounts), db.now()),
    )

    thread = threading.Thread(
        target=_run_sweep,
        args=(job_id, accounts, workers or SWEEP_WORKERS),
        daemon=True,
        name=job_id,
    )
    thread.start()
    return job_id


def check_sweep_status(job_id: str) -> dict:
    """How far the sweep has got. Never blocks.

    Args:
        job_id: From `start_queue_sweep`.
    """
    rows = db.fetch("SELECT * FROM sweep_jobs WHERE job_id = ?", (job_id,))
    if not rows:
        # `status` is absent only here. Callers test for that rather than for an
        # `error` key, because `sweep_jobs` HAS an error column, so every real
        # job row already contains one — usually None.
        return {"unknown_job": job_id}

    job = dict(rows[0])
    done = job["completed"] + job["failed"]
    job["progress_pct"] = round(100 * done / job["total"], 1) if job["total"] else 0.0
    job["remaining"] = job["total"] - done
    return job


def collect_sweep_results(job_id: str) -> dict:
    """The verdicts the sweep has produced so far.

    Safe to call while the sweep is still running: it returns what exists now.

    Args:
        job_id: From `start_queue_sweep`.
    """
    status = check_sweep_status(job_id)
    if not status.get("status"):
        return status

    verdicts = db.fetch(
        "SELECT verdict, confidence, COUNT(*) n FROM dispositions "
        "GROUP BY verdict, confidence ORDER BY verdict, confidence")
    queued = db.fetch(
        "SELECT action, COUNT(*) n FROM actions WHERE status = 'proposed' "
        "GROUP BY action")

    return {
        "job": status,
        "dispositions": db.fetch(
            "SELECT account_id, verdict, confidence, reasoning, evidence, missing "
            "FROM dispositions ORDER BY account_id"),
        "by_verdict": [dict(r) for r in verdicts],
        "actions_awaiting_approval": [dict(r) for r in queued],
    }


def wait_for_sweep(job_id: str, poll_seconds: float = 3.0,
                   on_progress=None) -> dict:
    """Block until the sweep finishes, and return the collected results.

    The sweep thread is a daemon, so a process that starts a sweep and exits
    immediately takes the work down with it. Anything that needs the results in
    the same process — the CLI without `--detach`, a notebook cell — calls this.

    The three-tool contract is unaffected: `start_queue_sweep` still returns in
    milliseconds, and this is a separate, optional wait. That separation is the
    point of the pattern.

    Args:
        job_id: From `start_queue_sweep`.
        poll_seconds: How often to re-check. Reading the job row is one indexed
            SELECT, so this is cheap.
        on_progress: Optional callback, passed the status dict on each poll.
    """
    import time

    while True:
        status = check_sweep_status(job_id)
        if on_progress:
            on_progress(status)
        if not status.get("status"):
            return status                      # no such job
        if status["status"] in ("done", "failed"):
            return collect_sweep_results(job_id)
        time.sleep(poll_seconds)


def _run_sweep(job_id: str, accounts: list[str], workers: int) -> None:
    """The background worker. Each account is an isolated supervisor run."""

    def work(account_id: str) -> None:
        try:
            run_case(account_id, auto=True, thread_id=f"{job_id}-{account_id}")
            db.write(
                "UPDATE sweep_jobs SET completed = completed + 1 WHERE job_id = ?",
                (job_id,))
        except Exception:
            db.write(
                "UPDATE sweep_jobs SET failed = failed + 1 WHERE job_id = ?",
                (job_id,))
            db.write(
                "INSERT INTO findings (account_id, specialist, finding, recorded_at) "
                "VALUES (?, 'error', ?, ?)",
                (account_id, traceback.format_exc()[-2000:], db.now()))

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, accounts))
        db.write(
            "UPDATE sweep_jobs SET status = 'done', finished_at = ? WHERE job_id = ?",
            (db.now(), job_id))
    except Exception as exc:
        db.write(
            "UPDATE sweep_jobs SET status = 'failed', error = ?, finished_at = ? "
            "WHERE job_id = ?", (str(exc)[:500], db.now(), job_id))
