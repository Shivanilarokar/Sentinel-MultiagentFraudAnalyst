"""Measurement, for the write-up and for arguing with the design.

Three questions this answers, all from recorded data rather than estimates:

    1. Is context actually isolated?     how much a specialist produced,
                                          against how much crossed back
    2. What did the sweep really cost?    the token ledger, summed
    3. What would one agent have cost?    the counterfactual, modelled from
                                          the same measured content

Question 3 cannot be measured directly without running the expensive version,
so it is *modelled* from real numbers. The model is stated openly below rather
than hidden behind a round figure, because an unexplained multiplier is not an
argument.

    python -m sentinel.analysis
"""

from __future__ import annotations

from sentinel import db
from sentinel.config import SPECIALIST_MODEL, SUPERVISOR_MODEL

# gpt-4.1-mini and gpt-4.1 both tokenise at roughly 4 characters per token for
# English prose and tabular output. Used only where a character count has to be
# turned into a token count; everywhere else the ledger's real counts are used.
CHARS_PER_TOKEN = 4

# USD per million tokens, as published.
PRICING = {
    "gpt-4.1-mini": {"in": 0.40, "out": 1.60},
    "gpt-4.1": {"in": 2.00, "out": 8.00},
}

# Which model each agent runs on. Read from config rather than hardcoded, so
# changing .env changes the costing too. Hardcoding it here once produced a
# report that priced a mini run at gpt-4.1 rates, which is exactly the kind of
# number a write-up should not contain.
def agent_model(agent: str) -> str:
    """The model an agent runs on, per the current configuration."""
    return SUPERVISOR_MODEL if agent in ("disposition", "supervisor") else SPECIALIST_MODEL

ALERTED_ACCOUNTS = 276


def accounts_measured() -> int:
    """How many distinct accounts the ledger covers.

    Every per-account figure divides by this, so it is read once rather than
    re-queried at each call site where it could drift.
    """
    return db.fetch("SELECT COUNT(DISTINCT account_id) n FROM token_ledger")[0]["n"] or 1


def cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """USD for a given number of tokens on a given model."""
    p = PRICING.get(model, PRICING["gpt-4.1-mini"])
    return tokens_in / 1e6 * p["in"] + tokens_out / 1e6 * p["out"]


# ===========================================================================
# 1. Isolation
# ===========================================================================
def isolation_report(account_id: str | None = None) -> dict:
    """How much of what the specialists produced never reached the supervisor.

    `findings` holds exactly what crossed the boundary: one final message per
    specialist. Everything a specialist read to get there — every table of
    transactions, every case note, every policy document — lived and died inside
    its own `.invoke()`.

    The produced side is reconstructed from the token ledger, which counted the
    real input the specialist processed.
    """
    where, params = ("WHERE account_id = ?", (account_id,)) if account_id else ("", ())

    crossed = db.fetch(
        f"SELECT specialist, SUM(LENGTH(finding)) chars, COUNT(*) n "
        f"FROM findings {where} GROUP BY specialist", params)
    produced = db.fetch(
        f"SELECT agent, SUM(input_tokens) tin, SUM(output_tokens) tout, COUNT(*) n "
        f"FROM token_ledger {where} GROUP BY agent", params)

    crossed_chars = sum(r["chars"] for r in crossed)
    produced_tokens = sum(r["tin"] for r in produced)
    produced_chars = produced_tokens * CHARS_PER_TOKEN

    return {
        "specialists": {r["specialist"]: r["chars"] for r in crossed},
        "produced_chars": produced_chars,
        "crossed_chars": crossed_chars,
        "discarded_pct": (round(100 * (1 - crossed_chars / produced_chars), 1)
                          if produced_chars else 0.0),
        "by_agent": {r["agent"]: dict(r) for r in produced},
    }


# ===========================================================================
# 2. What it really cost
# ===========================================================================
def token_report() -> dict:
    """The ledger, summed per agent, with the money attached."""
    rows = db.fetch(
        "SELECT agent, SUM(input_tokens) tin, SUM(output_tokens) tout, "
        "COUNT(*) calls "
        "FROM token_ledger GROUP BY agent")

    agents = {}
    for r in rows:
        model = agent_model(r["agent"])
        agents[r["agent"]] = {
            "model": model,
            "input": r["tin"],
            "output": r["tout"],
            "calls": r["calls"],
            "cost": cost(model, r["tin"], r["tout"]),
        }

    accounts = accounts_measured()
    total_in = sum(a["input"] for a in agents.values())
    total_out = sum(a["output"] for a in agents.values())
    total_cost = sum(a["cost"] for a in agents.values())

    return {
        "agents": agents,
        "accounts_measured": accounts,
        "input": total_in,
        "output": total_out,
        "cost": total_cost,
        "per_account_tokens": (total_in + total_out) / accounts,
        "per_account_cost": total_cost / accounts,
        "projected_276_tokens": (total_in + total_out) / accounts * ALERTED_ACCOUNTS,
        "projected_276_cost": total_cost / accounts * ALERTED_ACCOUNTS,
    }


