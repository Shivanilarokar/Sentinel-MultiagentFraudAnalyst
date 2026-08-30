"""The vocabulary of a disposition.

These types are the contract between the Disposition specialist and everything
downstream - the audit, the reports, the tests. Because they are Pydantic
models used as tool arguments, the schema is enforced by the tool-calling layer
itself: a malformed verdict is rejected and retried by the model rather than
landing in the database and being discovered later by a report generator.

`EvidenceRef` is the type that earns the defensibility marks. Every claim in a
disposition has to resolve to a row in the database, so every claim carries the
id of that row and, for anything written by a human, the words themselves.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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

    `ref_id` must be a real identifier - a note_id, txn_id, dispute_id,
    case_id, alert_id or device_id. `quote` must be text copied verbatim from
    the record, not a paraphrase, because the evidence audit re-reads the row
    and checks that the words are actually there.
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


class SpecialistFinding(BaseModel):
    """What one specialist reports back. Rendered to text before it crosses over.

    Kept deliberately small. The supervisor reads the rendered form, and the
    structured form is carried alongside so the report writer and the evidence
    audit can work from identifiers rather than re-parsing prose.
    """

    specialist: str
    headline: str = Field(description="One sentence: the finding, not a description of work.")
    findings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    assessment: str = Field(default="", description="This specialist's read, in its own terms.")
