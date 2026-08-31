"""Every SQL query in the system, grouped by domain. No LLM anywhere in here.

Deterministic logic belongs in Python. Ambiguity belongs in the model. Date
arithmetic, window anchoring and baseline statistics are not judgement calls, so
they are computed here and handed to the specialists as facts.

Two measured findings shape most of this file.

**1. `triggered_at` is the start of the episode, not the offending transaction.**
In 342 of 411 alerts the transaction named by `trigger_txn_id` happens *after*
`triggered_at`, by up to 18 hours. A window measured backwards from
`triggered_at` therefore excludes the very activity that caused the alert. Every
window here is anchored on `incident_window()` instead, which spans both.

**2. Timing is what makes a note evidence.**
Across alerted accounts, 179 notes were filed *before* the incident and 71
*after*. A note filed before is a pre-existing explanation. A note filed after is
the customer's reaction, and "I did not make these transactions" corroborates
fraud rather than explaining it. Every narrative row carries `days_before_alert`
and a `timing` label computed in SQL, because models are poor at date arithmetic
and this distinction decides roughly a third of the queue.
"""

from __future__ import annotations

from sentinel.db import query, query_one

# Categories the schema flags as higher risk. Legitimate customers use them too,
# which is exactly why this is a signal and not an answer.
HIGH_RISK_CATEGORIES = ("crypto", "giftcard", "moneytransfer")

# Timestamps in this database are ISO with a 'T' separator: '2026-02-27T12:46:44'.
# SQLite's own `datetime()` returns a SPACE separator, and every comparison here
# is a string comparison, so mixing the two silently matches nothing:
#
#     '2026-02-27T12:46:44' > '2026-02-27 17:46:44'      because 'T' (84) > ' ' (32)
#
# A window built with `datetime()` therefore returns zero rows rather than an
# error, which is the worst way for a bug to behave. Every date expression in
# this file is therefore written as `strftime('%Y-%m-%dT%H:%M:%S', ...)`, never
# as `datetime(...)`, so the separator always matches the column.


# ===========================================================================
# Shared helpers
# ===========================================================================
def alerted_accounts() -> list[str]:
    """The work list: every account with at least one open alert. 276 of them."""
    rows = query("SELECT DISTINCT account_id FROM alerts ORDER BY account_id")
    return [r["account_id"] for r in rows]


def customer_id_for(account_id: str) -> str | None:
    """Accounts are the alert key; the free text hangs off the customer."""
    row = query_one("SELECT customer_id FROM accounts WHERE account_id = ?", (account_id,))
    return row["customer_id"] if row else None


def incident_window(account_id: str) -> tuple[str, str]:
    """The span the alerts actually describe, as (start, end) ISO timestamps.

    Anchored on both `triggered_at` and the timestamp of every `trigger_txn_id`,
    then padded by two hours either side, so it contains the episode however the
    rules engine happened to order the two.
    """
    row = query_one(
        """
        SELECT MIN(MIN(a.triggered_at, COALESCE(t.ts, a.triggered_at))) AS lo,
               MAX(MAX(a.triggered_at, COALESCE(t.ts, a.triggered_at))) AS hi
        FROM alerts a
        LEFT JOIN transactions t ON t.txn_id = a.trigger_txn_id
        WHERE a.account_id = ?
        """,
        (account_id,),
    )
    if not row or not row["lo"]:
        return ("", "")

    padded = query_one(
        """
        SELECT strftime('%Y-%m-%dT%H:%M:%S', ?, '-2 hours') AS lo,
               strftime('%Y-%m-%dT%H:%M:%S', ?, '+2 hours') AS hi
        """,
        (row["lo"], row["hi"]),
    )
    return (padded["lo"], padded["hi"])


def _rows(sql: str, params: tuple) -> list[dict]:
    """Run a query and hand back plain dicts, which tools can format freely."""
    return [dict(r) for r in query(sql, params)]