# ===========================================================================
# 3. The single-agent counterfactual
# ===========================================================================
def single_agent_estimate() -> dict:
    """What one agent holding all 17 tools would have processed instead.

    The model, stated openly:

    A specialist makes T tool calls and therefore T+1 model calls, and on call i
    it re-sends everything it has seen so far. That re-processing is already in
    our measured input figure, per isolated context.

    One flat agent does the same work in ONE context. It makes the same total
    number of tool calls, but every call re-sends the accumulated output of
    every previous call, across all four domains rather than within one. If the
    four contexts each carry content C_k over T_k calls, the isolated cost is
    roughly sum(C_k * T_k / 2), while the flat cost is (sum C_k) * (sum T_k) / 2.

    The cross terms are the whole difference: the behaviour analyst's 80 rows of
    transactions get reprocessed on every later call about case notes, devices
    and disposition, and vice versa.
    """
    rows = db.fetch(
        "SELECT agent, SUM(input_tokens) tin, SUM(model_calls) calls "
        "FROM token_ledger WHERE agent != 'supervisor' GROUP BY agent")
    if not rows:
        return {}

    accounts = accounts_measured()

    # For one context: with T model calls over content that grows to C tokens,
    # the input summed across calls is about C * (T + 1) / 2. Invert that to
    # recover C, the content the context actually ended up holding.
    contexts = []
    for r in rows:
        calls = max(r["calls"], 1) / accounts
        measured_input = r["tin"] / accounts
        content = 2 * measured_input / (calls + 1)
        contexts.append({"agent": r["agent"], "content": content, "calls": calls})

    isolated_input = sum(c["content"] * (c["calls"] + 1) / 2 for c in contexts)

    # One flat agent holds every domain's content in a single context and makes
    # the same total number of model calls, so every call re-processes
    # everything read so far across ALL domains. The cross terms are the whole
    # difference: 80 rows of transactions get reprocessed on every later call
    # about case notes, devices and disposition, and the other way round.
    total_content = sum(c["content"] for c in contexts)
    total_calls = sum(c["calls"] for c in contexts)
    flat_input = total_content * (total_calls + 1) / 2

    return {
        "contexts": contexts,
        "isolated_input_per_account": isolated_input,
        "flat_input_per_account": flat_input,
        "total_content": total_content,
        "total_calls": total_calls,
        "multiplier": round(flat_input / isolated_input, 1) if isolated_input else 0,
        "isolated_276": isolated_input * ALERTED_ACCOUNTS,
        "flat_276": flat_input * ALERTED_ACCOUNTS,
        "isolated_cost_276": cost("gpt-4.1-mini", isolated_input * ALERTED_ACCOUNTS, 0),
        "flat_cost_276": cost("gpt-4.1", flat_input * ALERTED_ACCOUNTS, 0),
    }


# ===========================================================================
# Report
# ===========================================================================
def main() -> None:
    print("\nTOKEN AND ISOLATION ANALYSIS")
    print("=" * 74)

    t = token_report()
    if not t["agents"]:
        print("\n  No runs recorded yet. Run a case first.\n")
        return

    print(f"\nMEASURED, over {t['accounts_measured']} account(s):\n")
    print(f"  {'agent':<14} {'model':<14} {'calls':>6} {'input':>10} {'output':>8} {'cost':>9}")
    print(f"  {'-'*14} {'-'*14} {'-'*6} {'-'*10} {'-'*8} {'-'*9}")
    for name, a in sorted(t["agents"].items()):
        print(f"  {name:<14} {a['model']:<14} {a['calls']:>6} {a['input']:>10,} "
              f"{a['output']:>8,} {'$'+format(a['cost'], '.4f'):>9}")
    print(f"  {'-'*14} {'-'*14} {'-'*6} {'-'*10} {'-'*8} {'-'*9}")
    print(f"  {'TOTAL':<14} {'':<14} {'':>6} {t['input']:>10,} {t['output']:>8,} "
          f"{'$'+format(t['cost'], '.4f'):>9}")

    print(f"\n  per account : {t['per_account_tokens']:,.0f} tokens, "
          f"${t['per_account_cost']:.4f}")
    print(f"  projected   : {t['projected_276_tokens']:,.0f} tokens over 276 accounts, "
          f"${t['projected_276_cost']:.2f}")

    print(f"\n{'-' * 74}")
    print("ISOLATION - what the specialists produced, against what crossed back:\n")
    iso = isolation_report()
    for name, chars in sorted(iso["specialists"].items()):
        print(f"  {name:<14} final message {chars:>7,} chars")
    print(f"\n  produced inside specialists : {iso['produced_chars']:>9,} chars")
    print(f"  crossed the boundary        : {iso['crossed_chars']:>9,} chars")
    print(f"  discarded                   : {iso['discarded_pct']:>9}%")
    print("\n  Everything discarded lived inside one .invoke() and died with it.")
    print("  The supervisor's model never saw a single database row.")

    print(f"\n{'-' * 74}")
    print("THE COUNTERFACTUAL - one agent holding all 17 tools:\n")
    s = single_agent_estimate()
    if s:
        print("  content each isolated context ended up holding:")
        for c in s["contexts"]:
            print(f"    {c['agent']:<12} {c['content']:>8,.0f} tokens "
                  f"over {c['calls']:.1f} model calls")
        print(f"\n  all four domains     : {s['total_content']:>10,.0f} tokens of content, "
              f"{s['total_calls']:.0f} model calls")
        print()
        print(f"  isolated specialists : {s['isolated_input_per_account']:>10,.0f} "
              f"input tokens per account")
        print(f"  one flat agent       : {s['flat_input_per_account']:>10,.0f} "
              f"input tokens per account")
        print(f"  multiplier           : {s['multiplier']:>10}x")
        print()
        print(f"  over 276 accounts    : {s['isolated_276']:>12,.0f} vs "
              f"{s['flat_276']:>12,.0f} tokens")
        print(f"  at list prices       : ${s['isolated_cost_276']:>11,.2f} vs "
              f"${s['flat_cost_276']:>11,.2f}")
    print()


if __name__ == "__main__":
    main()
