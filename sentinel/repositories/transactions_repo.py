"""Money movement, always measured against the incident window.

Two window choices carry most of the analytical weight:

*   Everything is anchored on the incident window from `alerts_repo`, not on
    today and not on `triggered_at` alone. See that module for why: the
    transaction that tripped the rule usually happens *after* the alert
    timestamp, so a naive backward window misses the incident entirely.

*   The baseline stops seven days before the incident starts. If the incident
    is inside the baseline it drags the average up, and the anomaly then
    compares favourably against a version of "normal" that it created.
"""

from __future__ import annotations

from sentinel.db import db
from sentinel.repositories._rows import row, rows
from sentinel.repositories.alerts_repo import incident_window

NO_WINDOW = "This account has no alerts, so there is no incident window to measure."


def recent(account_id: str, limit: int = 40) -> list[dict]:
    """Transactions around the incident, newest first, with merchant context."""
    return rows(
        db.query(
            """
            SELECT t.txn_id, t.ts, t.amount, t.channel, t.ip_country, t.auth_result,
                   t.card_id, t.device_id,
                   m.name AS merchant_name, m.category AS merchant_category,
                   m.country AS merchant_country, m.risk_score AS merchant_risk
            FROM transactions t
            LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
            WHERE t.account_id = ?
            ORDER BY t.ts DESC
            LIMIT ?
            """,
            (account_id, limit),
        )
    )


def incident_transactions(account_id: str) -> list[dict]:
    """Every transaction inside the flagged episode itself.

    This is the set an analyst actually argues about, so it is returned whole
    rather than sampled.
    """
    window = incident_window(account_id)
    if not window:
        return []
    return rows(
        db.query(
            """
            SELECT t.txn_id, t.ts, t.amount, t.channel, t.ip_country, t.auth_result,
                   t.card_id, t.device_id,
                   m.name AS merchant_name, m.category AS merchant_category,
                   m.risk_score AS merchant_risk
            FROM transactions t
            LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
            WHERE t.account_id = ?
              AND t.ts BETWEEN strftime('%Y-%m-%dT%H:%M:%S', ?, '-1 hours')
                          AND strftime('%Y-%m-%dT%H:%M:%S', ?, '+1 hours')
            ORDER BY t.ts
            """,
            (account_id, window["incident_start"], window["incident_end"]),
        )
    )


def velocity(account_id: str, hours: int = 24) -> dict:
    """Activity in the N hours ending when the incident ends."""
    window = incident_window(account_id)
    if not window:
        return {"error": NO_WINDOW}
    end = window["incident_end"]

    summary = row(
        db.one(
            """
            SELECT COUNT(*) AS txn_count,
                   ROUND(COALESCE(SUM(amount), 0), 2)  AS total_amount,
                   ROUND(COALESCE(MAX(amount), 0), 2)  AS largest_amount,
                   COUNT(DISTINCT ip_country)          AS distinct_countries,
                   COUNT(DISTINCT device_id)           AS distinct_devices,
                   COUNT(DISTINCT merchant_id)         AS distinct_merchants,
                   SUM(CASE WHEN auth_result = 'declined' THEN 1 ELSE 0 END) AS declined,
                   SUM(CASE WHEN CAST(strftime('%H', ts) AS INTEGER) BETWEEN 1 AND 5
                            THEN 1 ELSE 0 END)         AS night_txns,
                   MIN(ts) AS window_first_txn,
                   MAX(ts) AS window_last_txn
            FROM transactions
            WHERE account_id = ?
              AND ts BETWEEN strftime('%Y-%m-%dT%H:%M:%S', ?, ?) AND ?
            """,
            (account_id, end, f"-{hours} hours", end),
        )
    ) or {}
    summary.update(
        {
            "window_hours": hours,
            "incident_start": window["incident_start"],
            "incident_end": end,
            "rules_fired": window["rules_fired"],
        }
    )
    return summary


def baseline(account_id: str) -> dict:
    """The customer's normal, from history that excludes the incident."""
    window = incident_window(account_id)
    if not window:
        return {"error": NO_WINDOW}

    summary = row(
        db.one(
            """
            SELECT COUNT(*) AS txn_count,
                   ROUND(AVG(amount), 2) AS avg_amount,
                   ROUND(MAX(amount), 2) AS max_amount,
                   COUNT(DISTINCT ip_country) AS distinct_countries,
                   COUNT(DISTINCT device_id)  AS distinct_devices,
                   ROUND(AVG(CASE WHEN CAST(strftime('%H', ts) AS INTEGER)
                                       BETWEEN 1 AND 5 THEN 1.0 ELSE 0.0 END), 3)
                        AS night_txn_rate,
                   MIN(ts) AS first_txn,
                   MAX(ts) AS last_txn
            FROM transactions
            WHERE account_id = ?
              AND ts < strftime('%Y-%m-%dT%H:%M:%S', ?, '-7 days')
            """,
            (account_id, window["incident_start"]),
        )
    ) or {}
    summary["baseline_ends"] = "7 days before the incident started"
    return summary


