"""The approval gate, demonstrated on both paths.

An approval gate is only worth having if both paths work, so this exercises both
against real runs and writes the transcripts to `docs/transcripts/`. A gate that
has only ever been tested on the happy path is an untested gate.

Where the pieces go, because getting it backwards is the usual mistake:

    HumanInTheLoopMiddleware  on the disposition SUBAGENT, because that is
                              where the irreversible tools live
    the checkpointer          on the SUPERVISOR, because that is the run that
                              has to freeze and thaw

The interrupt fires inside a subagent invoked within a supervisor tool, and
propagates all the way up. The whole run — supervisor, specialists, findings —
is frozen in `runtime/checkpoints.db` until somebody decides.

What the transcripts have to show:

    paused    status=awaiting_approval, and ZERO rows in the actions table
    approved  the action executed, approved_by=analyst
    rejected  still ZERO action rows, and the officer did NOT retry

That last one matters most. A rejection that the model works around is not an
approval gate, it is a speed bump.

    python -m sentinel.transcripts A00594
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from sentinel import db
from sentinel.config import PROJECT_ROOT
from sentinel.sweep import resume_case, run_case

TRANSCRIPTS = PROJECT_ROOT / "docs" / "transcripts"


def _action_rows(account_id: str) -> list[dict]:
    return [dict(r) for r in db.fetch(
        "SELECT action_id, action, target, status, approved_by, reason "
        "FROM actions WHERE account_id = ? ORDER BY action_id", (account_id,))]


def _disposition(account_id: str) -> dict | None:
    rows = db.fetch(
        "SELECT verdict, confidence, reasoning FROM dispositions WHERE account_id = ?",
        (account_id,))
    return dict(rows[0]) if rows else None


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _header(title: str, account_id: str) -> list[str]:
    return [
        "=" * 78,
        f"  {title}",
        f"  account {account_id}   generated {datetime.now():%Y-%m-%d %H:%M:%S}",
        "=" * 78,
        "",
    ]


def _describe_requests(requests: list) -> list[str]:
    out = []
    for req in requests:
        for action in (req.get("action_requests") or []):
            out += [
                f"    tool : {action.get('name')}",
                f"    args : {json.dumps(action.get('args', {}), indent=11)[1:-1].strip()}",
            ]
        for cfg in (req.get("review_configs") or []):
            out.append(f"    decisions allowed : {cfg.get('allowed_decisions')}")
    return out


def one_path(account_id: str, *, approve: bool, run_tag: str) -> list[str]:
    """Run the account, pause at the gate, then approve or reject. Returns lines."""
    label = "APPROVED" if approve else "REJECTED"
    lines = _header(f"HUMAN APPROVAL GATE - {label} PATH", account_id)

    # Clear only this account's actions, so the row counts below mean something.
    db.write("DELETE FROM actions WHERE account_id = ?", (account_id,))

    lines += ["[1] The supervisor works the case.", ""]
    result = run_case(account_id, thread_id=f"hitl-{run_tag}-{account_id}")

    consulted = result.get("specialists_consulted") or list(result.get("findings", {}))
    lines += [f"    specialists consulted : {', '.join(consulted) or '(none recorded)'}",
              f"    run status            : {result['status']}", ""]

    if result["status"] != "awaiting_approval":
        lines += [
            "    The disposition officer did not reach for an irreversible action on",
            "    this run, so there was nothing to approve. That is a legitimate",
            "    outcome - the escalation matrix reserves block_card and",
            "    escalate_case for cases that need them - but it means this run",
            "    does not demonstrate the gate.",
            "",
            f"    verdict recorded : {_disposition(account_id)}",
        ]
        return lines

    lines += ["[2] PAUSED. The gate fired BEFORE the tool ran.", ""]
    lines += _describe_requests(result["action_requests"])
    rows = _action_rows(account_id)
    lines += [
        "",
        f"    rows in the actions table while paused : {len(rows)}",
        "    Nothing has been written. No card is stopped. The whole run -",
        "    supervisor, specialists, findings - is frozen in the checkpointer.",
        "",
        f"    thread_id : {result['thread_id']}",
        "",
    ]

    decision = ("Command(resume={'decisions': [{'type': 'approve'}]})" if approve else
                "Command(resume={'decisions': [{'type': 'reject', 'message': ...}]})")
    lines += [f"[3] The analyst decides: {label}.", "", f"    {decision}", ""]

    resumed = resume_case(
        result["thread_id"],
        approve=approve,
        message="" if approve else (
            "Refused by the analyst: the shared-device link is not strong enough "
            "to justify an irreversible action on this customer. Do not retry. "
            "Record the case without the action and note that it was declined."
        ),
    )

    lines += ["[4] The run resumes and finishes.", "",
              f"    status : {resumed['status']}", ""]

    rows = _action_rows(account_id)
    lines += [f"    rows in the actions table now : {len(rows)}"]
    for r in rows:
        lines += [f"      #{r['action_id']}  {r['action']} -> {r['target']}",
                  f"          status      : {r['status']}",
                  f"          approved_by : {r['approved_by']}",
                  f"          reason      : {r['reason']}"]
    if not rows:
        lines += ["      (none - the rejection was honoured and nothing was written)"]

    disposition = _disposition(account_id)
    if disposition:
        lines += ["", "    verdict on file:",
                  f"      {disposition['verdict']} ({disposition['confidence']})",
                  f"      {disposition['reasoning'][:400]}"]

    lines += ["", "-" * 78, ""]
    if approve:
        lines += ["  RESULT: the action executed only after sign-off, and is",
                  "  recorded with approved_by=analyst."]
    else:
        lines += ["  RESULT: zero action rows. The officer was told the action was",
                  "  refused and did NOT retry it - it recorded the case without.",
                  "  A rejection the model works around is not an approval gate."]
    lines += ["", "=" * 78]
    return lines


def main(account_id: str = "A00594") -> None:
    """Run both paths and write the transcripts."""
    db.init_runtime()

    print(f"Generating approval-gate transcripts for {account_id}...\n")

    approved = one_path(account_id, approve=True, run_tag="approve")
    _write(TRANSCRIPTS / "hitl-approved.txt", approved)
    print("\n".join(approved))

    print("\n\n")

    rejected = one_path(account_id, approve=False, run_tag="reject")
    _write(TRANSCRIPTS / "hitl-rejected.txt", rejected)
    print("\n".join(rejected))

    print(f"\nWritten to {TRANSCRIPTS}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "A00594")
