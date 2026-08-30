"""Tools for the Disposition specialist: it writes, it does not read.

This agent holds no database read tools at all. Everything it knows arrives in
the brief the supervisor hands it, which is the point - it cannot quietly go
and re-derive a fact that the specialists were supposed to establish, and it
cannot cite a record nobody actually looked at.

Three tools, in two very different classes:

    record_disposition   safe and reversible. Writes a verdict row.
    block_card           IRREVERSIBLE. Stops a customer using their card.
    escalate_case        IRREVERSIBLE. Opens a case with the investigations team.

One clarification on "does not read". `record_disposition` validates the
citations it is handed against the database before writing them. That is the
*tool* checking its own input, not the agent querying anything: the agent still
has no read tool and cannot go looking for a record. It is the same shape as a
booking tool that refuses attendees who are not in the directory - the caller
does not gain a lookup, the write gains an integrity check. It matters here
because a model that was never told the real alert id will produce a
well-formed wrong one, and a citation pointing at somebody else's case is the
most damaging thing a disposition can contain.

The two irreversible ones are wrapped by HumanInTheLoopMiddleware in
`agents.py`, so they interrupt *before* executing. Nothing in this module is
responsible for asking permission; by the time a function body here runs, a
human has already approved it. That ordering is the whole safety property, and
it is why the approval lives in middleware rather than inside these functions.
"""

from __future__ import annotations

import json

from langchain.tools import tool

from sentinel import policy
from sentinel.analysis import evidence_check
from sentinel.db import actions
from sentinel.models import Disposition, EvidenceRef

# Set by the case runner. Sweep mode defers irreversible actions rather than
# executing them, which is what keeps a 276-account run from ever taking an
# unapproved action.
_MODE = {"approval": "interactive"}


def set_approval_mode(mode: str) -> None:
    """'interactive' pauses for a human. 'defer' queues actions for later review."""
    _MODE["approval"] = mode


def approval_mode() -> str:
    return _MODE["approval"]


