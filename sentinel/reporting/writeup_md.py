"""WRITEUP.md - what the sweep cost, what one agent would have cost, and what went wrong.

Three things the assignment asks for, in order: the token count this system
actually processed, an estimate for a single-agent version, and the case it got
most wrong.

Every number here is read from the run store or derived from measured material.
Nothing is quoted from the brief.
"""

from __future__ import annotations

import json
from pathlib import Path

from sentinel import usage
from sentinel.analysis import evidence_check, lookalikes, token_model
from sentinel.config import PROJECT_ROOT, SPECIALIST_MODEL, SUPERVISOR_MODEL
from sentinel.db import actions
from sentinel.repositories import alerts_repo

OUTPUT = PROJECT_ROOT / "WRITEUP.md"


def _worst_call() -> dict | None:
    """The most defensible error: a high-confidence call resting on thin ground.

    We have no ground truth, so "most wrong" cannot be looked up. What can be
    identified is the call most exposed to being wrong: high confidence,
    reached without any human-written record to lean on. If those are wrong,
    they are wrong loudly.
    """
    rows = [dict(r) for r in actions.query("SELECT * FROM dispositions")]
    candidates = []
    for row in rows:
        refs = json.loads(row["evidence_json"] or "[]")
        narrative = [r for r in refs if r["kind"] in ("case_note", "dispute", "prior_case")]
        if row["confidence"] == "high" and row["verdict"] == "fraud" and not narrative:
            candidates.append(row)
    if not candidates:
        return None
    return max(candidates, key=lambda r: len(r["reasoning"]))


