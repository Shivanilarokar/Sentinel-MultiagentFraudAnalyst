"""Token accounting, and the measurement that proves context isolation.

Two numbers matter for the write-up, and they are different things.

**Tokens.** Summed from the model's own `usage_metadata`, per agent, per
account. Not an estimate: the provider's count of what it actually processed.

**The boundary.** For each specialist invocation we record how many characters
were produced *inside* it - every tool result, every intermediate message - and
how many crossed back to the supervisor. The gap between those two numbers is
the entire architectural claim of this assignment, expressed as a measurement
rather than an assertion.

A single agent holding all the tools would carry everything in the first column
into every subsequent model call. `analysis/token_model.py` turns that into a
comparable figure.
"""

from __future__ import annotations

from sentinel.db import actions
from sentinel.messages import message_text


def sum_usage(result: dict) -> dict[str, int]:
    """Total the usage metadata across every message an agent produced.

    An agent run makes several model calls - one per tool-use turn - and each
    carries its own usage. Taking only the final message, as is tempting,
    undercounts a multi-step specialist by most of its actual cost.
    """
    input_tokens = 0
    output_tokens = 0
    for message in result.get("messages", []):
        usage = getattr(message, "usage_metadata", None)
        if usage:
            input_tokens += usage.get("input_tokens", 0) or 0
            output_tokens += usage.get("output_tokens", 0) or 0
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def measure_boundary(result: dict) -> dict[str, int]:
    """Characters produced inside an agent, against characters that escaped it.

    `chars_crossed` counts only the final message, because that is literally
    all the wrapper returns. Everything else dies with the message list.
    """
    messages = result.get("messages", [])
    inside = sum(len(message_text(m)) for m in messages)
    crossed = len(message_text(messages[-1])) if messages else 0
    return {"chars_inside": inside, "chars_crossed": crossed}


def record(account_id: str, agent: str, result: dict) -> dict[str, int]:
    """Measure one agent invocation and append it to the ledger."""
    usage = sum_usage(result)
    boundary = measure_boundary(result)
    row = {**usage, **boundary}
    try:
        with actions.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage
                    (account_id, agent, input_tokens, output_tokens,
                     chars_inside, chars_crossed)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    agent,
                    row["input_tokens"],
                    row["output_tokens"],
                    row["chars_inside"],
                    row["chars_crossed"],
                ),
            )
    except Exception:
        # Accounting must never take down a case.
        pass
    return row


def totals() -> dict:
    """Everything the ledger knows, aggregated for the write-up."""
    per_agent = [
        dict(r)
        for r in actions.query(
            """
            SELECT agent,
                   COUNT(*)                AS invocations,
                   SUM(input_tokens)       AS input_tokens,
                   SUM(output_tokens)      AS output_tokens,
                   SUM(input_tokens + output_tokens) AS total_tokens,
                   SUM(chars_inside)       AS chars_inside,
                   SUM(chars_crossed)      AS chars_crossed
            FROM usage
            GROUP BY agent
            ORDER BY total_tokens DESC
            """
        )
    ]
    overall = dict(
        actions.query(
            """
            SELECT COUNT(DISTINCT account_id) AS accounts,
                   COUNT(*)                   AS invocations,
                   COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
                   COALESCE(SUM(chars_inside), 0)  AS chars_inside,
                   COALESCE(SUM(chars_crossed), 0) AS chars_crossed
            FROM usage
            """
        )[0]
    )
    inside = overall.get("chars_inside") or 0
    crossed = overall.get("chars_crossed") or 0
    overall["discarded_at_boundary_pct"] = (
        round(100 * (1 - crossed / inside), 1) if inside else None
    )
    return {"per_agent": per_agent, "overall": overall}


def reset() -> None:
    with actions.cursor() as cur:
        cur.execute("DELETE FROM usage")