# ===========================================================================
# BEHAVIOUR: is this spending normal for this customer?
# ===========================================================================
def get_alerts(account_id: str) -> list[dict]:
    """What fired, when, and what the rule was actually looking for.

    The rule description matters as much as the rule name: it tells the
    specialist what a *false positive* of that rule looks like.
    """
    return _rows(
        """
        SELECT a.alert_id, a.rule_id, r.name AS rule_name,
               r.description AS rule_description,
               a.triggered_at, a.severity, a.trigger_txn_id,
               t.ts AS trigger_txn_ts, t.amount AS trigger_amount,
               t.channel AS trigger_channel, t.ip_country AS trigger_ip_country,
               m.name AS trigger_merchant, m.category AS trigger_merchant_category
        FROM alerts a
        JOIN rules r ON r.rule_id = a.rule_id
        LEFT JOIN transactions t ON t.txn_id = a.trigger_txn_id
        LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
        WHERE a.account_id = ?
        ORDER BY a.triggered_at
        """,
        (account_id,),
    )


def get_incident_activity(account_id: str) -> list[dict]:
    """Every transaction inside the incident window, oldest first.

    This is the episode the alerts are about. Anchored on `incident_window`,
    not measured backwards from `triggered_at`.
    """
    lo, hi = incident_window(account_id)
    if not lo:
        return []
    return _rows(
        """
        SELECT t.txn_id, t.ts, t.amount, t.channel, t.ip_country, t.auth_result,
               t.device_id, t.card_id,
               m.name AS merchant, m.category, m.country AS merchant_country,
               m.risk_score
        FROM transactions t
        LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
        WHERE t.account_id = ? AND t.ts BETWEEN ? AND ?
        ORDER BY t.ts
        """,
        (account_id, lo, hi),
    )


def get_spending_baseline(account_id: str) -> dict:
    """What normal looks like *for this customer*, over the 90 days before.

    Abnormality is relative. 200,000 rupees is a spree on a student account and
    a Tuesday on a business one, so the specialist is given the customer's own
    history rather than a global threshold.
    """
    lo, _ = incident_window(account_id)
    if not lo:
        return {}

    summary = query_one(
        """
        SELECT COUNT(*) AS txn_count,
               ROUND(AVG(amount), 2) AS mean_amount,
               ROUND(MAX(amount), 2) AS max_amount,
               ROUND(SUM(amount), 2) AS total_amount,
               COUNT(DISTINCT date(ts)) AS active_days,
               COUNT(DISTINCT ip_country) AS countries_used,
               COUNT(DISTINCT device_id) AS devices_used
        FROM transactions
        WHERE account_id = ? AND ts < ? AND ts >= strftime('%Y-%m-%dT%H:%M:%S', ?, '-90 days')
          AND auth_result = 'approved'
        """,
        (account_id, lo, lo),
    )
    baseline = dict(summary) if summary else {}

    # A median survives one holiday better than a mean does.
    median = query_one(
        """
        SELECT ROUND(amount, 2) AS median_amount FROM transactions
        WHERE account_id = ? AND ts < ? AND ts >= strftime('%Y-%m-%dT%H:%M:%S', ?, '-90 days')
          AND auth_result = 'approved'
        ORDER BY amount
        LIMIT 1 OFFSET (
            SELECT COUNT(*) / 2 FROM transactions
            WHERE account_id = ? AND ts < ? AND ts >= strftime('%Y-%m-%dT%H:%M:%S', ?, '-90 days')
              AND auth_result = 'approved'
        )
        """,
        (account_id, lo, lo, account_id, lo, lo),
    )
    baseline["median_amount"] = median["median_amount"] if median else None
    baseline["window_start"] = lo
    baseline["usual_hours"] = _rows(
        """
        SELECT CAST(strftime('%H', ts) AS INTEGER) AS hour, COUNT(*) AS n
        FROM transactions
        WHERE account_id = ? AND ts < ? AND ts >= strftime('%Y-%m-%dT%H:%M:%S', ?, '-90 days')
        GROUP BY hour ORDER BY n DESC LIMIT 5
        """,
        (account_id, lo, lo),
    )
    return baseline


