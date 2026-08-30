"""HTTP surface, mirroring the CLI.

    POST /cases/{account_id}            work one account
    POST /cases/{account_id}/resume     approve or reject a paused run
    POST /sweep                         start the queue sweep, returns immediately
    GET  /sweep/{job_id}                progress
    GET  /sweep/{job_id}/results        the verdicts
    GET  /dispositions                  every recorded verdict
    GET  /approvals                     irreversible actions queued for review
    GET  /analysis/evidence             citation audit
    GET  /analysis/lookalikes           matched pairs called differently
    GET  /analysis/tokens               measured cost and the single-agent comparison

`POST /sweep` exists mainly so the asynchronous requirement can be checked from
outside the process:

    curl -w '%{time_total}s\\n' -XPOST localhost:8000/sweep

Every handler is a plain `def`, not `async def`. FastAPI runs those in a
threadpool, which is what we want: the agent stack is synchronous, and
declaring these `async` would block the event loop for the whole of a case.
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException

from sentinel import sweep as sweep_module
from sentinel import usage
from sentinel.analysis import evidence_check, lookalikes, token_model
from sentinel.case import describe_interrupt, resume_case, run_case
from sentinel.db import actions, db

app = FastAPI(
    title="Sentinel",
    description="Multi-agent fraud triage for the Sentinel Bank alert queue.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    """Environment and database integrity."""
    matches, expected, actual = db.verify_integrity()
    return {
        "status": "ok",
        "alerted_accounts": db.scalar("SELECT COUNT(DISTINCT account_id) FROM alerts"),
        "source_db_unchanged": matches,
        "source_db_sha256": actual,
    }


# --------------------------------------------------------------------------
# Single case
# --------------------------------------------------------------------------
def _case_payload(result) -> dict:
    disposition = result.disposition
    return {
        "account_id": result.account_id,
        "status": result.status,
        "summary": result.summary,
        "elapsed_seconds": round(result.elapsed_seconds, 2),
        "error": result.error or None,
        "awaiting_approval": [describe_interrupt(i) for i in result.interrupts],
        "findings": result.findings,
        "disposition": disposition.model_dump() if disposition else None,
    }


@app.post("/cases/{account_id}")
def work_case(account_id: str, approve_interactively: bool = True) -> dict:
    """Work one account.

    With `approve_interactively`, the run pauses before any irreversible action
    and returns `awaiting_approval` with the interrupt id and the exact
    arguments. Resume it at `/cases/{account_id}/resume`.
    """
    return _case_payload(run_case(account_id, human_in_the_loop=approve_interactively))


@app.post("/cases/{account_id}/resume")
def resume(account_id: str, decisions: dict[str, Any] = Body(...)) -> dict:
    """Resume a paused run.

    Body maps interrupt id to a decision, e.g.

        {"<interrupt_id>": {"decisions": [{"type": "approve"}]}}
        {"<interrupt_id>": {"decisions": [{"type": "reject", "message": "why"}]}}
    """
    return _case_payload(resume_case(account_id, decisions))


# --------------------------------------------------------------------------
# Queue sweep
# --------------------------------------------------------------------------
@app.post("/sweep")
def start_sweep(limit: int = 0, workers: int = 0) -> dict:
    """Start the queue sweep. Returns a job id immediately."""
    return sweep_module.start_queue_sweep(limit=limit, workers=workers)


@app.get("/sweep/{job_id}")
def sweep_status(job_id: str) -> dict:
    """Progress. Does not block."""
    status = sweep_module.check_sweep_status(job_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status


@app.get("/sweep/{job_id}/results")
def sweep_results(job_id: str, limit: int = 0) -> dict:
    """The verdicts a sweep produced."""
    results = sweep_module.collect_sweep_results(job_id, limit=limit)
    if "error" in results:
        raise HTTPException(status_code=404, detail=results["error"])
    return results


@app.get("/sweep")
def sweep_jobs() -> list[dict]:
    """Recent sweeps."""
    return sweep_module.recent_jobs()


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@app.get("/dispositions")
def dispositions(verdict: str | None = None) -> list[dict]:
    """Every recorded verdict, optionally filtered."""
    if verdict:
        rows = actions.query(
            "SELECT * FROM dispositions WHERE verdict = ? ORDER BY account_id", (verdict,)
        )
    else:
        rows = actions.query("SELECT * FROM dispositions ORDER BY account_id")
    return [dict(r) for r in rows]


@app.get("/dispositions/{account_id}")
def disposition(account_id: str) -> dict:
    rows = actions.query("SELECT * FROM dispositions WHERE account_id = ?", (account_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"No disposition for {account_id}.")
    return dict(rows[0])


@app.get("/approvals")
def approvals() -> list[dict]:
    """Irreversible actions a sweep proposed and queued for an analyst."""
    return sweep_module.pending_actions()


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
@app.get("/analysis/evidence")
def analysis_evidence() -> dict:
    """Every citation, re-checked against the database."""
    return evidence_check.audit_all()


@app.get("/analysis/lookalikes")
def analysis_lookalikes() -> dict:
    """Accounts with identical signatures, and where our verdicts diverge."""
    return {"summary": lookalikes.summary(), "pairs": lookalikes.separated_pairs()}


@app.get("/analysis/tokens")
def analysis_tokens() -> dict:
    """Measured cost, and the single-agent comparison."""
    return {"measured": usage.totals(), "single_agent_estimate": token_model.single_agent_estimate()}