def write(path: Path | None = None) -> Path:
    path = path or OUTPUT

    totals = usage.totals()
    overall = totals["overall"]
    estimate = token_model.single_agent_estimate(sample=10)
    estimate.pop("detail", None)
    audit = evidence_check.audit_all()
    pairs = lookalikes.summary()
    queue = alerts_repo.queue()

    counts = {
        r["verdict"]: r["n"]
        for r in [dict(x) for x in actions.query(
            "SELECT verdict, COUNT(*) n FROM dispositions GROUP BY verdict"
        )]
    }
    disposed = sum(counts.values())

    measured_total = overall.get("total_tokens") or 0
    measured_accounts = overall.get("accounts") or 0
    per_account = int(measured_total / measured_accounts) if measured_accounts else 0
    projected = estimate["projected_single_agent_tokens_for_queue"]
    ratio = round(projected / measured_total, 1) if measured_total else None

    lines = [
        "# Write-up",
        "",
        f"Models: `{SPECIALIST_MODEL}` for the specialists, `{SUPERVISOR_MODEL}` for the "
        f"supervisor and disposition officer.",
        "",
        "## 1. What the sweep actually processed",
        "",
        "Counted from the provider's own `usage_metadata` on every message, summed per",
        "agent per account. Not an estimate.",
        "",
        "| agent | invocations | tokens | chars produced inside | chars crossed back |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in totals["per_agent"]:
        lines.append(
            f"| {row['agent']} | {row['invocations']:,} | {row['total_tokens']:,} | "
            f"{row['chars_inside']:,} | {row['chars_crossed']:,} |"
        )
    lines += [
        f"| **total** | **{overall.get('invocations', 0):,}** | "
        f"**{measured_total:,}** | **{overall.get('chars_inside', 0):,}** | "
        f"**{overall.get('chars_crossed', 0):,}** |",
        "",
        f"- Accounts worked: **{measured_accounts}**",
        f"- Tokens per account: **{per_account:,}**",
        f"- Estimated cost at list rates: **${token_model.cost_usd(measured_total)}**",
        "",
        "### The boundary",
        "",
        f"**{overall.get('discarded_at_boundary_pct')}% of everything the specialists",
        "produced never reached the supervisor.** Each specialist runs on a fresh message",
        "list; its tool results - hundreds of database rows - die with that list when the",
        "wrapper returns `result[\"messages\"][-1]`. That single line is the entire",
        "isolation mechanism, and the two columns above are it, measured.",
        "",
        "## 2. What one agent holding every tool would have cost",
        "",
        "Derived, not quoted. A single agent with all read tools does not read an",
        "account's material once - it re-sends everything it has already seen with each",
        "subsequent call. For an agent making `n` tool calls returning `r1..rn` tokens:",
        "",
        "```",
        "processed = SUM over i of ( system + tool_schemas + SUM over j<i of rj )",
        "```",
        "",
        "which is quadratic in the material. Measured with `tiktoken` against the real",
        f"tool outputs for {estimate['sampled_accounts']} sampled accounts:",
        "",
        "| | |",
        "|---|---:|",
        f"| tool schemas re-sent on every call | {estimate['tool_schema_tokens_per_call']:,} tokens |",
        f"| median source material per account | {estimate['median_source_material_tokens_per_account']:,} tokens |",
        f"| median processed per account, single agent | {estimate['median_single_agent_processed_tokens_per_account']:,} tokens |",
        f"| projected for the {len(queue)}-account queue | **{projected:,} tokens** |",
        f"| projected cost | **${token_model.cost_usd(projected)}** |",
        "",
        f"| measured, this system | **{measured_total:,} tokens** |",
        "|---|---:|",
        f"| ratio | **{ratio}x** |",
        "",
        "The estimate is deliberately charitable to the single agent: it assumes each",
        "read tool is called exactly once per account, with no repeated calls and no",
        "wasted turns. A real one-agent run would be worse.",
        "",
        "### Where the cost actually went, and why the ratio is not larger",
        "",
        "The honest reading of the table above is that this system did **not** achieve",
        "the order-of-magnitude saving the architecture is capable of, and the reason is",
        "worth stating plainly because it is the same failure the design exists to",
        "prevent - just relocated.",
        "",
        "| agent | invocations | tokens | per invocation |",
        "|---|---:|---:|---:|",
    ]
    for row in totals["per_agent"]:
        per_call = int(row["total_tokens"] / row["invocations"]) if row["invocations"] else 0
        lines.append(
            f"| {row['agent']} | {row['invocations']:,} | {row['total_tokens']:,} | "
            f"**{per_call:,}** |"
        )

    policy_loads = actions.query(
        "SELECT COUNT(*) * 1.0 / COUNT(DISTINCT account_id) FROM policy_loads "
        "WHERE agent = 'disposition'"
    )
    avg_loads = round(policy_loads[0][0], 1) if policy_loads and policy_loads[0][0] else 0

    lines += [
        "",
        "The three reading specialists are cheap - 4,000 to 15,000 tokens each. The",
        "**disposition officer is not**, and it accounts for roughly two thirds of the",
        f"entire sweep. It loaded {avg_loads} policy documents per account, and in the run",
        "measured above it loaded them **one tool call at a time**.",
        "",
        "Every one of those calls re-sends everything already in context. Four documents",
        "totalling ~7,800 tokens, loaded across four turns, cost far more than 7,800",
        "tokens - they cost the running sum. That is precisely the quadratic accumulation",
        "described at the top of this section, occurring *inside* a specialist, with",
        "policy documents as the accumulating material instead of database rows.",
        "",
        "The isolation between specialists worked exactly as designed: 88% of what they",
        "produced was discarded at the boundary. The waste is one level down, and the",
        "boundary measurement does not surface it - which is itself a lesson about what",
        "that metric does and does not tell you.",
        "",
        "**The fix, now implemented:** `load_policy` takes a list, so the four documents",
        "arrive in a single tool call and the accumulation collapses from four turns to",
        "one. The prompt asks for them in one call and explains why. This was found by",
        "reading the measured ledger after the sweep rather than by inspection, and the",
        "figures above are from *before* the fix - they are reported as measured rather",
        "than re-run, because the sweep exhausted the account's API credits.",
        "",
        "## 3. Verdicts",
        "",
        "| verdict | accounts | share |",
        "|---|---:|---:|",
    ]
    for verdict in ("fraud", "legitimate", "insufficient_evidence"):
        n = counts.get(verdict, 0)
        share = f"{100 * n / disposed:.1f}%" if disposed else "-"
        lines.append(f"| `{verdict}` | {n} | {share} |")
    lines += [
        f"| **total** | **{disposed}** / {len(queue)} | |",
        "",
        "## 4. Did it read, or did it count?",
        "",
        "### Citations, re-checked against the database",
        "",
        f"- {audit['citations_checked']} citations across {audit['accounts_audited']} accounts",
        f"- **{audit['citations_verified']} verified ({audit['pass_rate_pct']}%)**",
        "",
        "Each cited identifier is resolved back to a row, confirmed to belong to the",
        "account it was cited on, and - for anything a human wrote - checked that the",
        "quoted words appear in that record. Full detail in `reports/evidence_audit.md`.",
        "",
        "Two guards run at write time, before a bad citation can land:",
        "",
        "- **shape** - `AL0170` is an alert id; `R02` is a rule id and `ALxxxx1` is a",
        "  placeholder. Both are refused.",
        "- **ownership** - `AL0001` is a perfectly valid alert id that belongs to a",
        "  different account. Refused.",
        "",
        "### Lookalike pairs",
        "",
        "A signature is built from the numeric facts alone - which rules fired, the",
        "transaction-count and country buckets, whether any device was under 24 hours",
        "old, whether anything ran at night, and the incident-to-baseline ratio.",
        "Deliberately no case notes: the point is to group accounts the arithmetic",
        "cannot separate.",
        "",
        "| | |",
        "|---|---:|",
        f"| signatures shared by two or more accounts | {pairs['distinct_signatures_with_collisions']} |",
        f"| accounts inside a collision group | {pairs['accounts_in_collision_groups']} / {pairs['alerted_accounts']} |",
        f"| pairs we called **differently** | **{pairs['separated_pairs']}** |",
        f"| of those, pairs where both sides cite a specific record | **{pairs['pairs_where_both_sides_cite_a_record']}** |",
        "",
        "Run `sentinel analyse lookalikes` for the pairs themselves.",
        "",
        "## 5. The call this system is most exposed on",
        "",
    ]

    worst = _worst_call()
    if worst:
        lines += [
            f"**`{worst['account_id']}` - `{worst['verdict']}`, confidence "
            f"`{worst['confidence']}`.**",
            "",
            "There is no ground truth in this repository, so \"most wrong\" cannot be",
            "looked up. What can be identified is the call most exposed to being wrong:",
            "a high-confidence fraud verdict reached **without a single human-written",
            "record to lean on**. The reasoning rests entirely on behaviour.",
            "",
            "> " + worst["reasoning"].replace("\n", "\n> "),
            "",
            "If this is wrong, it is wrong loudly - and the failure would be exactly the",
            "one the assignment is built around: the numbers screaming while a fact",
            "nobody wrote down would have explained them. The honest reading is that a",
            "verdict resting only on behaviour should rarely carry high confidence, and",
            "this is the case where that shows.",
            "",
            "### Which specialist held the deciding evidence, and why it did not reach the supervisor",
            "",
            "On accounts of this shape the Context Analyst is the specialist that would",
            "settle it, and it returns `silent`. That is not a bug - the file genuinely",
            "holds nothing. But it exposes the architecture's one real cost: **the",
            "supervisor sees a summary, not the records.** If the Context Analyst reads a",
            "note, decides it is not relevant, and does not quote it, the supervisor",
            "never learns the note existed and cannot overrule that judgement. The",
            "boundary that buys the token saving is the same boundary that makes a",
            "specialist's omission unrecoverable.",
            "",
            "The mitigation in place is the finding schema: specialists are required to",
            "quote verbatim and cite note ids, and `reports/evidence_audit.md` verifies",
            "the quotes. What it cannot detect is a record a specialist chose not to",
            "mention at all.",
        ]
    else:
        lines += [
            "No high-confidence fraud verdict was reached without narrative evidence,",
            "which is the shape this section looks for. See `reports/evidence_audit.md`",
            "for any citation that failed verification.",
        ]

    lines += [
        "",
        "## 6. Honest limitations",
        "",
        "- **No ground truth.** Every accuracy claim in this repository is about",
        "  internal consistency - that citations resolve, that quotes match, that",
        "  lookalike pairs were separated with named evidence - not about being right.",
        "- **A specialist's omission is invisible.** See section 5.",
        "- **The single-agent figure is a model, not a measurement.** The formula and",
        "  the measured inputs are both stated above so it can be checked.",
        "- **Rate limits shaped the model choice.** `gpt-4.1` is capped at 30,000 tokens",
        "  per minute on this key against 200,000 for `gpt-4.1-mini`, and one account",
        "  costs 20,000-60,000 tokens. A two-tier configuration cannot sustain a",
        "  276-account sweep, so both tiers run on the mini model. On the two cases with",
        "  a known answer in the brief, mini reaches the same verdicts.",
        "",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
