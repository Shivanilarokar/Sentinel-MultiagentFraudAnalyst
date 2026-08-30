"""CASES.md - three worked cases, in full.

The assignment asks for one obvious fraud, one convincing false positive, and
one that could not be resolved. They are selected from the recorded results
rather than hand-picked, using the strongest example of each shape, so the
document reflects what the system actually did.

Each case shows every specialist's finding as the supervisor received it -
which is to say, the whole of what crossed the boundary - alongside how much
was produced inside and discarded. That contrast is the architecture, made
visible on a single case.
"""

from __future__ import annotations

import json
from pathlib import Path

from sentinel.config import PROJECT_ROOT
from sentinel.db import actions
from sentinel.repositories import alerts_repo, narrative_repo, transactions_repo

OUTPUT = PROJECT_ROOT / "CASES.md"


def _dispositions() -> list[dict]:
    return [dict(r) for r in actions.query("SELECT * FROM dispositions")]


def _findings(account_id: str) -> list[dict]:
    return [
        dict(r)
        for r in actions.query(
            "SELECT * FROM findings WHERE account_id = ? ORDER BY finding_id",
            (account_id,),
        )
    ]


def _score(row: dict) -> int:
    """Prefer cases with high confidence and a rich citation trail."""
    refs = json.loads(row["evidence_json"] or "[]")
    quoted = sum(1 for r in refs if r.get("quote"))
    return {"high": 3, "medium": 2, "low": 1}.get(row["confidence"], 0) * 10 + len(refs) + quoted


def pick_cases() -> dict[str, dict | None]:
    """The strongest example of each of the three required shapes."""
    rows = _dispositions()
    picked: dict[str, dict | None] = {}
    for label, verdict in (
        ("obvious fraud", "fraud"),
        ("convincing false positive", "legitimate"),
        ("could not be resolved", "insufficient_evidence"),
    ):
        candidates = [r for r in rows if r["verdict"] == verdict and _findings(r["account_id"])]
        if not candidates:
            candidates = [r for r in rows if r["verdict"] == verdict]
        picked[label] = max(candidates, key=_score) if candidates else None
    return picked


def _case_section(label: str, row: dict) -> list[str]:
    account_id = row["account_id"]
    alerts = alerts_repo.for_account(account_id)
    window = alerts_repo.incident_window(account_id)
    incident = transactions_repo.incident_transactions(account_id)
    notes = narrative_repo.case_notes(account_id)
    refs = json.loads(row["evidence_json"] or "[]")
    needed = json.loads(row["information_required"] or "[]")

    lines = [
        f"## {label}: `{account_id}`",
        "",
        f"**Verdict: `{row['verdict']}`, confidence `{row['confidence']}`, "
        f"action `{row['action']}`**",
        "",
        "### What fired",
        "",
        "| alert | rule | what the rule detects | severity | triggered |",
        "|---|---|---|---|---|",
    ]
    for alert in alerts:
        lines.append(
            f"| `{alert['alert_id']}` | {alert['rule_id']} {alert['rule_name']} | "
            f"{alert['rule_description']} | {alert['severity']} | {alert['triggered_at']} |"
        )
    if window:
        lines += [
            "",
            f"Incident window: `{window['incident_start']}` to `{window['incident_end']}`.",
        ]

    if incident:
        lines += [
            "",
            "### The transactions inside that window",
            "",
            "| txn | time | amount | country | merchant | category | result |",
            "|---|---|---:|---|---|---|---|",
        ]
        for txn in incident[:12]:
            lines.append(
                f"| `{txn['txn_id']}` | {txn['ts']} | {txn['amount']:,.2f} | "
                f"{txn['ip_country']} | {txn.get('merchant_name', '')} | "
                f"{txn.get('merchant_category', '')} | {txn['auth_result']} |"
            )

    if notes:
        lines += ["", "### What the file said", ""]
        for note in notes:
            when = (
                f"{abs(note['days_before_alert'])} days "
                f"{'before' if note['timing'] == 'before_alert' else 'after'} the incident"
            )
            lines += [
                f"**`{note['note_id']}`** - {note['created_at']}, {note['author']} "
                f"({note['channel']}), {when}",
                "",
                f"> {note['note']}",
                "",
            ]
    else:
        lines += ["", "### What the file said", "", "Nothing. There are no case notes.", ""]

    lines += ["", "### What each specialist reported back", ""]
    for finding in _findings(account_id):
        discarded = (
            f"{100 * (1 - finding['chars_crossed'] / finding['chars_inside']):.0f}%"
            if finding["chars_inside"]
            else "n/a"
        )
        lines += [
            f"#### {finding['specialist'].title()}",
            "",
            f"*{finding['chars_inside']:,} characters produced inside this specialist, "
            f"{finding['chars_crossed']:,} crossed back to the supervisor "
            f"({discarded} discarded).*",
            "",
            "```",
            finding["finding"],
            "```",
            "",
        ]

    lines += [
        "### How the supervisor weighed them",
        "",
        row["reasoning"],
        "",
        "### Evidence cited",
        "",
        "| kind | id | quote or detail |",
        "|---|---|---|",
    ]
    for ref in refs:
        detail = (ref.get("quote") or ref.get("detail") or "").replace("|", "/")
        lines.append(f"| {ref['kind']} | `{ref['ref_id']}` | {detail} |")

    if needed:
        lines += ["", "### What would resolve this case", ""]
        for item in needed:
            lines.append(f"- {item}")

    lines += ["", "---", ""]
    return lines


def write(path: Path | None = None) -> Path:
    path = path or OUTPUT
    picked = pick_cases()

    lines = [
        "# Three worked cases",
        "",
        "One obvious fraud, one convincing false positive, and one that could not be",
        "resolved. Each is chosen from the recorded results by confidence and citation",
        "depth, not hand-picked, and each shows exactly what the supervisor received",
        "from every specialist.",
        "",
        "Everything below is reproducible: run `sentinel case <id> --show-trail`.",
        "",
        "---",
        "",
    ]
    for label, row in picked.items():
        if row is None:
            lines += [f"## {label}", "", "*No case of this shape in the current results.*", "", "---", ""]
        else:
            lines += _case_section(label, row)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
