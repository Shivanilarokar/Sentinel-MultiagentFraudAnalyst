"""reports/evidence_audit.md - every citation re-checked against the database.

A disposition's reasoning is a claim. This report is what turns the whole set
of them into checkable ones: each cited identifier is resolved back to a row,
confirmed to belong to the account it was cited on, and - for anything a human
wrote - checked that the quoted words are actually in the record.

It is deliberately a separate pass from the write-time check in
`record_disposition`. The write-time check stops bad citations landing; this
one proves, after the fact and over every account, that none did.
"""

from __future__ import annotations

from pathlib import Path

from sentinel.analysis import evidence_check
from sentinel.config import PROJECT_ROOT, REPORTS_DIR, ensure_dirs

OUTPUT = REPORTS_DIR / "evidence_audit.md"


def write(path: Path | None = None) -> Path:
    ensure_dirs()
    path = path or OUTPUT
    audit = evidence_check.audit_all()

    lines = [
        "# Evidence audit",
        "",
        "Every citation on every recorded disposition, resolved back to a row in",
        "`data/sentinel.db`. Three questions per citation: does the identifier exist,",
        "does it belong to the account it was cited on, and - for case notes, disputes",
        "and prior cases - are the quoted words actually in that record?",
        "",
        "| | |",
        "|---|---:|",
        f"| accounts audited | {audit['accounts_audited']} |",
        f"| citations checked | {audit['citations_checked']} |",
        f"| citations verified | {audit['citations_verified']} |",
        f"| pass rate | {audit['pass_rate_pct']}% |",
        "",
    ]

    failures = audit["accounts_with_failures"]
    if not failures:
        lines += [
            "**No citation failed.** Every identifier exists, belongs to the account it",
            "was cited on, and every quote appears verbatim in the record it names.",
            "",
        ]
    else:
        lines += [
            f"## {len(failures)} account(s) with a failing citation",
            "",
        ]
        for row in failures:
            lines += [f"### `{row['account_id']}` ({row['verdict']})", ""]
            for problem in row["failures"]:
                lines.append(f"- {problem}")
            lines.append("")

    lines += [
        "---",
        "",
        "## Per-account detail",
        "",
        "| account | verdict | citations | failures |",
        "|---|---|---:|---:|",
    ]
    for row in audit["detail"]:
        lines.append(
            f"| `{row['account_id']}` | {row['verdict']} | {row['citations']} | "
            f"{len(row['failures'])} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