def get_device_history(account_id: str) -> list[dict]:
    """Devices this customer has used, and how old each was at the incident.

    `age_days_at_incident` is the number R02 turns on. A device first seen the
    morning of the alert is a different story from one seen for three months.
    """
    lo, _ = incident_window(account_id)
    customer = customer_id_for(account_id)
    if not lo or not customer:
        return []
    return _rows(
        """
        SELECT d.device_id, d.os, d.device_type, d.first_seen,
               cd.first_seen AS customer_first_seen, cd.last_seen,
               ROUND(julianday(?) - julianday(cd.first_seen), 1) AS age_days_at_incident,
               (SELECT COUNT(*) FROM transactions t
                 WHERE t.account_id = ? AND t.device_id = d.device_id) AS txns_on_device
        FROM customer_devices cd
        JOIN devices d ON d.device_id = cd.device_id
        WHERE cd.customer_id = ?
        ORDER BY cd.first_seen DESC
        """,
        (lo, account_id, customer),
    )


def get_geography(account_id: str) -> dict:
    """Where this account normally transacts, against where it just did.

    Returned as two lists so the specialist can see whether a foreign country in
    the incident is genuinely new or a place this customer visits every month.
    """
    lo, hi = incident_window(account_id)
    if not lo:
        return {}
    return {
        "baseline_90d": _rows(
            """
            SELECT ip_country, COUNT(*) AS n, ROUND(SUM(amount), 2) AS total
            FROM transactions
            WHERE account_id = ? AND ts < ? AND ts >= strftime('%Y-%m-%dT%H:%M:%S', ?, '-90 days')
            GROUP BY ip_country ORDER BY n DESC
            """,
            (account_id, lo, lo),
        ),
        "incident": _rows(
            """
            SELECT ip_country, COUNT(*) AS n, ROUND(SUM(amount), 2) AS total,
                   MIN(ts) AS first_ts, MAX(ts) AS last_ts
            FROM transactions
            WHERE account_id = ? AND ts BETWEEN ? AND ?
            GROUP BY ip_country ORDER BY first_ts
            """,
            (account_id, lo, hi),
        ),
    }


def get_high_risk_merchant_activity(account_id: str) -> dict:
    """Crypto, gift card and money transfer spend, incident against history.

    Legitimate customers use these categories. What separates a spree from a
    habit is whether the customer has ever used them before.
    """
    lo, hi = incident_window(account_id)
    if not lo:
        return {}
    marks = ",".join("?" * len(HIGH_RISK_CATEGORIES))
    return {
        "incident": _rows(
            f"""
            SELECT t.ts, t.amount, t.auth_result, m.name AS merchant,
                   m.category, m.country, m.risk_score
            FROM transactions t JOIN merchants m ON m.merchant_id = t.merchant_id
            WHERE t.account_id = ? AND t.ts BETWEEN ? AND ?
              AND m.category IN ({marks})
            ORDER BY t.ts
            """,
            (account_id, lo, hi, *HIGH_RISK_CATEGORIES),
        ),
        "history_90d": _rows(
            f"""
            SELECT m.category, COUNT(*) AS n, ROUND(SUM(t.amount), 2) AS total
            FROM transactions t JOIN merchants m ON m.merchant_id = t.merchant_id
            WHERE t.account_id = ? AND t.ts < ? AND t.ts >= strftime('%Y-%m-%dT%H:%M:%S', ?, '-90 days')
              AND m.category IN ({marks})
            GROUP BY m.category
            """,
            (account_id, lo, lo, *HIGH_RISK_CATEGORIES),
        ),
    }


