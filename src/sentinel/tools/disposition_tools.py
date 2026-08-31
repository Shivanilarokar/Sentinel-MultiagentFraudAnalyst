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

from langchain.tools import ToolRuntime, tool

from sentinel import db, validation


def _parse_evidence(evidence: str) -> tuple[list[validation.EvidenceRef], str | None]:
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
        refs.append(validation.EvidenceRef(
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

    d = validation.Disposition(
        account_id=account_id,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        evidence=refs,
        missing=missing,
    )
    problems = validation.validate(d)
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
         json.dumps([r.as_dict() for r in refs]), missing, db.now()),
    )
    return (
        f"RECORDED: {account_id} disposed as {verdict} ({confidence} confidence), "
        f"{len(refs)} citation(s) verified against the database."
    )


def _verdict_for(account_id: str) -> str | None:
    """The verdict already recorded for this account, if any."""
    rows = db.fetch("SELECT verdict FROM dispositions WHERE account_id = ?", (account_id,))
    return rows[0]["verdict"] if rows else None


def _file_action(account_id: str, action: str, target: str, reason: str,
                 runtime: ToolRuntime) -> str:
    """Record an irreversible action, executing it only if a human is present.

    During a sweep nobody is watching, so the action is written with status
    `proposed` and waits in `sentinel approvals` for a person. An unattended run
    that could block cards is a worse system than one that cannot.

    When a human IS present, `HumanInTheLoopMiddleware` has already interrupted
    and been approved before this function is reached at all — so by the time we
    are here, the sign-off has happened.
    """
    verdict = _verdict_for(account_id)
    if verdict is None:
        return (
            "REFUSED: no verdict has been recorded for this account yet. "
            "Call record_disposition first — an action must follow a verdict."
        )
    if contradiction := validation.check_action(action, verdict):
        return contradiction

    unattended = bool(runtime.state.get("unattended"))
    status = "proposed" if unattended else "approved"

    action_id = db.write(
        "INSERT INTO actions (account_id, action, target, reason, status, "
        "approved_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (account_id, action, target, reason, status,
         None if unattended else "analyst", db.now()),
    )

    if unattended:
        return (
            f"QUEUED (action #{action_id}): {action} on {account_id} targeting "
            f"{target} has been PROPOSED, not executed. No analyst is present "
            f"during a sweep, and this action cannot be undone. It is waiting "
            f"for sign-off. Reason recorded: {reason}"
        )
    return (
        f"EXECUTED (action #{action_id}): {action} on {account_id} targeting "
        f"{target}, approved by analyst. Reason: {reason}"
    )


@tool
def block_card(account_id: str, card_id: str, reason: str,
               runtime: ToolRuntime) -> str:
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
    return _file_action(account_id, "block_card", card_id, reason, runtime)


@tool
def escalate_case(account_id: str, to_team: str, reason: str,
                  runtime: ToolRuntime) -> str:
    """Escalate to a human investigation team. IRREVERSIBLE — needs approval.

    Use when the case needs a person: a suspected ring, a large loss, or a file
    that cannot be resolved from what is on record but should not simply be
    closed. Escalating an account you have called legitimate is refused.

    Args:
        account_id: The account to escalate.
        to_team: Which team, e.g. 'fraud_investigations' or 'aml_review'.
        reason: What you want them to do, and what you could not settle yourself.
    """
    return _file_action(account_id, "escalate_case", to_team, reason, runtime)


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
