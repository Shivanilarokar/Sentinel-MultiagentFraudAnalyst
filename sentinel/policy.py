"""The vocabulary of a disposition, and the rules that are checked rather than taught.

`skills/*.md` is the human half: documents an analyst can edit, that teach
judgement the model cannot infer. But a policy in a document is advisory - the
model reads it, and mostly complies.

Some rules have to hold every time. Those live here, and `record_disposition`
refuses without them.

    The skills teach. This file guarantees.

Keep the two in sync: every rule below is also stated, marked as a HARD RULE,
in the document that governs it, so an agent can comply in advance rather than
discovering the refusal by trial and error.

The types come first because they are the contract between the Disposition
specialist and everything downstream. Being Pydantic models used as tool
arguments, the schema is enforced by the tool-calling layer itself: a malformed
verdict is rejected and retried by the model rather than landing in the
database and being discovered later by a report generator.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

# ==========================================================================
# Types
# ==========================================================================

Verdict = Literal["fraud", "legitimate", "insufficient_evidence"]
Confidence = Literal["high", "medium", "low"]
Action = Literal["none", "monitor", "block_card", "escalate_case"]
EvidenceKind = Literal["case_note", "dispute", "prior_case", "transaction", "alert", "device"]

# Actions that cannot be undone, and therefore cannot happen without a human.
IRREVERSIBLE: set[str] = {"block_card", "escalate_case"}

VERDICTS: tuple[str, ...] = ("fraud", "legitimate", "insufficient_evidence")
CONFIDENCES: tuple[str, ...] = ("high", "medium", "low")
ACTIONS: tuple[str, ...] = ("none", "monitor", "block_card", "escalate_case")


class EvidenceRef(BaseModel):
    """One citation, resolvable back to a database row.

    `ref_id` must be a real identifier. `quote` must be text copied verbatim
    from the record, not a paraphrase, because the evidence audit re-reads the
    row and checks that the words are actually there.
    """

    kind: EvidenceKind = Field(description="Which table this citation comes from.")
    ref_id: str = Field(
        description="The exact identifier, e.g. 'N00080', 'T0107306', 'DP0012', 'AL0170'."
    )
    quote: str = Field(
        default="",
        description=(
            "For a case note, dispute or prior case: a verbatim fragment of the "
            "text, copied exactly. Leave empty for transactions and alerts."
        ),
    )
    detail: str = Field(
        default="",
        description="What this record shows, in one clause. e.g. 'device 6h old at incident'.",
    )


class Disposition(BaseModel):
    """A finished verdict on one account."""

    account_id: str
    verdict: Verdict
    confidence: Confidence
    reasoning: str
    action: Action
    evidence: list[EvidenceRef] = Field(default_factory=list)
    information_required: list[str] = Field(default_factory=list)


# ==========================================================================
# The rules
# ==========================================================================

MIN_REASONING_CHARS = 120

# Identifier shapes, taken from the database itself. A model that has not been
# given a real id will happily invent a plausible-looking one - 'ALxxxx1',
# 'T000000', or a rule id where an alert id belongs. Checking the shape catches
# that at write time, while the model can still fix it.
ID_PATTERNS: dict[str, re.Pattern] = {
    "alert": re.compile(r"^AL\d{4}$"),          # AL0170
    "transaction": re.compile(r"^T\d{7}$"),     # T0107306
    "case_note": re.compile(r"^N\d{5}$"),       # N00080
    "dispute": re.compile(r"^DP\d{4}$"),        # DP0012
    "prior_case": re.compile(r"^PC\d{4}$"),     # PC0044
    "device": re.compile(r"^D[X\d]\d{4,5}$"),   # D009851 or DX01444
}

ID_EXAMPLES: dict[str, str] = {
    "alert": "AL0170",
    "transaction": "T0107306",
    "case_note": "N00080",
    "dispute": "DP0012",
    "prior_case": "PC0044",
    "device": "DX01444",
}

# Which actions each verdict may carry. Blocking a card on an account you have
# just called legitimate is not a judgement call, it is a contradiction.
ALLOWED_ACTIONS: dict[str, set[str]] = {
    "fraud": {"block_card", "escalate_case", "monitor"},
    "legitimate": {"none", "monitor"},
    "insufficient_evidence": {"monitor", "escalate_case"},
}

TEXT_EVIDENCE_KINDS = {"case_note", "dispute", "prior_case"}


def check_disposition(
    verdict: str,
    confidence: str,
    reasoning: str,
    action: str,
    evidence: list[EvidenceRef],
    information_required: list[str],
) -> str | None:
    """Return a refusal message if the disposition breaks a hard rule, else None.

    The message is written to be actionable: it says what is wrong and what to
    do about it, because it goes back to the model as a tool result and a vague
    refusal produces a confused retry.
    """
    if verdict not in VERDICTS:
        return f"REFUSED: verdict must be one of {', '.join(VERDICTS)}. Got '{verdict}'."

    if confidence not in CONFIDENCES:
        return f"REFUSED: confidence must be one of {', '.join(CONFIDENCES)}. Got '{confidence}'."

    if action not in ACTIONS:
        return f"REFUSED: action must be one of {', '.join(ACTIONS)}. Got '{action}'."

    allowed = ALLOWED_ACTIONS[verdict]
    if action not in allowed:
        return (
            f"REFUSED: action '{action}' is not permitted for a '{verdict}' verdict. "
            f"Permitted here: {', '.join(sorted(allowed))}. "
            f"If you believe the action is right, your verdict is wrong."
        )

    if len(reasoning.strip()) < MIN_REASONING_CHARS:
        return (
            f"REFUSED: reasoning is {len(reasoning.strip())} characters. A disposition has "
            f"to be defensible to a compliance officer who cannot see your tools, so it "
            f"needs at least {MIN_REASONING_CHARS}. State what fired, what the behaviour "
            f"showed, what the file said, and which of those decided it."
        )

    # An honest 'I cannot tell' names what would settle it. A bare
    # insufficient_evidence is a refusal to decide, which scores as badly as a
    # confident guess.
    if verdict == "insufficient_evidence" and not [
        item for item in information_required if item.strip()
    ]:
        return (
            "REFUSED: a verdict of insufficient_evidence must name what would resolve it. "
            "Populate information_required with the specific missing artefacts, e.g. "
            "'a case note explaining the device registered on 27 Feb' or 'customer "
            "confirmation of whether they travelled to MY in this window'. "
            "'Unclear' or 'more information' is not an answer."
        )

    if verdict in ("fraud", "legitimate") and not evidence:
        return (
            f"REFUSED: a '{verdict}' verdict must cite the records it rests on. "
            f"Add at least one EvidenceRef with the real note_id, txn_id, dispute_id "
            f"or alert_id you are relying on."
        )

    # A legitimate verdict is a claim that somebody explained the behaviour.
    # That claim has to point at the text making the explanation.
    if verdict == "legitimate" and not any(e.kind in TEXT_EVIDENCE_KINDS for e in evidence):
        return (
            "REFUSED: 'legitimate' asserts that the activity was explained, so it must "
            "cite the text that explains it - a case_note, dispute or prior_case. "
            "If no such record exists, the honest verdict is insufficient_evidence, "
            "not legitimate."
        )

    for ref in evidence:
        if not ref.ref_id.strip():
            return "REFUSED: every EvidenceRef needs a real ref_id. One was empty."

        pattern = ID_PATTERNS.get(ref.kind)
        article = "An" if ref.kind[0] in "aeiou" else "A"
        if pattern and not pattern.match(ref.ref_id.strip()):
            return (
                f"REFUSED: '{ref.ref_id}' is not a valid {ref.kind} identifier. "
                f"{article} {ref.kind} id looks like {ID_EXAMPLES[ref.kind]}. "
                f"You have written a placeholder or the wrong kind of id - a rule id "
                f"(R02) is not an alert id (AL0170). Use the exact identifier from the "
                f"specialist findings, or drop this citation entirely. Never invent one: "
                f"a fabricated id looks like evidence and is not."
            )

        if ref.kind in TEXT_EVIDENCE_KINDS and not ref.quote.strip():
            return (
                f"REFUSED: evidence {ref.ref_id} is a {ref.kind}, so it must carry a "
                f"verbatim quote from the record. Copy the deciding sentence exactly; "
                f"the evidence audit re-reads the row and checks the words are there."
            )

    return None


def requires_approval(action: str) -> bool:
    """True if this action cannot be taken without a human.

    Derived in code from the action itself, never asked of the model. An agent
    that could decide its own actions were reversible would be the whole
    problem the approval gate exists to prevent.
    """
    return action in IRREVERSIBLE