def get_limit_utilisation(account_id: str) -> dict:
    """Incident spend against the account's credit limit.

    R08 fires on limit approach. Whether that is alarming depends on the limit,
    which depends on the segment, so both are returned alongside it.
    """
    lo, hi = incident_window(account_id)
    row = query_one(
        """
        SELECT a.credit_limit, a.product, a.status, c.segment, c.kyc_level
        FROM accounts a JOIN customers c ON c.customer_id = a.customer_id
        WHERE a.account_id = ?
        """,
        (account_id,),
    )
    if not row or not lo:
        return {}

    spend = query_one(
        """
        SELECT ROUND(SUM(amount), 2) AS incident_spend, COUNT(*) AS incident_txns
        FROM transactions
        WHERE account_id = ? AND ts BETWEEN ? AND ? AND auth_result = 'approved'
        """,
        (account_id, lo, hi),
    )
    out = dict(row) | dict(spend or {})
    if out.get("incident_spend") and out.get("credit_limit"):
        out["utilisation_pct"] = round(100 * out["incident_spend"] / out["credit_limit"], 1)
    return out


# ===========================================================================
# CONTEXT: did the customer already explain this?
# ===========================================================================
def get_customer_profile(account_id: str) -> dict:
    """Who this is. Segment and KYC level set the baseline for everything else."""
    row = query_one(
        """
        SELECT c.customer_id, c.full_name, c.signup_date, c.home_country,
               c.kyc_level, c.segment,
               a.account_id, a.opened_date, a.product, a.status, a.credit_limit,
               ROUND(julianday('2026-03-02') - julianday(c.signup_date)) AS days_since_signup
        FROM accounts a JOIN customers c ON c.customer_id = a.customer_id
        WHERE a.account_id = ?
        """,
        (account_id,),
    )
    if not row:
        return {}
    profile = dict(row)
    profile["cards"] = _rows(
        "SELECT card_id, last4, issued_date, status FROM cards WHERE account_id = ?",
        (account_id,),
    )
    return profile


def get_case_notes(account_id: str) -> list[dict]:
    """Everything a colleague typed about this customer, with the timing label.

    `days_before_alert` and `timing` are computed in SQL, not left to the model:

        before_incident   filed before the alerts fired. A pre-existing
                          explanation, and the strongest evidence in the file.
        during_incident   filed inside the incident window itself.
        after_incident    filed afterwards. This is the customer's reaction, not
                          an explanation. "I did not make these" corroborates
                          fraud; it does not excuse it.
    """
    customer = customer_id_for(account_id)
    lo, hi = incident_window(account_id)
    if not customer or not lo:
        return []
    return _rows(
        """
        SELECT n.note_id, n.created_at, n.author, n.channel, n.note,
               ROUND(julianday(?) - julianday(n.created_at), 1) AS days_before_alert,
               CASE
                   WHEN n.created_at <  ? THEN 'before_incident'
                   WHEN n.created_at <= ? THEN 'during_incident'
                   ELSE 'after_incident'
               END AS timing
        FROM case_notes n
        WHERE n.customer_id = ?
        ORDER BY n.created_at DESC
        """,
        (lo, lo, hi, customer),
    )


def get_disputes(account_id: str) -> list[dict]:
    """The customer's own words about charges they are challenging.

    Disputing is not proof of fraud. Some are chargebacks over undelivered
    goods; some are a family member using the card. The statement text is what
    separates them, so it is returned in full.
    """
    lo, hi = incident_window(account_id)
    if not lo:
        return []
    return _rows(
        """
        SELECT d.dispute_id, d.txn_id, d.filed_at, d.reason_code,
               d.customer_statement, d.status,
               t.ts AS txn_ts, t.amount, m.name AS merchant, m.category,
               CASE
                   WHEN d.filed_at <  ? THEN 'before_incident'
                   WHEN d.filed_at <= ? THEN 'during_incident'
                   ELSE 'after_incident'
               END AS timing
        FROM disputes d
        JOIN transactions t ON t.txn_id = d.txn_id
        LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
        WHERE t.account_id = ?
        ORDER BY d.filed_at DESC
        """,
        (lo, hi, account_id),
    )