@tool
def record_disposition(
    account_id: str,
    verdict: str,
    confidence: str,
    reasoning: str,
    action: str,
    evidence: list[EvidenceRef],
    information_required: list[str] = [],
) -> str:
    """Record the final verdict on this account. Safe and reversible.

    Call this exactly once, after you have weighed all three specialist
    findings. It validates against the desk's hard rules and refuses anything
    that would not survive review, telling you what to fix.

    Args:
        account_id: The account being disposed of, e.g. 'A00985'.
        verdict: 'fraud', 'legitimate' or 'insufficient_evidence'.
        confidence: 'high', 'medium' or 'low'.
        reasoning: The defensible account of why, written for a compliance
            officer who cannot see your tools. Name what fired, what the
            behaviour showed, what the file said, and which of those decided it.
        action: 'none', 'monitor', 'block_card' or 'escalate_case'. This
            records the intent; block_card and escalate_case must also be
            called as their own tools, which is where approval happens.
        evidence: The records this rests on. Every claim in your reasoning
            should appear here with its real identifier, and any case note,
            dispute or prior case must carry a verbatim quote.
        information_required: For insufficient_evidence only - the specific
            artefacts that would settle the case.
    """
    refusal = policy.check_disposition(
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        action=action,
        evidence=evidence,
        information_required=information_required,
    )
    if refusal:
        return refusal

    # Every citation must resolve to a real row that belongs to THIS account.
    # Shape alone is not enough: AL0001 is a valid alert id and the wrong one.
    refusal = evidence_check.refusal_for(account_id, evidence)
    if refusal:
        return refusal

    payload = [e.model_dump() for e in evidence]
    with actions.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dispositions
                (account_id, verdict, confidence, reasoning, action,
                 evidence_json, information_required)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                verdict = excluded.verdict,
                confidence = excluded.confidence,
                reasoning = excluded.reasoning,
                action = excluded.action,
                evidence_json = excluded.evidence_json,
                information_required = excluded.information_required,
                decided_at = datetime('now')
            """,
            (
                account_id,
                verdict,
                confidence,
                reasoning.strip(),
                action,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(information_required, ensure_ascii=False),
            ),
        )
    actions.log("disposition", "record", f"{account_id} {verdict}/{confidence} action={action}")

    tail = ""
    if policy.requires_approval(action):
        tail = (
            f" '{action}' is irreversible, so it does not take effect from this call. "
            f"Call the {action} tool to request it; a human has to sign it off."
        )
    return f"Recorded {account_id}: {verdict} ({confidence}), action={action}.{tail}"


@tool
def block_card(account_id: str, card_id: str, reason: str) -> str:
    """Block a card so it can take no further transactions. IRREVERSIBLE.

    Reserved for active money movement you want to stop now: a fraud verdict
    where the account is still transacting and the loss is ongoing. A
    confirmed one-off that has already finished does not need a block, and
    blocking a card on a customer who did nothing wrong is a real harm.

    This pauses for human approval before it executes. If you are told the
    decision was rejected, record that and do not call this tool again.

    Args:
        account_id: The account holding the card.
        card_id: The specific card to block, e.g. 'CD01234'.
        reason: Why, in one sentence, citing the evidence.
    """
    if approval_mode() == "defer":
        with actions.cursor() as cur:
            cur.execute(
                "INSERT INTO actions (account_id, action, reason, state) VALUES (?,?,?,?)",
                (account_id, "block_card", f"{card_id}: {reason}", "pending_review"),
            )
        actions.log("disposition", "block_card:deferred", f"{account_id} {card_id}")
        return (
            f"QUEUED FOR REVIEW, not executed. Card {card_id} on {account_id} is "
            f"recorded as a proposed block awaiting an analyst. No card has been "
            f"blocked. Say so in your final message."
        )

    with actions.cursor() as cur:
        cur.execute(
            "INSERT INTO actions (account_id, action, reason, state, approved_by) "
            "VALUES (?,?,?,?,?)",
            (account_id, "block_card", f"{card_id}: {reason}", "executed", "analyst"),
        )
    actions.log("disposition", "block_card:executed", f"{account_id} {card_id} - {reason}")
    return f"EXECUTED after approval: card {card_id} on {account_id} is blocked. Reason: {reason}"


@tool
def escalate_case(account_id: str, reason: str, escalate_to: str = "investigations") -> str:
    """Open a case with the investigations team. IRREVERSIBLE.

    Use when the case needs a human with powers you do not have: a suspected
    mule network, a customer who cannot be reached, or a fraud call you can
    only make at medium confidence. Escalating everything is its own failure,
    so escalate what a person genuinely needs to look at.

    This pauses for human approval before it executes. If the decision is
    rejected, record that and do not call this tool again.

    Args:
        account_id: The account to escalate.
        reason: Why this needs a person, citing the evidence.
        escalate_to: Which desk. Defaults to 'investigations'.
    """
    if approval_mode() == "defer":
        with actions.cursor() as cur:
            cur.execute(
                "INSERT INTO actions (account_id, action, reason, state) VALUES (?,?,?,?)",
                (account_id, "escalate_case", f"{escalate_to}: {reason}", "pending_review"),
            )
        actions.log("disposition", "escalate_case:deferred", f"{account_id} -> {escalate_to}")
        return (
            f"QUEUED FOR REVIEW, not executed. An escalation of {account_id} to "
            f"{escalate_to} is recorded as awaiting an analyst. No case has been "
            f"opened. Say so in your final message."
        )

    with actions.cursor() as cur:
        cur.execute(
            "INSERT INTO actions (account_id, action, reason, state, approved_by) "
            "VALUES (?,?,?,?,?)",
            (account_id, "escalate_case", f"{escalate_to}: {reason}", "executed", "analyst"),
        )
    actions.log("disposition", "escalate_case:executed", f"{account_id} -> {escalate_to}")
    return f"EXECUTED after approval: {account_id} escalated to {escalate_to}. Reason: {reason}"


def load_disposition(account_id: str) -> Disposition | None:
    """Read a recorded verdict back. Used by reporting and the evidence audit."""
    rows = actions.query("SELECT * FROM dispositions WHERE account_id = ?", (account_id,))
    if not rows:
        return None
    r = dict(rows[0])
    return Disposition(
        account_id=r["account_id"],
        verdict=r["verdict"],
        confidence=r["confidence"],
        reasoning=r["reasoning"],
        action=r["action"],
        evidence=[EvidenceRef(**e) for e in json.loads(r["evidence_json"] or "[]")],
        information_required=json.loads(r["information_required"] or "[]"),
    )


DISPOSITION_TOOLS = [record_disposition, block_card, escalate_case]
