"""Disposition tools: what do we do, and who has to approve it?

This module writes. It does not read.

That is deliberate and it is tested. The disposition officer holds no query
tool at all, so it cannot go and look something up to fill a gap in what it was
told. It has to decide on the findings it was handed, which is what forces the
supervisor to route properly — and it is why swapping this agent's prompt with
any other would visibly break the system.

Two of these three tools are irreversible, and `HumanInTheLoopMiddleware`
intercepts both BEFORE they run (see `agents.py`):

    record_disposition   reversible. Writes a verdict. Never interrupts.
    block_card           irreversible for the customer. Interrupts.
    escalate_case        irreversible for the customer. Interrupts.

Every write goes to `runtime/actions.db`. Nothing here can touch the bank's data.
"""

from __future__ import annotations

import json
from datetime import datetime

from langchain.tools import tool

from sentinel import db, policy


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_evidence(evidence: str) -> tuple[list[policy.EvidenceRef], str | None]:
    """Turn the model's JSON evidence list into refs, or explain what is wrong.

    Expected shape, which the tool docstring states explicitly:

        [{"kind": "note", "id": "N00080", "quote": "verified with video KYC"}]
    """
    try:
        raw = json.loads(evidence)
    except json.JSONDecodeError as exc:
        return [], (
            f"evidence is not valid JSON ({exc}). Pass a JSON list, for example: "
            '[{"kind": "note", "id": "N00080", "quote": "verified with video KYC"}]'
        )
    if not isinstance(raw, list):
        return [], "evidence must be a JSON list of citation objects."

    refs = []
    for item in raw:
        if not isinstance(item, dict) or "kind" not in item or "id" not in item:
            return [], (
                'each citation needs "kind" and "id", for example '
                '{"kind": "alert", "id": "AL0170"}.'
            )
        refs.append(policy.EvidenceRef(
            kind=str(item["kind"]),
            ref_id=str(item["id"]),
            quote=str(item.get("quote", "")),
        ))
    return refs, None


@tool
def record_disposition(
    account_id: str,
    verdict: str,
    confidence: str,
    reasoning: str,
    evidence: str,
    missing: str = "",
) -> str:
    """File the verdict on this account. This is the deliverable.

    Every citation is checked against the database before the verdict is
    accepted: the id must have the right shape, the row must exist, and it must
    belong to THIS account. If you quote a human's words they are compared with
    the stored text. A rejection tells you exactly what was wrong — fix it and
    call again rather than dropping the citation.

    Args:
        account_id: The account being disposed, e.g. 'A00985'.
        verdict: One of 'fraud', 'legitimate', 'insufficient_evidence'.
            'legitimate' must cite something a human wrote. If nothing in the
            file explains the activity, the honest verdict is
            'insufficient_evidence'.
        confidence: One of 'high', 'medium', 'low'.
        reasoning: Why this verdict, in prose an analyst could defend. Name what
            fired, what the deciding evidence said, and why it settles the
            question. Reference the note or dispute by its content, not just its
            id.
        evidence: A JSON list of citations, e.g.
            [{"kind": "alert", "id": "AL0170"},
             {"kind": "note", "id": "N00080", "quote": "verified with video KYC"}]
            Valid kinds: alert, transaction, note, dispute, prior_case.
        missing: Required when the verdict is 'insufficient_evidence'. Name the
            artefact that would resolve it, e.g. 'a customer callback confirming
            the 27 Feb transfers'.
    """
    refs, parse_error = _parse_evidence(evidence)
    if parse_error:
        return f"REJECTED: {parse_error}"

    d = policy.Disposition(
        account_id=account_id,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        evidence=refs,
        missing=missing,
    )
    problems = policy.validate(d)
    if problems:
        return "REJECTED, nothing was written:\n" + "\n".join(f"  - {p}" for p in problems)

    db.write(
        """
        INSERT INTO dispositions
            (account_id, verdict, confidence, reasoning, evidence, missing, decided_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            verdict=excluded.verdict, confidence=excluded.confidence,
            reasoning=excluded.reasoning, evidence=excluded.evidence,
            missing=excluded.missing, decided_at=excluded.decided_at
        """,
        (account_id, verdict, confidence, reasoning,
         json.dumps([r.as_dict() for r in refs]), missing, _now()),
    )
    return (
        f"RECORDED: {account_id} disposed as {verdict} ({confidence} confidence), "
        f"{len(refs)} citation(s) verified against the database."
    )


@tool
def block_card(account_id: str, card_id: str, reason: str) -> str:
    """Block a card. IRREVERSIBLE — a human must approve this before it runs.

    Reserve this for cases where money is still moving. A confirmed one-off that
    has already stopped does not need the customer's card killed; an active
    takeover does. Blocking the card of an account you have called legitimate is
    refused.

    Args:
        account_id: The account the card belongs to.
        card_id: The card to block, e.g. 'K000123'. Take this from the customer
            profile you were given — do not guess it.
        reason: Why this card, now. One sentence an analyst could defend.
    """
    row = db.fetch("SELECT verdict FROM dispositions WHERE account_id = ?", (account_id,))
    if not row:
        return (
            "REFUSED: no verdict has been recorded for this account yet. "
            "Call record_disposition first — an action must follow a verdict."
        )

    verdict = row[0]["verdict"]
    if contradiction := policy.check_action("block_card", verdict):
        return contradiction

    action_id = db.write(
        """
        INSERT INTO actions (account_id, action, target, reason, status, created_at)
        VALUES (?, 'block_card', ?, ?, 'approved', ?)
        """,
        (account_id, card_id, reason, _now()),
    )
    return f"BLOCKED: card {card_id} on {account_id} (action #{action_id}). Reason: {reason}"


@tool
def escalate_case(account_id: str, to_team: str, reason: str) -> str:
    """Escalate to a human investigation team. IRREVERSIBLE — needs approval.

    Use when the case needs a person: a suspected ring, a large loss, or a file
    that cannot be resolved from what is on record but should not simply be
    closed. Escalating an account you have called legitimate is refused.

    Args:
        account_id: The account to escalate.
        to_team: Which team, e.g. 'fraud_investigations' or 'aml_review'.
        reason: What you want them to do, and what you could not settle yourself.
    """
    row = db.fetch("SELECT verdict FROM dispositions WHERE account_id = ?", (account_id,))
    if not row:
        return (
            "REFUSED: no verdict has been recorded for this account yet. "
            "Call record_disposition first — an action must follow a verdict."
        )

    if contradiction := policy.check_action("escalate_case", row[0]["verdict"]):
        return contradiction

    action_id = db.write(
        """
        INSERT INTO actions (account_id, action, target, reason, status, created_at)
        VALUES (?, 'escalate_case', ?, ?, 'approved', ?)
        """,
        (account_id, to_team, reason, _now()),
    )
    return f"ESCALATED: {account_id} to {to_team} (action #{action_id}). Reason: {reason}"


# The registry. Writes only — there is deliberately no read tool in this list,
# and `tests/test_architecture.py` asserts that.
DISPOSITION_TOOLS = [
    record_disposition,
    block_card,
    escalate_case,
]

# The two that cannot be undone. `agents.py` feeds this straight into
# HumanInTheLoopMiddleware, so the gate and the list can never drift apart.
IRREVERSIBLE = ["block_card", "escalate_case"]
