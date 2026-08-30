"""What the sweep actually cost, and what one agent holding every tool would cost.

The measured figure comes from `usage.py` - the provider's own count of tokens
processed. This module supplies the comparison, and it derives it rather than
quoting the brief's numbers.

The single-agent figure is not a guess about a worse prompt. It is arithmetic
about how a tool-calling loop accumulates context. An agent with every tool
does not read an account's history once; it reads it, then re-sends it with the
next call, and the one after. For an agent making `n` tool calls whose results
are `r1..rn` tokens:

    processed = SUM over i of ( system + tool_schemas + SUM over j<i of rj )

which is quadratic in the material. The isolated design pays the linear cost
instead, because each specialist sees only its own domain's rows and hands back
roughly 200 tokens.

Everything here is measured with `tiktoken` against the real tool outputs for
real accounts, so the comparison is reproducible rather than asserted.
"""

from __future__ import annotations

import statistics

import tiktoken

from sentinel import usage
from sentinel.repositories import alerts_repo
from sentinel.tools.behaviour_tools import BEHAVIOUR_TOOLS
from sentinel.tools.context_tools import CONTEXT_TOOLS
from sentinel.tools.network_tools import NETWORK_TOOLS

# gpt-4.1 family uses o200k_base.
_ENCODER = tiktoken.get_encoding("o200k_base")

READ_TOOLS = BEHAVIOUR_TOOLS + CONTEXT_TOOLS + NETWORK_TOOLS


def count(text: str) -> int:
    return len(_ENCODER.encode(text or ""))


def tool_schema_tokens() -> int:
    """What the tool definitions alone cost, re-sent on every model call.

    A single agent carries all of them on every turn. Each specialist carries
    only its own domain's, which is a real part of the saving and is easy to
    forget.
    """
    total = 0
    for tool in READ_TOOLS:
        total += count(tool.name) + count(tool.description or "")
        try:
            total += count(str(tool.args_schema.model_json_schema()))
        except Exception:
            pass
    return total


def source_material(account_id: str) -> dict:
    """Run every read tool for one account and measure what comes back.

    This is the material a single agent would accumulate. Calling the tools for
    real, rather than estimating from row counts, keeps the figure honest.
    """
    per_tool = {}
    for tool in READ_TOOLS:
        try:
            per_tool[tool.name] = count(tool.invoke({"account_id": account_id}))
        except Exception:
            per_tool[tool.name] = 0
    return {"account_id": account_id, "per_tool": per_tool, "total": sum(per_tool.values())}


def single_agent_estimate(sample: int = 12, system_tokens: int = 1200) -> dict:
    """Model the one-agent cost from measured material.

    Assumes the single agent calls every read tool once per account, in some
    order, re-sending everything it has already seen. That is the charitable
    version - it assumes no repeated calls and no wasted turns.
    """
    accounts = alerts_repo.queue()
    sampled = accounts[:: max(1, len(accounts) // sample)][:sample]
    schema = tool_schema_tokens()

    per_account = []
    for account_id in sampled:
        material = source_material(account_id)
        results = [t for t in material["per_tool"].values() if t]
        # Turn i carries the system prompt, every tool schema, and every result
        # returned so far.
        processed = 0
        seen = 0
        for result_tokens in results:
            processed += system_tokens + schema + seen
            seen += result_tokens
        processed += system_tokens + schema + seen  # the final answer turn
        per_account.append(
            {
                "account_id": account_id,
                "material_tokens": material["total"],
                "tool_calls": len(results),
                "processed_tokens": processed,
            }
        )

    median_processed = int(statistics.median(p["processed_tokens"] for p in per_account))
    median_material = int(statistics.median(p["material_tokens"] for p in per_account))
    queue_size = len(accounts)

    measured = usage.totals()["overall"]
    measured_accounts = measured.get("accounts") or 0
    measured_total = measured.get("total_tokens") or 0
    measured_per_account = int(measured_total / measured_accounts) if measured_accounts else 0

    projected_single = median_processed * queue_size
    return {
        "sampled_accounts": len(per_account),
        "tool_schema_tokens_per_call": schema,
        "median_source_material_tokens_per_account": median_material,
        "median_single_agent_processed_tokens_per_account": median_processed,
        "projected_single_agent_tokens_for_queue": projected_single,
        "measured_accounts": measured_accounts,
        "measured_total_tokens": measured_total,
        "measured_tokens_per_account": measured_per_account,
        "projected_measured_tokens_for_queue": measured_per_account * queue_size,
        "ratio": (
            round(projected_single / (measured_per_account * queue_size), 1)
            if measured_per_account
            else None
        ),
        "detail": per_account,
    }


def cost_usd(tokens: int, input_rate: float = 0.40, output_rate: float = 1.60,
             output_share: float = 0.05) -> float:
    """Dollar cost at gpt-4.1-mini list rates, per million tokens."""
    output = tokens * output_share
    inputs = tokens - output
    return round((inputs * input_rate + output * output_rate) / 1_000_000, 2)
