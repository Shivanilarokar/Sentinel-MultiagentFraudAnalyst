"""Sentinel's command line.

    sentinel doctor                     environment, database integrity, tool isolation
    sentinel case A00985                work one account, print the reasoning trail
    sentinel sweep                      work all 276 in the background
    sentinel status <job_id>            progress, without blocking
    sentinel collect <job_id>           the finished verdicts
    sentinel approvals                  irreversible actions a sweep queued for review
    sentinel report all                 DISPOSITIONS.md, CASES.md, WRITEUP.md
    sentinel analyse lookalikes         accounts with identical signatures
    sentinel analyse evidence           re-check every citation against the database

`case` is interactive: if the disposition officer proposes blocking a card or
escalating, the run pauses and asks. Approving one gate can reveal the next, so
it loops until the run finishes.
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sentinel import analysis, config, reports, sweep as sweep_module
from sentinel.sweep import describe_interrupt, resume_case, run_case
from sentinel.db import actions, db, usage_totals

app = typer.Typer(add_completion=False, help="Multi-agent fraud triage for the Sentinel queue.")
analyse_app = typer.Typer(help="Checks that run over recorded results.")
app.add_typer(analyse_app, name="analyse")

console = Console()


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------
@app.command()
def doctor() -> None:
    """Check the environment, the database and the agent wiring before a run."""
    from sentinel.policies import discover_policies, policy_catalog
    from sentinel.tools import disjointness_report

    console.print("[bold]Environment[/bold]")
    key_set = bool(config._first_env("OPENAI_API_KEY", "OPEN_AI_API_KEY"))
    console.print(f"  OPENAI_API_KEY      {'set' if key_set else '[red]MISSING[/red]'}")
    console.print(f"  specialist model    {config.SPECIALIST_MODEL}")
    console.print(f"  supervisor model    {config.SUPERVISOR_MODEL}")
    console.print(f"  LangSmith tracing   {'on' if config.LANGSMITH_ENABLED else 'off'}")
    console.print(f"  sweep workers       {config.SWEEP_WORKERS}")

    console.print("\n[bold]Source database (read-only)[/bold]")
    matches, expected, actual = db.verify_integrity()
    console.print(f"  path                {db.path}")
    console.print(f"  sha256              {actual[:32]}...")
    if expected and matches:
        console.print("  integrity           [green]unchanged since setup[/green]")
    elif expected:
        console.print(f"  integrity           [red]CHANGED - expected {expected[:32]}...[/red]")
    else:
        console.print("  integrity           no recorded hash to compare")
    try:
        db.connect().execute("INSERT INTO alerts (alert_id) VALUES ('x')")
        console.print("  write guard         [red]FAILED - the database is writable[/red]")
    except Exception:
        console.print("  write guard         [green]writes raise, as intended[/green]")
    console.print(f"  alerted accounts    {db.scalar('SELECT COUNT(DISTINCT account_id) FROM alerts')}")

    console.print("\n[bold]Tool isolation[/bold]")
    report = disjointness_report()
    for name, tools in report["tools"].items():
        console.print(f"  {name:<12} {len(tools):>2} tools  {', '.join(tools)}")
    if report["disjoint"]:
        console.print("  [green]specialist tool sets are pairwise disjoint[/green]")
    else:
        console.print(f"  [red]OVERLAP: {report['overlaps']}[/red]")

    console.print("\n[bold]Policy documents (loaded on demand)[/bold]")
    policies = discover_policies()
    bodies = sum(len(p["content"]) for p in policies)
    catalog = len(policy_catalog(policies))
    for p in policies:
        console.print(f"  {p['name']:<20} {len(p['content']):>6,} chars")
    console.print(
        f"  catalog in prompt   {catalog:,} chars   "
        f"({100 * (1 - catalog / (bodies + catalog)):.0f}% of the corpus stays out "
        f"until an agent asks)"
    )


# --------------------------------------------------------------------------
# case
# --------------------------------------------------------------------------
@app.command()
def case(
    account_id: str = typer.Argument(..., help="The flagged account, e.g. A00985"),
    auto: bool = typer.Option(False, "--auto", help="Skip approval prompts; defer actions."),
    show_trail: bool = typer.Option(False, "--show-trail", help="Print each specialist finding."),
) -> None:
    """Work one account and print the verdict with its reasoning trail."""
    console.print(f"[bold]Working {account_id}[/bold]  (supervisor -> 4 specialists)")
    result = run_case(account_id, human_in_the_loop=not auto)

    while result.awaiting_approval:
        console.print()
        decisions = {}
        for interrupt in result.interrupts:
            described = describe_interrupt(interrupt)
            for request in described["action_requests"]:
                console.print(
                    Panel(
                        f"[bold]{request['tool']}[/bold]\n\n"
                        + json.dumps(request["args"], indent=2),
                        title="IRREVERSIBLE ACTION - analyst sign-off required",
                        border_style="yellow",
                    )
                )
            choice = typer.prompt("  [a]pprove / [r]eject", default="r").strip().lower()
            if choice.startswith("a"):
                decisions[described["interrupt_id"]] = {"decisions": [{"type": "approve"}]}
            else:
                why = typer.prompt("  reason", default="Rejected by the analyst.")
                decisions[described["interrupt_id"]] = {
                    "decisions": [{"type": "reject", "message": why}]
                }
        result = resume_case(account_id, decisions)

    if result.status == "failed":
        console.print(f"[red]FAILED[/red] {result.error}")
        raise typer.Exit(1)

    if show_trail:
        for finding in result.findings:
            console.print(
                Panel(
                    finding["finding"],
                    title=(
                        f"{finding['specialist'].upper()}  "
                        f"({finding['chars_inside']:,} chars inside -> "
                        f"{finding['chars_crossed']:,} crossed)"
                    ),
                    border_style="magenta",
                )
            )

    disposition = result.disposition
    if disposition:
        colour = {"fraud": "red", "legitimate": "green"}.get(disposition.verdict, "yellow")
        console.print(
            Panel(
                f"[bold {colour}]{disposition.verdict.upper()}[/bold {colour}]  "
                f"confidence {disposition.confidence}  action {disposition.action}\n\n"
                f"{disposition.reasoning}",
                title=account_id,
                border_style=colour,
            )
        )
        if disposition.evidence:
            table = Table("kind", "id", "quote / detail", show_lines=False)
            for ref in disposition.evidence:
                table.add_row(ref.kind, ref.ref_id, (ref.quote or ref.detail)[:80])
            console.print(table)
        if disposition.information_required:
            console.print("[yellow]To resolve this case we would need:[/yellow]")
            for item in disposition.information_required:
                console.print(f"  - {item}")
    else:
        console.print("[yellow]No disposition was recorded.[/yellow]")

    console.print(f"\n[dim]{result.elapsed_seconds:.1f}s[/dim]")


# --------------------------------------------------------------------------
# sweep
# --------------------------------------------------------------------------
@app.command()
def sweep(
    limit: int = typer.Option(0, help="Work only the first N accounts. 0 means all 276."),
    workers: int = typer.Option(0, help="Accounts in parallel. 0 uses the configured default."),
    detach: bool = typer.Option(False, "--detach", help="Return the job id and exit."),
) -> None:
    """Work the whole queue in the background. Returns a job id immediately."""
    import time

    started = time.time()
    job = sweep_module.start_queue_sweep(limit=limit, workers=workers)
    console.print(
        f"[green]started[/green] {job['job_id']}  {job['accounts']} accounts  "
        f"(returned in {time.time() - started:.3f}s)"
    )

    if detach:
        console.print(f"[dim]sentinel status {job['job_id']}[/dim]")
        return

    with console.status("working the queue...") as status:
        while True:
            state = sweep_module.check_sweep_status(job["job_id"])
            status.update(
                f"{state['progress']} accounts  ({state['pct']}%)  "
                f"failed={state['failed']}"
            )
            if state["status"] != "running":
                break
            time.sleep(3)

    final = sweep_module.check_sweep_status(job["job_id"])
    console.print(
        f"[bold]{final['status']}[/bold]  completed={final['completed']} "
        f"failed={final['failed']}  in {time.time() - started:.0f}s"
    )
    _verdict_table(job["job_id"])


def _verdict_table(job_id: str) -> None:
    results = sweep_module.collect_sweep_results(job_id)
    table = Table("verdict", "accounts")
    for verdict, count in sorted(results.get("verdicts", {}).items()):
        table.add_row(verdict, str(count))
    console.print(table)


@app.command()
def status(job_id: str) -> None:
    """Progress on a sweep. Does not block."""
    console.print(json.dumps(sweep_module.check_sweep_status(job_id), indent=1))


@app.command()
def collect(job_id: str, limit: int = typer.Option(0)) -> None:
    """The verdicts a sweep produced."""
    results = sweep_module.collect_sweep_results(job_id, limit=limit)
    if "error" in results:
        console.print(f"[red]{results['error']}[/red]")
        raise typer.Exit(1)
    table = Table("account", "verdict", "confidence", "action")
    for row in results["dispositions"]:
        table.add_row(row["account_id"], row["verdict"], row["confidence"], row["action"])
    console.print(table)
    console.print(results["verdicts"])


@app.command()
def jobs() -> None:
    """Recent sweeps."""
    table = Table("job", "status", "total", "done", "failed", "started")
    for job in sweep_module.recent_jobs():
        table.add_row(
            job["job_id"], job["status"], str(job["total"]),
            str(job["completed"]), str(job["failed"]), job["started_at"],
        )
    console.print(table)


# --------------------------------------------------------------------------
# approvals
# --------------------------------------------------------------------------
@app.command()
def approvals() -> None:
    """Irreversible actions a sweep proposed and queued for an analyst."""
    pending = sweep_module.pending_actions()
    if not pending:
        console.print("Nothing awaiting review.")
        return
    table = Table("id", "account", "action", "reason", "when")
    for row in pending:
        table.add_row(
            str(row["action_id"]), row["account_id"], row["action"],
            row["reason"][:70], row["at"],
        )
    console.print(table)


# --------------------------------------------------------------------------
# analyse
# --------------------------------------------------------------------------
@analyse_app.command("evidence")
def analyse_evidence() -> None:
    """Re-check every citation on every recorded disposition against the database."""

    audit = analysis.audit_all()
    console.print(
        f"{audit['citations_verified']}/{audit['citations_checked']} citations verified "
        f"({audit['pass_rate_pct']}%) across {audit['accounts_audited']} accounts"
    )
    for failure in audit["accounts_with_failures"]:
        console.print(f"[red]{failure['account_id']}[/red]")
        for problem in failure["failures"]:
            console.print(f"   - {problem}")


@analyse_app.command("lookalikes")
def analyse_lookalikes(limit: int = typer.Option(12)) -> None:
    """Accounts with identical alert signatures, and whether we called them differently."""

    pairs = analysis.separated_pairs()
    console.print(f"{len(pairs)} matched pairs with identical signatures and opposite verdicts\n")
    for pair in pairs[:limit]:
        console.print(f"[bold]{pair['signature']}[/bold]")
        for side in ("a", "b"):
            account = pair[side]
            console.print(
                f"   {account['account_id']}  "
                f"[{'red' if account['verdict'] == 'fraud' else 'green'}]"
                f"{account['verdict']}[/]  {account['confidence']}"
            )


@analyse_app.command("tokens")
def analyse_tokens() -> None:
    """Measured sweep cost, and the single-agent comparison."""

    totals = usage_totals()
    table = Table("agent", "runs", "tokens", "chars inside", "chars crossed")
    for row in totals["per_agent"]:
        table.add_row(
            row["agent"], str(row["invocations"]), f"{row['total_tokens']:,}",
            f"{row['chars_inside']:,}", f"{row['chars_crossed']:,}",
        )
    console.print(table)
    overall = totals["overall"]
    console.print(
        f"total {overall['total_tokens']:,} tokens over {overall['accounts']} accounts; "
        f"{overall['discarded_at_boundary_pct']}% of specialist output discarded at the boundary"
    )
    console.print(json.dumps(analysis.single_agent_estimate(), indent=1))


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
@app.command()
def report(
    what: str = typer.Argument("all", help="all | dispositions | cases | writeup | evidence")
) -> None:
    """Generate the deliverables from recorded results."""

    made = []
    if what == "all":
        made = reports.write_all()
    elif what == "dispositions":
        made = [reports.write_dispositions()]
    elif what == "evidence":
        made = [reports.write_evidence_audit()]
    elif what == "cases":
        made = [reports.write_cases()]
    elif what == "writeup":
        made = [reports.write_writeup()]
    for path in made:
        console.print(f"[green]wrote[/green] {path}")


@app.command()
def reset() -> None:
    """Drop all run state. Never touches the source database."""
    actions.reset()
    console.print("runtime/actions.db removed. data/sentinel.db untouched.")


if __name__ == "__main__":
    app()
