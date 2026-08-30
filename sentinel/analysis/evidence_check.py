"""Resolve every citation back to a database row.

A disposition's reasoning is a claim. This module is what turns it into a
checkable one: for each `EvidenceRef` it asks three questions.

    1. Does this identifier exist at all?
    2. Does it belong to *this* account?
    3. For human-written records, are the quoted words actually in the row?

Question 2 is the one that catches the most damaging error. A model that was
never told the real alert id will produce a well-formed one - `AL0001` instead
of `AL0009` - which passes a format check and points at somebody else's case.

This runs in two places. `verify_refs` is called inside `record_disposition`,
so a bad citation is refused while the model can still fix it. The same
function drives `reports/evidence_audit.md` after a sweep, which is the
evidence that nothing was invented across all 276.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sentinel.db import db
from sentinel.models import EvidenceRef

# How each kind of record is tied back to an account. Notes and prior cases
# hang off the customer, disputes off a transaction, so each needs its own hop.
OWNERSHIP_SQL: dict[str, str] = {
    "alert": "SELECT account_id FROM alerts WHERE alert_id = ?",
    "transaction": "SELECT account_id FROM transactions WHERE txn_id = ?",
    "case_note": """
        SELECT a.account_id FROM case_notes n
        JOIN accounts a ON a.customer_id = n.customer_id
        WHERE n.note_id = ?
    """,
    "dispute": """
        SELECT t.account_id FROM disputes d
        JOIN transactions t ON t.txn_id = d.txn_id
        WHERE d.dispute_id = ?
    """,
    "prior_case": """
        SELECT a.account_id FROM prior_cases p
        JOIN accounts a ON a.customer_id = p.customer_id
        WHERE p.case_id = ?
    """,
    "device": """
        SELECT DISTINCT t.account_id FROM transactions t
        WHERE t.device_id = ?
    """,
}

QUOTE_SQL: dict[str, str] = {
    "case_note": "SELECT note FROM case_notes WHERE note_id = ?",
    "dispute": "SELECT customer_statement FROM disputes WHERE dispute_id = ?",
    "prior_case": "SELECT summary FROM prior_cases WHERE case_id = ?",
}


def _normalise(text: str) -> str:
    """Collapse whitespace and case so a quote is compared on its words."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


@dataclass
class RefCheck:
    """The verdict on one citation."""

    kind: str
    ref_id: str
    exists: bool
    belongs: bool
    quote_ok: bool
    problem: str = ""

    @property
    def ok(self) -> bool:
        return self.exists and self.belongs and self.quote_ok


def check_ref(account_id: str, ref: EvidenceRef) -> RefCheck:
    """Resolve one citation against the database."""
    kind, ref_id = ref.kind, ref.ref_id.strip()

    sql = OWNERSHIP_SQL.get(kind)
    if sql is None:
        return RefCheck(kind, ref_id, True, True, True)

    owners = {r[0] for r in db.query(sql, (ref_id,))}
    if not owners:
        return RefCheck(
            kind, ref_id, False, False, False,
            problem=f"{kind} '{ref_id}' does not exist in the database.",
        )

    if account_id not in owners:
        others = ", ".join(sorted(owners)[:3])
        return RefCheck(
            kind, ref_id, True, False, False,
            problem=(
                f"{kind} '{ref_id}' exists but belongs to {others}, not {account_id}."
            ),
        )

    quote_sql = QUOTE_SQL.get(kind)
    if quote_sql and ref.quote.strip():
        stored = db.scalar(quote_sql, (ref_id,)) or ""
        fragment = _normalise(ref.quote)
        # Compare on a leading fragment: a specialist may legitimately quote
        # part of a long note, but it must be part of that note.
        if fragment and fragment[:80] not in _normalise(stored):
            return RefCheck(
                kind, ref_id, True, True, False,
                problem=(
                    f"the quote attributed to {kind} '{ref_id}' is not in that record. "
                    f"The record actually reads: \"{stored[:160]}\""
                ),
            )

    return RefCheck(kind, ref_id, True, True, True)


def verify_refs(account_id: str, refs: list[EvidenceRef]) -> list[RefCheck]:
    """Check every citation on a disposition."""
    return [check_ref(account_id, ref) for ref in refs]


def refusal_for(account_id: str, refs: list[EvidenceRef]) -> str | None:
    """A tool-result refusal if any citation does not hold up, else None.

    Written to be actionable, because it goes back to the model and a vague
    refusal produces a confused retry rather than a correction.
    """
    problems = [c.problem for c in verify_refs(account_id, refs) if not c.ok]
    if not problems:
        return None
    listed = "\n".join(f"  - {p}" for p in problems)
    return (
        f"REFUSED: {len(problems)} citation(s) on {account_id} do not check out against "
        f"the database:\n{listed}\n"
        f"Use only identifiers that appeared in the specialist findings for this "
        f"account, and copy quotes exactly. Drop any citation you cannot support - "
        f"an invented or misattributed reference is worse than a missing one."
    )


def audit_all() -> dict:
    """Re-check every recorded disposition. Drives reports/evidence_audit.md."""
    import json

    from sentinel.db import actions

    rows = [dict(r) for r in actions.query("SELECT * FROM dispositions ORDER BY account_id")]
    results = []
    total = clean = 0
    for row in rows:
        refs = [EvidenceRef(**e) for e in json.loads(row["evidence_json"] or "[]")]
        checks = verify_refs(row["account_id"], refs)
        total += len(checks)
        clean += sum(1 for c in checks if c.ok)
        results.append(
            {
                "account_id": row["account_id"],
                "verdict": row["verdict"],
                "citations": len(checks),
                "failures": [c.problem for c in checks if not c.ok],
            }
        )
    return {
        "accounts_audited": len(rows),
        "citations_checked": total,
        "citations_verified": clean,
        "pass_rate_pct": round(100 * clean / total, 1) if total else None,
        "accounts_with_failures": [r for r in results if r["failures"]],
        "detail": results,
    }
