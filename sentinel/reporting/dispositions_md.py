"""DISPOSITIONS.md - the verdict on every alerted account.

The assignment specifies the columns: account_id, verdict, confidence,
reasoning. We add the recorded action and the evidence ids, because a reader
checking a claim should not have to open the database to find out which note
the reasoning is talking about.
"""

from __future__ import annotations

import json
from pathlib import Path

from sentinel.config import PROJECT_ROOT
from sentinel.db import actions
from sentinel.repositories import alerts_repo

OUTPUT = PROJECT_ROOT / "DISPOSITIONS.md"


def _cell(text: str) -> str:
    """Markdown tables cannot hold pipes or newlines."""
    return (text or "").replace("|", "/").replace("\n", " ").strip()


def rows() -> list[dict]:
    return [dict(r) for r in actions.query("SELECT * FROM dispositions ORDER BY account_id")]


def write(path: Path | None = None) -> Path:
    path = path or OUTPUT
    recorded = rows()
    by_account = {r["account_id"]: r for r in recorded}
    queue = alerts_repo.queue()

    counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    for row in recorded:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
        confidence_counts[row["confidence"]] = confidence_counts.get(row["confidence"], 0) + 1

    lines = [
        "# Dispositions",
        "",
        f"Every one of the {len(queue)} alerted accounts in `data/sentinel.db`.",
        "",
        "| verdict | accounts | share |",
        "|---|---:|---:|",
    ]
    for verdict in ("fraud", "legitimate", "insufficient_evidence"):
        n = counts.get(verdict, 0)
        share = f"{100 * n / len(recorded):.1f}%" if recorded else "-"
        lines.append(f"| `{verdict}` | {n} | {share} |")
    lines += [
        f"| **total** | **{len(recorded)}** | |",
        "",
        "| confidence | accounts |",
        "|---|---:|",
    ]
    for level in ("high", "medium", "low"):
        lines.append(f"| `{level}` | {confidence_counts.get(level, 0)} |")

    missing = [a for a in queue if a not in by_account]
    if missing:
        lines += [
            "",
            f"> {len(missing)} account(s) have no recorded disposition: "
            f"{', '.join(missing[:20])}{' ...' if len(missing) > 20 else ''}",
        ]

    lines += [
        "",
        "---",
        "",
        "| account_id | verdict | confidence | action | reasoning | evidence |",
        "|---|---|---|---|---|---|",
    ]

    for account_id in queue:
        row = by_account.get(account_id)
        if not row:
            lines.append(f"| `{account_id}` | - | - | - | *no disposition recorded* | |")
            continue
        refs = json.loads(row["evidence_json"] or "[]")
        cited = ", ".join(f"`{r['ref_id']}`" for r in refs) or "-"
        reasoning = _cell(row["reasoning"])
        needed = json.loads(row["information_required"] or "[]")
        if needed:
            reasoning += " **Needs:** " + "; ".join(_cell(n) for n in needed)
        lines.append(
            f"| `{account_id}` | `{row['verdict']}` | `{row['confidence']}` | "
            f"`{row['action']}` | {reasoning} | {cited} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