def geo_pattern(account_id: str) -> list[dict]:
    """Every country this account has transacted from, with first and last use.

    A country seen for the first time inside the incident means something very
    different from one the customer has used for months. `first_seen` is what
    makes that distinction visible.
    """
    return rows(
        db.query(
            """
            SELECT ip_country,
                   COUNT(*) AS txn_count,
                   ROUND(SUM(amount), 2) AS total_amount,
                   MIN(ts) AS first_seen,
                   MAX(ts) AS last_seen
            FROM transactions
            WHERE account_id = ?
            GROUP BY ip_country
            ORDER BY txn_count DESC
            """,
            (account_id,),
        )
    )


def device_usage(account_id: str) -> list[dict]:
    """Devices this account transacted from, with registration age at the incident.

    `device_age_hours_at_incident` is the number that decides an R02 alert. A
    device registered minutes before the transaction is a different fact from
    one registered eighteen months ago, and the model should not have to do
    that subtraction itself.
    """
    window = incident_window(account_id)
    anchor = window["incident_start"] if window else None
    return rows(
        db.query(
            """
            SELECT t.device_id,
                   d.os, d.device_type, d.first_seen AS device_registered,
                   ROUND((julianday(?) - julianday(d.first_seen)) * 24, 1)
                        AS device_age_hours_at_incident,
                   COUNT(*) AS txn_count,
                   ROUND(SUM(t.amount), 2) AS total_amount,
                   MIN(t.ts) AS first_txn_on_device,
                   MAX(t.ts) AS last_txn_on_device
            FROM transactions t
            LEFT JOIN devices d ON d.device_id = t.device_id
            WHERE t.account_id = ?
            GROUP BY t.device_id
            ORDER BY last_txn_on_device DESC
            """,
            (anchor, account_id),
        )
    )


def high_risk_merchant_activity(account_id: str, days: int = 30) -> list[dict]:
    """Spend at crypto, gift card, money transfer and gaming merchants near the incident.

    These carry the highest risk scores in the data, and they are also used by
    ordinary customers, so this returns rows to reason about rather than a score.
    """
    window = incident_window(account_id)
    if not window:
        return []
    end = window["incident_end"]
    return rows(
        db.query(
            """
            SELECT t.txn_id, t.ts, t.amount, t.auth_result, t.ip_country,
                   m.name AS merchant_name, m.category AS merchant_category,
                   m.risk_score AS merchant_risk
            FROM transactions t
            JOIN merchants m ON m.merchant_id = t.merchant_id
            WHERE t.account_id = ?
              AND m.category IN ('crypto', 'giftcard', 'moneytransfer', 'gaming')
              AND t.ts BETWEEN strftime('%Y-%m-%dT%H:%M:%S', ?, ?) AND ?
            ORDER BY t.ts DESC
            """,
            (account_id, end, f"-{days} days", end),
        )
    )


def limit_utilisation(account_id: str, days: int = 2) -> dict:
    """Cumulative approved spend against the credit limit over the closing days.

    R08 fires on crossing 90 percent of the limit inside 48 hours, so this is
    the figure that either supports or undercuts that specific alert.
    """
    window = incident_window(account_id)
    if not window:
        return {"error": NO_WINDOW}
    end = window["incident_end"]
    result = row(
        db.one(
            """
            SELECT a.credit_limit,
                   ROUND(COALESCE(SUM(t.amount), 0), 2) AS spend_in_window,
                   COUNT(t.txn_id) AS txn_count
            FROM accounts a
            LEFT JOIN transactions t
                   ON t.account_id = a.account_id
                  AND t.auth_result = 'approved'
                  AND t.ts BETWEEN strftime('%Y-%m-%dT%H:%M:%S', ?, ?) AND ?
            WHERE a.account_id = ?
            """,
            (end, f"-{days} days", end, account_id),
        )
    ) or {}
    limit = result.get("credit_limit") or 0
    spend = result.get("spend_in_window") or 0
    result["pct_of_limit"] = round(100 * spend / limit, 1) if limit else None
    result["window_days"] = days
    return result
