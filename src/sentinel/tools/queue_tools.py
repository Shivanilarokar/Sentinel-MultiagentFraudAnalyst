"""Queue tools: start the sweep, check on it, collect what it produced.

Three tools rather than one blocking call, so that *starting* the work and
*waiting* for it are separate decisions. `start_queue_sweep` does one
`SELECT DISTINCT`, one job row and one `Thread.start()`, then returns — which
means the supervisor can answer other questions while 276 accounts are still
being worked.

These sit on the supervisor, alongside the four specialists. One consequence has
to be handled explicitly: a sweep works each account through a supervisor of its
own, so a supervisor that is already inside a sweep must not be able to start
another. Each tool checks `unattended` and refuses. Without that guard the first
sweep would fork a second, and so on.

The import of `sentinel.sweep` is deliberately inside the function bodies.
`sweep` imports `agents`, `agents` imports these tools, and at module scope that
is a cycle.
"""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool

REFUSAL = (
    "REFUSED: you are already working one account inside a queue sweep. Starting "
    "another sweep from here would fork a second pass over the whole queue, and "
    "then a third. Finish this account and report your verdict."
)


@tool
def start_queue_sweep(runtime: ToolRuntime, limit: int = 0) -> str:
    """Begin working the whole alert queue in the background. Returns a job id.

    Returns immediately — it does not wait for a single account. Use
    `check_sweep_status` to follow progress and `collect_sweep_results` to read
    the verdicts.

    Args:
        limit: Work only the first N accounts. 0 means the whole queue.
    """
    if runtime.state.get("unattended"):
        return REFUSAL

    from sentinel.sweep import start_queue_sweep as start

    job_id = start(limit=limit or None)
    return (
        f"Sweep started. Job id: {job_id}\n"
        f"It is running in the background; nothing is blocked. Call "
        f"check_sweep_status('{job_id}') for progress."
    )


@tool
def check_sweep_status(job_id: str, runtime: ToolRuntime) -> str:
    """How far a running sweep has got. Never blocks.

    Args:
        job_id: From `start_queue_sweep`.
    """
    if runtime.state.get("unattended"):
        return REFUSAL

    from sentinel.sweep import check_sweep_status as status

    job = status(job_id)
    if not job.get("status"):
        return f"No such job: {job_id}"
    return (
        f"Job {job_id}: {job['status']}\n"
        f"  {job['completed']} done, {job['failed']} failed, "
        f"{job['remaining']} remaining of {job['total']} ({job['progress_pct']}%)\n"
        f"  started {job['started_at']}"
        + (f", finished {job['finished_at']}" if job.get("finished_at") else "")
    )


@tool
def collect_sweep_results(job_id: str, runtime: ToolRuntime) -> str:
    """The verdicts a sweep has produced so far. Safe to call while it runs.

    Args:
        job_id: From `start_queue_sweep`.
    """
    if runtime.state.get("unattended"):
        return REFUSAL

    from sentinel.sweep import collect_sweep_results as collect

    results = collect(job_id)
    if not results.get("dispositions"):
        return f"No verdicts recorded yet for {job_id}."

    lines = [f"{len(results['dispositions'])} account(s) disposed:"]
    lines += [f"  {r['verdict']:<22} {r['confidence']:<7} {r['n']}"
              for r in results["by_verdict"]]
    if results["actions_awaiting_approval"]:
        lines.append("\nIrreversible actions proposed and waiting for a person:")
        lines += [f"  {r['action']}: {r['n']}"
                  for r in results["actions_awaiting_approval"]]
    return "\n".join(lines)


# Not a specialist domain, so deliberately not in TOOLSETS: these do not read the
# bank's data, they schedule work.
QUEUE_TOOLS = [start_queue_sweep, check_sweep_status, collect_sweep_results]