def get_prior_cases(account_id: str) -> list[dict]:
    """Previous investigations and how they closed.

    A customer with three prior false positives is a different proposition from
    one with a confirmed compromise last year.
    """
    customer = customer_id_for(account_id)
    if not customer:
        return []
    return _rows(
        """
        SELECT case_id, opened_date, closed_date, outcome, summary
        FROM prior_cases WHERE customer_id = ?
        ORDER BY opened_date DESC
        """,
        (customer,),
    )


# ===========================================================================
# NETWORK: is this account acting alone?
# ===========================================================================
def get_shared_devices(account_id: str) -> list[dict]:
    """Devices this customer shares with somebody else.

    16 devices in the database are shared. Some of those are mule rings. Some
    are married couples with a family tablet. Sharing is a signal, not an answer,
    so the peers are returned rather than a verdict.
    """
    customer = customer_id_for(account_id)
    if not customer:
        return []
    return _rows(
        """
        SELECT d.device_id, d.device_type, d.os, cd.first_seen, cd.last_seen,
               (SELECT COUNT(DISTINCT customer_id) FROM customer_devices
                 WHERE device_id = d.device_id) AS customers_on_device
        FROM customer_devices cd
        JOIN devices d ON d.device_id = cd.device_id
        WHERE cd.customer_id = ?
          AND (SELECT COUNT(DISTINCT customer_id) FROM customer_devices
                WHERE device_id = d.device_id) > 1
        ORDER BY customers_on_device DESC
        """,
        (customer,),
    )


def get_device_peers(account_id: str) -> list[dict]:
    """Who else uses those devices, and whether they are alerted too.

    Two strangers who share a device and are both flagged this weekend is a
    ring. A spouse who shares a tablet and has never been flagged is a family.
    """
    customer = customer_id_for(account_id)
    if not customer:
        return []
    return _rows(
        """
        SELECT DISTINCT peer.customer_id, c.full_name, c.segment, c.home_country,
               cd.device_id, peer.first_seen AS peer_first_seen,
               pa.account_id AS peer_account_id,
               (SELECT COUNT(*) FROM alerts al
                 WHERE al.account_id = pa.account_id) AS peer_alert_count,
               (SELECT COUNT(*) FROM prior_cases pc
                 WHERE pc.customer_id = peer.customer_id
                   AND pc.outcome = 'confirmed_fraud') AS peer_confirmed_fraud
        FROM customer_devices cd
        JOIN customer_devices peer ON peer.device_id = cd.device_id
                                  AND peer.customer_id != cd.customer_id
        JOIN customers c ON c.customer_id = peer.customer_id
        LEFT JOIN accounts pa ON pa.customer_id = peer.customer_id
        WHERE cd.customer_id = ?
        """,
        (customer,),
    )


def get_merchant_overlap(account_id: str) -> list[dict]:
    """Merchants hit during this incident that other alerted accounts also hit.

    A merchant many flagged accounts touched in the same weekend is a cash-out
    point. A supermarket everybody uses is not, which is why the count of *other
    alerted accounts* is returned rather than raw popularity.
    """
    lo, hi = incident_window(account_id)
    if not lo:
        return []
    return _rows(
        """
        SELECT m.merchant_id, m.name AS merchant, m.category, m.country,
               m.risk_score,
               COUNT(DISTINCT t2.account_id) AS other_alerted_accounts,
               ROUND(SUM(t.amount), 2) AS our_spend
        FROM transactions t
        JOIN merchants m ON m.merchant_id = t.merchant_id
        LEFT JOIN transactions t2 ON t2.merchant_id = t.merchant_id
             AND t2.account_id != t.account_id
             AND t2.account_id IN (SELECT DISTINCT account_id FROM alerts)
             AND t2.ts >= strftime('%Y-%m-%dT%H:%M:%S', ?, '-7 days') AND t2.ts <= ?
        WHERE t.account_id = ? AND t.ts BETWEEN ? AND ?
        GROUP BY m.merchant_id
        ORDER BY other_alerted_accounts DESC, our_spend DESC
        """,
        (lo, hi, account_id, lo, hi),
    )
