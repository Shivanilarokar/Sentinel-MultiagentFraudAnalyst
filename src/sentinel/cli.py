"""The operator surface.

    sentinel doctor                    environment, database integrity, tool isolation
    sentinel case A00985               one account, with the approval gate live
    sentinel case A00985 --auto        skip approvals, queue irreversible actions
    sentinel sweep                     all 276, live progress
    sentinel sweep --limit 20          a subset, while developing
    sentinel sweep --detach            return the job id and exit
    sentinel status <job_id>           progress, without blocking
    sentinel collect <job_id>          the verdicts so far
    sentinel approvals                 irreversible actions waiting for sign-off
    sentinel policies                  the progressive-disclosure report
    sentinel analyse                   tokens, isolation, the single-agent model
    sentinel report                    regenerate the four deliverables
    sentinel reset                     drop run state; never touches data/sentinel.db
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from sentinel import agents, analysis, db, doctor, middleware, reports, sweep

app = typer.Typer(add_completion=False, help="Multi-agent fraud triage for the Sentinel Bank queue.")
console = Console()

VERDICT_STYLE = {
    "fraud": "bold red",
    "legitimate": "green",
    "insufficient_evidence": "yellow",
}


@app.command()
def doctor_cmd() -> None:
    """Check the environment, the database and the tool isolation."""
    doctor.main()


app.command("doctor")(doctor_cmd)


@app.command()
def case(
    account_id: str = typer.Argument(..., help="The account to work, e.g. A00985."),
    auto: bool = typer.Option(False, "--auto", help="Skip approvals; queue irreversible actions."),
    show_trail: bool = typer.Option(False, "--show-trail", help="Print every specialist's finding."),
) -> None:
    """Work one account, with the approval gate live unless --auto."""
    db.init_runtime()
    console.print(f"\n[bold]Working {account_id}[/bold]\n")
    result = sweep.run_case(account_id, auto=auto)

    if show_trail:
        for name, finding in (result.get("findings") or {}).items():
            console.print(f"[dim]--- {name} specialist ---[/dim]")
            console.print(finding)
            console.print()

    if result["status"] == "awaiting_approval":
        console.print("[bold yellow]PAUSED - an irreversible action needs sign-off[/bold yellow]\n")
        for req in result["action_requests"]:
            for action in (req.get("action_requests") or []):
                console.print(f"  tool : [bold]{action.get('name')}[/bold]")
                console.print(f"  args : {action.get('args')}")
        console.print(f"\n  rows written so far: "
                      f"{len(db.fetch('SELECT 1 FROM actions WHERE account_id = ?', (account_id,)))}")

        choice = typer.prompt("\n[a]pprove / [r]eject", default="r")
        approve = choice.lower().startswith("a")
        reason = "" if approve else typer.prompt("Reason for refusing", default="Not warranted.")
        result = sweep.resume_case(result["thread_id"], approve=approve, message=reason)

    verdict = result.get("verdict")
    if verdict:
        style = VERDICT_STYLE.get(verdict["verdict"], "white")
        console.print(f"\n[{style}]{verdict['verdict'].upper()}[/{style}] "
                      f"({verdict['confidence']} confidence)\n")
        console.print(verdict["reasoning"])
        if verdict.get("missing"):
            console.print(f"\n[dim]Would be resolved by:[/dim] {verdict['missing']}")
        console.print("\n[dim]Evidence:[/dim]")
        for e in json.loads(verdict["evidence"]):
            quote = f'  "{e["quote"]}"' if e.get("quote") else ""
            console.print(f"  {e['kind']:<12} {e['id']}{quote}")
    else:
        console.print("[red]No verdict was recorded.[/red]")
    console.print()


@app.command()
def sweep_cmd(
    limit: int = typer.Option(None, "--limit", help="Work only the first N accounts."),
    workers: int = typer.Option(None, "--workers", help="Accounts to run concurrently."),
    detach: bool = typer.Option(False, "--detach", help="Return the job id and exit."),
) -> None:
    """Work the whole queue in the background."""
    db.init_runtime()
    job_id = sweep.start_queue_sweep(limit=limit, workers=workers)
    console.print(f"\njob [bold]{job_id}[/bold] started")

    if detach:
        console.print(f"  sentinel status {job_id}\n")
        return

    console.print("[dim]  (the call above returned immediately; this is a separate wait)[/dim]\n")
    seen = [-1]

    def progress(status: dict) -> None:
        done = status["completed"] + status["failed"]
        if done != seen[0]:
            seen[0] = done
            console.print(f"  {done}/{status['total']}  ok={status['completed']} "
                          f"failed={status['failed']}  {status['progress_pct']}%")

    result = sweep.wait_for_sweep(job_id, on_progress=progress)
    console.print("\n[bold green]Sweep complete[/bold green]\n")
    _print_verdicts(result)


app.command("sweep")(sweep_cmd)


@app.command()
def status(job_id: str) -> None:
    """Progress on a sweep, without blocking."""
    console.print(sweep.check_sweep_status(job_id))


@app.command()
def collect(job_id: str) -> None:
    """The verdicts a sweep has produced so far."""
    _print_verdicts(sweep.collect_sweep_results(job_id))


def _print_verdicts(result: dict) -> None:
    if not result.get("by_verdict"):
        console.print("[yellow]No verdicts recorded yet.[/yellow]")
        return
    table = Table("verdict", "confidence", "accounts")
    for row in result["by_verdict"]:
        style = VERDICT_STYLE.get(row["verdict"], "white")
        table.add_row(f"[{style}]{row['verdict']}[/{style}]", row["confidence"], str(row["n"]))
    console.print(table)
    if result.get("actions_awaiting_approval"):
        console.print(f"\n[yellow]Actions queued for approval:[/yellow] "
                      f"{result['actions_awaiting_approval']}")


@app.command()
def approvals() -> None:
    """Irreversible actions proposed during a sweep, waiting for a person."""
    rows = db.fetch("SELECT * FROM actions WHERE status = 'proposed' ORDER BY action_id")
    if not rows:
        console.print("\n[green]Nothing waiting for approval.[/green]\n")
        return
    table = Table("#", "account", "action", "target", "reason")
    for r in rows:
        table.add_row(str(r["action_id"]), r["account_id"], r["action"],
                      r["target"] or "-", (r["reason"] or "")[:70])
    console.print(table)
    console.print("\n[dim]Proposed during an unattended sweep. Nothing has been "
                  "executed.[/dim]\n")


@app.command()
def policies() -> None:
    """The progressive-disclosure report, including the hot-reload demonstration."""
    middleware.main()


@app.command()
def analyse() -> None:
    """Measured tokens, the isolation boundary, and the single-agent comparison."""
    analysis.main()


@app.command()
def report() -> None:
    """Regenerate DISPOSITIONS.md, CASES.md, WRITEUP.md and EVIDENCE_AUDIT.md."""
    reports.main()


@app.command()
def reset() -> None:
    """Drop all run state. Never touches data/sentinel.db."""
    db.reset_runtime()
    console.print("[green]Runtime reset.[/green] data/sentinel.db untouched.\n")


if __name__ == "__main__":
    app()
