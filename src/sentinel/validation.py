"""The rules that are checked, rather than taught.

`policies/*.md` is the human half: documents an analyst can edit, that teach the
agent judgement it cannot infer. But a policy in a document is **advisory** — the
model reads it, and mostly complies.

Some rules must hold every time. Those live here, in Python, and
`record_disposition` refuses without them.

    The policy documents teach. The code guarantees.

Three layers, in the order they fire:

    1. Shape        is 'ALxxxx1' even the right shape for an alert id?
    2. Ownership    AL0001 is a real alert. Does it belong to THIS account?
    3. Quotes       did a human actually write the words being quoted?

Layer 2 is the one that catches real failures. A model that has read four
specialist findings will cite a plausible identifier it half-remembers, and
AL0001 is a perfectly valid alert id that belongs to somebody else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sentinel.db import query_one

# ---------------------------------------------------------------------------
# The vocabulary. Both lists are closed: a verdict outside them is not a verdict
# the desk can act on, and a free-text confidence cannot be sorted or counted.
# ---------------------------------------------------------------------------
VERDICTS = ("fraud", "legitimate", "insufficient_evidence")
CONFIDENCES = ("high", "medium", "low")

# Identifier shapes, measured off the database rather than guessed.
#   alert AL0001   note N00001   txn T0000001   dispute DP0001   prior case PC0001
ID_SHAPES = {
    "alert": re.compile(r"^AL\d{4}$"),
    "note": re.compile(r"^N\d{5}$"),
    "transaction": re.compile(r"^T\d{7}$"),
    "dispute": re.compile(r"^DP\d{4}$"),
    "prior_case": re.compile(r"^PC\d{4}$"),
}

EXAMPLE_ID = {
    "alert": "AL0170",
    "note": "N00080",
    "transaction": "T0107306",
    "dispute": "DP0001",
    "prior_case": "PC0001",
}

# Which table each evidence kind resolves to, and how to prove it belongs to the
# account under investigation. Anything not in here cannot be cited.
OWNERSHIP = {
    "alert":
        "SELECT alert_id FROM alerts WHERE alert_id = ? AND account_id = ?",
    "transaction":
        "SELECT txn_id FROM transactions WHERE txn_id = ? AND account_id = ?",
    "note":
        "SELECT n.note_id FROM case_notes n "
        "JOIN accounts a ON a.customer_id = n.customer_id "
        "WHERE n.note_id = ? AND a.account_id = ?",
    "dispute":
        "SELECT d.dispute_id FROM disputes d "
        "JOIN transactions t ON t.txn_id = d.txn_id "
        "WHERE d.dispute_id = ? AND t.account_id = ?",
    "prior_case":
        "SELECT p.case_id FROM prior_cases p "
        "JOIN accounts a ON a.customer_id = p.customer_id "
        "WHERE p.case_id = ? AND a.account_id = ?",
}

# Kinds that are something a human wrote, as opposed to something the system
# recorded. A `legitimate` verdict has to rest on at least one of these.
NARRATIVE_KINDS = ("note", "dispute", "prior_case")

# Where the quoted words live, so a quote can be checked against stored text.
QUOTE_SOURCE = {
    "note": "SELECT note AS text FROM case_notes WHERE note_id = ?",
    "dispute": "SELECT customer_statement AS text FROM disputes WHERE dispute_id = ?",
    "prior_case": "SELECT summary AS text FROM prior_cases WHERE case_id = ?",
}


@dataclass
class EvidenceRef:
    """One citation: what kind of record, which id, and the words relied on."""

    kind: str
    ref_id: str
    quote: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "id": self.ref_id, "quote": self.quote}


@dataclass
class Disposition:
    """A verdict on one account, with the evidence it rests on."""

    account_id: str
    verdict: str
    confidence: str
    reasoning: str
    evidence: list[EvidenceRef] = field(default_factory=list)
    missing: str = ""          # what would resolve it, when insufficient


# ===========================================================================
# The checks
# ===========================================================================
def check_shape(kind: str, ref_id: str) -> str | None:
    """Layer 1. Is this even the right shape for an id of that kind?

    Catches the two things models actually produce: a placeholder like ALxxxx1,
    and a rule id like R02 where an alert id belongs.
    """
    pattern = ID_SHAPES.get(kind)
    if not pattern:
        return f"{kind!r} is not a citable kind. Use one of: {', '.join(ID_SHAPES)}."
    if not pattern.match(ref_id):
        return (
            f"{ref_id!r} is not a valid {kind} id. Expected the form "
            f"{pattern.pattern.strip('^$')}, for example {EXAMPLE_ID[kind]}. "
            f"Do not invent or abbreviate identifiers."
        )
    return None


def check_ownership(kind: str, ref_id: str, account_id: str) -> str | None:
    """Layer 2. The row exists, but does it belong to THIS account?

    AL0001 is a real alert. It belongs to A00832. Citing it on A00985 is the most
    common way a confident-sounding verdict turns out to be about somebody
    else's case.
    """
    sql = OWNERSHIP.get(kind)
    if not sql:
        return f"{kind!r} cannot be resolved against the database."
    if query_one(sql, (ref_id, account_id)) is None:
        return (
            f"{kind} {ref_id} does not exist for account {account_id}. "
            f"Cite only records returned by your own tool calls."
        )
    return None


def check_quote(kind: str, ref_id: str, quote: str) -> str | None:
    """Layer 3. For anything a human wrote, are these really their words?

    Compared loosely — whitespace and case are normalised — because the point is
    to catch invention, not to police punctuation.
    """
    if not quote or kind not in QUOTE_SOURCE:
        return None
    row = query_one(QUOTE_SOURCE[kind], (ref_id,))
    if row is None:
        return f"{kind} {ref_id} has no stored text to quote."

    def norm(s: str) -> str:
        return " ".join(s.lower().split())

    if norm(quote) not in norm(row["text"]):
        return (
            f"The quoted words are not in {kind} {ref_id}. Quote the stored text "
            f"exactly, or cite the id without a quote."
        )
    return None


def validate(d: Disposition) -> list[str]:
    """Run every check. Returns a list of problems; empty means it may be filed.

    The messages are written to be acted on: each says what was wrong and what to
    do instead, because the model reads them and tries again.
    """
    problems: list[str] = []

    if d.verdict not in VERDICTS:
        problems.append(f"verdict must be one of {VERDICTS}, got {d.verdict!r}.")
    if d.confidence not in CONFIDENCES:
        problems.append(f"confidence must be one of {CONFIDENCES}, got {d.confidence!r}.")
    if len(d.reasoning.split()) < 15:
        problems.append(
            "reasoning is too short to be defensible. State what fired, what the "
            "evidence said, and why it settles the question."
        )

    for ref in d.evidence:
        for problem in (
            check_shape(ref.kind, ref.ref_id),
            check_ownership(ref.kind, ref.ref_id, d.account_id),
            check_quote(ref.kind, ref.ref_id, ref.quote),
        ):
            if problem:
                problems.append(problem)
                break   # one problem per citation is enough to act on

    # A `legitimate` verdict means something explained the alert away, and only a
    # human's words can do that. Amounts and counts cannot.
    if d.verdict == "legitimate":
        if not any(e.kind in NARRATIVE_KINDS for e in d.evidence):
            problems.append(
                "a 'legitimate' verdict must cite something a human wrote - a case "
                "note, a dispute statement or a prior case. Numbers alone cannot "
                "explain an alert away. If the file holds no such record, the "
                "honest verdict is 'insufficient_evidence'."
            )

    # `insufficient_evidence` is a real verdict here, not a hiding place. It has
    # to name the artefact that would settle the question.
    if d.verdict == "insufficient_evidence":
        if len(d.missing.split()) < 5:
            problems.append(
                "'insufficient_evidence' must name what would resolve it - for "
                "example 'a customer callback confirming the 27 Feb transfers', or "
                "'device registration logs for D000123'. Say what is missing."
            )

    return problems


def check_action(action: str, verdict: str) -> str | None:
    """No action may contradict its own verdict.

    Severity has to be proportionate: card blocks are for cases where money is
    still moving. Blocking the card of an account you just called legitimate is
    the failure this catches, and it is a real harm with a real complaint
    attached.
    """
    if action in ("block_card", "escalate_case") and verdict == "legitimate":
        return (
            f"REFUSED: {action!r} contradicts a 'legitimate' verdict. If the account "
            f"is legitimate, close it and record why. If you believe an action is "
            f"needed, the verdict is not 'legitimate'."
        )
    if action == "block_card" and verdict == "insufficient_evidence":
        return (
            "REFUSED: 'block_card' is irreversible for the customer and this verdict "
            "says the file is unresolved. Escalate for review instead, and name what "
            "would settle it."
        )
    return None
