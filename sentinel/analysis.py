"""Checks that run over recorded results rather than over the model's prose.

Three things live here, and they answer three different questions.

**Evidence.** A specialist's final message is a *claim*. `check_ref` turns it
into a checkable one: does the identifier exist, does it belong to *this*
account, and are the quoted words actually in that row?

**Lookalikes.** Which accounts does the arithmetic alone fail to separate, and
did we still call them differently? That is the whole point of reading the
notes, measured.

**Tokens.** What the sweep cost, and what one agent holding every tool would
have cost - derived from measured material, not quoted from the brief.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass

import tiktoken

from sentinel import queries
from sentinel.db import actions, db, usage_totals
from sentinel.policy import EvidenceRef

# ==========================================================================
# Evidence: does every citation resolve to a real row on the right account?
# ==========================================================================
#
# The ownership check is the one that catches the most damaging error. A model
# that was never told the real alert id will produce a well-formed one -
# `AL0001` instead of `AL0009` - which passes a format check and points at
# somebody else's case.
#
# This runs in two places: inside `record_disposition`, so a bad citation is
# refused while the model can still fix it, and over every recorded result
# afterwards to produce `reports/evidence_audit.md`.

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
    "device": "SELECT DISTINCT account_id FROM transactions WHERE device_id = ?",
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
        return RefCheck(kind, ref_id, False, False, False,
                        problem=f"{kind} '{ref_id}' does not exist in the database.")

    if account_id not in owners:
        others = ", ".join(sorted(owners)[:3])
        return RefCheck(kind, ref_id, True, False, False,
                        problem=f"{kind} '{ref_id}' exists but belongs to {others}, "
                                f"not {account_id}.")

    quote_sql = QUOTE_SQL.get(kind)
    if quote_sql and ref.quote.strip():
        stored = db.scalar(quote_sql, (ref_id,)) or ""
        fragment = _normalise(ref.quote)
        # A specialist may legitimately quote part of a long note, but it must
        # be part of that note.
        if fragment and fragment[:80] not in _normalise(stored):
            return RefCheck(kind, ref_id, True, True, False,
                            problem=f"the quote attributed to {kind} '{ref_id}' is not in "
                                    f'that record. The record actually reads: "{stored[:160]}"')

    return RefCheck(kind, ref_id, True, True, True)


def verify_refs(account_id: str, refs: list[EvidenceRef]) -> list[RefCheck]:
    """Check every citation on a disposition."""
    return [check_ref(account_id, ref) for ref in refs]


def refusal_for(account_id: str, refs: list[EvidenceRef]) -> str | None:
    """A tool-result refusal if any citation does not hold up, else None."""
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
    rows = [dict(r) for r in actions.query("SELECT * FROM dispositions ORDER BY account_id")]
    results, total, clean = [], 0, 0
    for row in rows:
        refs = [EvidenceRef(**e) for e in json.loads(row["evidence_json"] or "[]")]
        checks = verify_refs(row["account_id"], refs)
        total += len(checks)
        clean += sum(1 for c in checks if c.ok)
        results.append({
            "account_id": row["account_id"],
            "verdict": row["verdict"],
            "citations": len(checks),
            "failures": [c.problem for c in checks if not c.ok],
        })
    return {
        "accounts_audited": len(rows),
        "citations_checked": total,
        "citations_verified": clean,
        "pass_rate_pct": round(100 * clean / total, 1) if total else None,
        "accounts_with_failures": [r for r in results if r["failures"]],
        "detail": results,
    }


# ==========================================================================
# Lookalikes: accounts the numbers cannot separate
# ==========================================================================
#
# The queue contains matched pairs - same rules firing, same device-age
# profile, same geography shape - with opposite truths. A00985 and A00782 both
# fired R02 on a device registered hours before a large spend. One has a note
# filed before the incident recording a verified phone upgrade; the other has a
# note filed after it reporting a device registration the customer did not
# perform.
#
# The signature below is built from numeric facts *only* - deliberately no case
# notes, because the point is to group accounts the arithmetic cannot tell
# apart, then see whether we still called them differently and named why.


def _bucket(value: float | None, edges: tuple) -> str:
    if value is None:
        return "na"
    for i, edge in enumerate(edges):
        if value < edge:
            return f"b{i}"
    return f"b{len(edges)}"


def signature(account_id: str) -> str:
    """A signature built only from numbers a rules engine could see."""
    window = queries.incident_window(account_id)
    if not window:
        return "no-alerts"

    rules = "+".join(sorted((window["rules_fired"] or "").split(",")))
    velocity = queries.velocity(account_id, 24)
    baseline = queries.baseline(account_id)
    devices = queries.device_usage(account_id)

    youngest = min(
        (d["device_age_hours_at_incident"] for d in devices
         if d.get("device_age_hours_at_incident") is not None),
        default=None,
    )
    ratio = None
    if baseline.get("max_amount") and velocity.get("largest_amount"):
        ratio = velocity["largest_amount"] / baseline["max_amount"]

    return "|".join([
        rules,
        f"txn:{_bucket(velocity.get('txn_count'), (2, 4, 6, 10))}",
        f"ctry:{_bucket(velocity.get('distinct_countries'), (2, 3, 5))}",
        f"night:{'y' if (velocity.get('night_txns') or 0) > 0 else 'n'}",
        f"newdev:{'y' if youngest is not None and youngest < 24 else 'n'}",
        f"ratio:{_bucket(ratio, (1, 5, 20, 100))}",
    ])


def signature_groups(account_ids: list[str] | None = None) -> dict[str, list[str]]:
    """Group alerted accounts by identical signature."""
    groups: dict[str, list[str]] = defaultdict(list)
    for account_id in account_ids or queries.queue():
        groups[signature(account_id)].append(account_id)
    return {sig: ids for sig, ids in groups.items() if len(ids) > 1}


def _dispositions() -> dict[str, dict]:
    return {r["account_id"]: dict(r) for r in actions.query("SELECT * FROM dispositions")}


def _deciding_records(row: dict) -> list[str]:
    """The narrative records the reasoning actually leaned on."""
    refs = json.loads(row.get("evidence_json") or "[]")
    return [f"{r['kind']}:{r['ref_id']}" for r in refs
            if r["kind"] in ("case_note", "dispute", "prior_case")]


def separated_pairs(min_group: int = 2) -> list[dict]:
    """Pairs sharing a signature where our verdicts diverge.

    A divergence without a named reason is a coin flip rather than a reading,
    so pairs where both sides cite a specific record sort to the top.
    """
    verdicts = _dispositions()
    pairs = []
    for sig, accounts in signature_groups().items():
        scored = [a for a in accounts if a in verdicts]
        if len(scored) < min_group:
            continue
        for i, left in enumerate(scored):
            for right in scored[i + 1:]:
                a, b = verdicts[left], verdicts[right]
                if a["verdict"] == b["verdict"]:
                    continue
                pairs.append({
                    "signature": sig,
                    "a": {"account_id": left, "verdict": a["verdict"],
                          "confidence": a["confidence"],
                          "deciding_records": _deciding_records(a),
                          "reasoning": a["reasoning"]},
                    "b": {"account_id": right, "verdict": b["verdict"],
                          "confidence": b["confidence"],
                          "deciding_records": _deciding_records(b),
                          "reasoning": b["reasoning"]},
                })
    pairs.sort(
        key=lambda p: bool(p["a"]["deciding_records"]) + bool(p["b"]["deciding_records"]),
        reverse=True,
    )
    return pairs


def lookalike_summary() -> dict:
    groups = signature_groups()
    pairs = separated_pairs()
    return {
        "alerted_accounts": len(queries.queue()),
        "accounts_disposed": len(_dispositions()),
        "distinct_signatures_with_collisions": len(groups),
        "accounts_in_collision_groups": sum(len(v) for v in groups.values()),
        "separated_pairs": len(pairs),
        "pairs_where_both_sides_cite_a_record": sum(
            1 for p in pairs if p["a"]["deciding_records"] and p["b"]["deciding_records"]
        ),
    }


# ==========================================================================
# Tokens: what it cost, and what one agent would have cost
# ==========================================================================
#
# The single-agent figure is not a guess about a worse prompt. It is arithmetic
# about how a tool-calling loop accumulates context. An agent with every tool
# does not read an account's history once; it reads it, then re-sends it with
# the next call, and the one after. For an agent making `n` tool calls whose
# results are `r1..rn` tokens:
#
#     processed = SUM over i of ( system + tool_schemas + SUM over j<i of rj )
#
# which is quadratic in the material. Everything below is measured with
# tiktoken against the real tool outputs for real accounts.

_ENCODER = tiktoken.get_encoding("o200k_base")  # the gpt-4.1 family


def _read_tools() -> list:
    from sentinel.tools import BEHAVIOUR_TOOLS, CONTEXT_TOOLS, NETWORK_TOOLS

    return BEHAVIOUR_TOOLS + CONTEXT_TOOLS + NETWORK_TOOLS


def count(text: str) -> int:
    return len(_ENCODER.encode(text or ""))


def tool_schema_tokens() -> int:
    """What the tool definitions alone cost, re-sent on every model call.

    A single agent carries all of them every turn. Each specialist carries only
    its own domain's, which is a real part of the saving and easy to forget.
    """
    total = 0
    for tool in _read_tools():
        total += count(tool.name) + count(tool.description or "")
        try:
            total += count(str(tool.args_schema.model_json_schema()))
        except Exception:
            pass
    return total


def source_material(account_id: str) -> dict:
    """Run every read tool for one account and measure what comes back."""
    per_tool = {}
    for tool in _read_tools():
        try:
            per_tool[tool.name] = count(tool.invoke({"account_id": account_id}))
        except Exception:
            per_tool[tool.name] = 0
    return {"account_id": account_id, "per_tool": per_tool, "total": sum(per_tool.values())}


def single_agent_estimate(sample: int = 12, system_tokens: int = 1200) -> dict:
    """Model the one-agent cost from measured material.

    Charitable to the single agent: assumes each read tool is called exactly
    once per account, with no repeated calls and no wasted turns.
    """
    accounts = queries.queue()
    sampled = accounts[:: max(1, len(accounts) // sample)][:sample]
    schema = tool_schema_tokens()

    per_account = []
    for account_id in sampled:
        material = source_material(account_id)
        results = [t for t in material["per_tool"].values() if t]
        processed, seen = 0, 0
        for result_tokens in results:
            processed += system_tokens + schema + seen
            seen += result_tokens
        processed += system_tokens + schema + seen  # the final answer turn
        per_account.append({
            "account_id": account_id,
            "material_tokens": material["total"],
            "tool_calls": len(results),
            "processed_tokens": processed,
        })

    median_processed = int(statistics.median(p["processed_tokens"] for p in per_account))
    median_material = int(statistics.median(p["material_tokens"] for p in per_account))
    queue_size = len(accounts)

    measured = usage_totals()["overall"]
    measured_accounts = measured.get("accounts") or 0
    measured_total = measured.get("total_tokens") or 0
    per_acct = int(measured_total / measured_accounts) if measured_accounts else 0
    projected = median_processed * queue_size

    return {
        "sampled_accounts": len(per_account),
        "tool_schema_tokens_per_call": schema,
        "median_source_material_tokens_per_account": median_material,
        "median_single_agent_processed_tokens_per_account": median_processed,
        "projected_single_agent_tokens_for_queue": projected,
        "measured_accounts": measured_accounts,
        "measured_total_tokens": measured_total,
        "measured_tokens_per_account": per_acct,
        "projected_measured_tokens_for_queue": per_acct * queue_size,
        "ratio": round(projected / (per_acct * queue_size), 1) if per_acct else None,
        "detail": per_account,
    }


def cost_usd(tokens: int, input_rate: float = 0.40, output_rate: float = 1.60,
             output_share: float = 0.05) -> float:
    """Dollar cost at gpt-4.1-mini list rates, per million tokens."""
    output = tokens * output_share
    return round(((tokens - output) * input_rate + output * output_rate) / 1_000_000, 2)
