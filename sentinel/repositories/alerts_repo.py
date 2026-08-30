"""Alerts, rules, and the incident window everything else is anchored to.

`incident_window` is the most important function in this package, and it exists
because of a property of this dataset that is easy to get wrong.

`alerts.triggered_at` is *not* the moment the offending transaction happened.
In 342 of the 411 alerts the transaction named by `trigger_txn_id` occurs
**after** `triggered_at`, by anything up to twelve hours. `triggered_at` marks
the start of the episode the rules engine flagged; the trigger transaction is
somewhere inside it.

A window that runs backwards from `triggered_at` therefore excludes the very
activity that caused the alert. On account A00985 that mistake reports 36,869
of spend across two transactions when the real episode is 216,091 across four.
Every window in this codebase is measured against the incident window instead:

    start = earliest triggered_at on the account
    end   = latest of (triggered_at, its own trigger transaction's timestamp)
"""

from __future__ import annotations

from sentinel.db import db
from sentinel.repositories._rows import row, rows

ALERTS_SQL = """
SELECT a.alert_id, a.rule_id, r.name AS rule_name, r.description AS rule_description,
       a.severity, a.triggered_at, a.trigger_txn_id, a.status
FROM alerts a
JOIN rules r ON r.rule_id = a.rule_id
WHERE a.account_id = ?
ORDER BY a.triggered_at
"""

INCIDENT_SQL = """
SELECT MIN(a.triggered_at)                        AS incident_start,
       MAX(COALESCE(t.ts, a.triggered_at))        AS incident_end,
       COUNT(*)                                   AS alert_count,
       GROUP_CONCAT(DISTINCT a.rule_id)           AS rules_fired
FROM alerts a
LEFT JOIN transactions t ON t.txn_id = a.trigger_txn_id
WHERE a.account_id = ?
"""


def for_account(account_id: str) -> list[dict]:
    """Every alert on an account, with the firing rule's description inlined."""
    return rows(db.query(ALERTS_SQL, (account_id,)))


def incident_window(account_id: str) -> dict | None:
    """The span of the flagged episode. Returns None if the account is not alerted."""
    result = row(db.one(INCIDENT_SQL, (account_id,)))
    if not result or not result.get("incident_start"):
        return None
    return result


def reference_time(account_id: str) -> str | None:
    """End of the incident window: the anchor for every backward-looking window."""
    window = incident_window(account_id)
    return window["incident_end"] if window else None


def trigger_transactions(account_id: str) -> list[dict]:
    """The exact transactions that tripped the rules.

    These are the rows a disposition is most likely to cite, so they are
    fetched whole rather than left to be found in a listing.
    """
    return rows(
        db.query(
            """
            SELECT t.txn_id, t.ts, t.amount, t.channel, t.ip_country, t.auth_result,
                   t.card_id, t.device_id,
                   m.name AS merchant_name, m.category AS merchant_category,
                   m.country AS merchant_country, m.risk_score AS merchant_risk,
                   a.alert_id, a.rule_id, a.triggered_at
            FROM alerts a
            JOIN transactions t ON t.txn_id = a.trigger_txn_id
            LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
            WHERE a.account_id = ?
            ORDER BY t.ts
            """,
            (account_id,),
        )
    )


def queue() -> list[str]:
    """Every distinct alerted account. This is the work list: 276 of them."""
    return [
        r["account_id"]
        for r in rows(db.query("SELECT DISTINCT account_id FROM alerts ORDER BY account_id"))
    ]


def all_rules() -> list[dict]:
    return rows(db.query("SELECT rule_id, name, description FROM rules ORDER BY rule_id"))
