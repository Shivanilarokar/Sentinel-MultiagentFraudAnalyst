"""Every SQL query in the system, grouped by domain.

Pure functions over the read-only database. No language model, no prompt, no
formatting decisions - parameterised queries returning plain dicts. Keeping
them here rather than inside the tool modules means the SQL can be tested on
its own, which is how the two window bugs below were caught before any agent
existed.

Two pieces of domain reasoning are built into these queries and carry most of
the analytical weight:

**The incident window.** `alerts.triggered_at` is not the moment the offending
transaction happened. In 342 of the 411 alerts the transaction named by
`trigger_txn_id` occurs *after* `triggered_at`, by up to twelve hours - the
alert marks the start of the flagged episode. A window measured backwards from
`triggered_at` therefore excludes the very activity that caused the alert. On
account A00985 that mistake reports 36,869 across two transactions when the
real episode is 216,099 across five. Every window here is anchored on:

    start = earliest triggered_at on the account
    end   = latest of (triggered_at, its trigger transaction's timestamp)

**Timestamp formats.** SQLite's `datetime()` returns `YYYY-MM-DD HH:MM:SS` with
a space, while every `ts` column uses `T`. String comparison between the two
silently fails, so all date arithmetic uses
`strftime('%Y-%m-%dT%H:%M:%S', ...)` to match the stored format.
"""

from __future__ import annotations

import sqlite3

from sentinel.db import db

NO_WINDOW = "This account has no alerts, so there is no incident window to measure."

# Match the stored timestamp format exactly; see the module docstring.
ISO = "strftime('%Y-%m-%dT%H:%M:%S', "


def _rows(result: list[sqlite3.Row]) -> list[dict]:
    """sqlite3.Row is not JSON-serialisable; everything here returns dicts."""
    return [dict(row) for row in result]


def _row(result: sqlite3.Row | None) -> dict | None:
    return dict(result) if result is not None else None


# ==========================================================================
# Alerts, rules, and the incident window everything else is anchored to
# ==========================================================================

def alerts_for(account_id: str) -> list[dict]:
    """Every alert on an account, with the firing rule's description inlined."""
    return _rows(db.query(
        """
        SELECT a.alert_id, a.rule_id, r.name AS rule_name,
               r.description AS rule_description,
               a.severity, a.triggered_at, a.trigger_txn_id, a.status
        FROM alerts a
        JOIN rules r ON r.rule_id = a.rule_id
        WHERE a.account_id = ?
        ORDER BY a.triggered_at
        """,
        (account_id,),
    ))


def incident_window(account_id: str) -> dict | None:
    """The span of the flagged episode. None if the account is not alerted."""
    result = _row(db.one(
        """
        SELECT MIN(a.triggered_at)                 AS incident_start,
               MAX(COALESCE(t.ts, a.triggered_at)) AS incident_end,
               COUNT(*)                            AS alert_count,
               GROUP_CONCAT(DISTINCT a.rule_id)    AS rules_fired
        FROM alerts a
        LEFT JOIN transactions t ON t.txn_id = a.trigger_txn_id
        WHERE a.account_id = ?
        """,
        (account_id,),
    ))
    return result if result and result.get("incident_start") else None


def trigger_transactions(account_id: str) -> list[dict]:
    """The exact transactions that tripped the rules.

    These are the rows a disposition is most likely to cite, so they are
    fetched whole rather than left to be found in a listing.
    """
    return _rows(db.query(
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
    ))


def queue() -> list[str]:
    """Every distinct alerted account. This is the work list: 276 of them."""
    return [r["account_id"] for r in _rows(
        db.query("SELECT DISTINCT account_id FROM alerts ORDER BY account_id")
    )]


def all_rules() -> list[dict]:
    return _rows(db.query("SELECT rule_id, name, description FROM rules ORDER BY rule_id"))


# ==========================================================================
# The customer behind the account
# ==========================================================================

def profile(account_id: str) -> dict | None:
    """Attributes that change what 'normal' means for this customer.

    Segment drives the expected spending pattern and credit limit; KYC level
    changes how much weight an unexplained anomaly should carry.
    """
    return _row(db.one(
        """
        SELECT c.customer_id, c.full_name, c.email, c.signup_date,
               c.home_country, c.kyc_level, c.segment,
               a.account_id, a.opened_date, a.product,
               a.status AS account_status, a.credit_limit
        FROM accounts a
        JOIN customers c ON c.customer_id = a.customer_id
        WHERE a.account_id = ?
        """,
        (account_id,),
    ))


def cards(account_id: str) -> list[dict]:
    return _rows(db.query(
        "SELECT card_id, last4, issued_date, status FROM cards WHERE account_id = ?",
        (account_id,),
    ))


# ==========================================================================
# Money movement, always measured against the incident window
# ==========================================================================

def incident_transactions(account_id: str) -> list[dict]:
    """Every transaction inside the flagged episode itself."""
    window = incident_window(account_id)
    if not window:
        return []
    return _rows(db.query(
        f"""
        SELECT t.txn_id, t.ts, t.amount, t.channel, t.ip_country, t.auth_result,
               t.card_id, t.device_id,
               m.name AS merchant_name, m.category AS merchant_category,
               m.risk_score AS merchant_risk
        FROM transactions t
        LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
        WHERE t.account_id = ?
          AND t.ts BETWEEN {ISO}?, '-1 hours') AND {ISO}?, '+1 hours')
        ORDER BY t.ts
        """,
        (account_id, window["incident_start"], window["incident_end"]),
    ))


def velocity(account_id: str, hours: int = 24) -> dict:
    """Activity in the N hours ending when the incident ends."""
    window = incident_window(account_id)
    if not window:
        return {"error": NO_WINDOW}
    end = window["incident_end"]

    summary = _row(db.one(
        f"""
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
          AND ts BETWEEN {ISO}?, ?) AND ?
        """,
        (account_id, end, f"-{hours} hours", end),
    )) or {}
    summary.update({
        "window_hours": hours,
        "incident_start": window["incident_start"],
        "incident_end": end,
        "rules_fired": window["rules_fired"],
    })
    return summary


def baseline(account_id: str) -> dict:
    """The customer's normal, from history that excludes the incident.

    Stops seven days before the incident starts. If the incident is inside the
    baseline it drags the average up, and the anomaly then compares favourably
    against a version of 'normal' that it created.
    """
    window = incident_window(account_id)
    if not window:
        return {"error": NO_WINDOW}

    summary = _row(db.one(
        f"""
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
          AND ts < {ISO}?, '-7 days')
        """,
        (account_id, window["incident_start"]),
    )) or {}
    summary["baseline_ends"] = "7 days before the incident started"
    return summary


def geo_pattern(account_id: str) -> list[dict]:
    """Every country this account has transacted from, with first and last use.

    A country used for months is not new. One appearing for the first time
    inside the incident is, and `first_seen` is what makes that visible.
    """
    return _rows(db.query(
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
    ))


def device_usage(account_id: str) -> list[dict]:
    """Devices this account used, with registration age at the incident.

    `device_age_hours_at_incident` is the number that decides an R02 alert, and
    the model should not have to do that subtraction itself.
    """
    window = incident_window(account_id)
    anchor = window["incident_start"] if window else None
    return _rows(db.query(
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
    ))


def high_risk_merchant_activity(account_id: str, days: int = 30) -> list[dict]:
    """Crypto, gift card, money transfer and gaming spend near the incident.

    These carry the highest risk scores in the book and are also used by
    ordinary customers, so this returns rows to reason about, not a score.
    """
    window = incident_window(account_id)
    if not window:
        return []
    end = window["incident_end"]
    return _rows(db.query(
        f"""
        SELECT t.txn_id, t.ts, t.amount, t.auth_result, t.ip_country,
               m.name AS merchant_name, m.category AS merchant_category,
               m.risk_score AS merchant_risk
        FROM transactions t
        JOIN merchants m ON m.merchant_id = t.merchant_id
        WHERE t.account_id = ?
          AND m.category IN ('crypto', 'giftcard', 'moneytransfer', 'gaming')
          AND t.ts BETWEEN {ISO}?, ?) AND ?
        ORDER BY t.ts DESC
        """,
        (account_id, end, f"-{days} days", end),
    ))


def limit_utilisation(account_id: str, days: int = 2) -> dict:
    """Approved spend against the credit limit over the closing days.

    R08 fires at 90 percent of the limit inside 48 hours, so this is the figure
    that either supports or undercuts that specific alert.
    """
    window = incident_window(account_id)
    if not window:
        return {"error": NO_WINDOW}
    end = window["incident_end"]
    result = _row(db.one(
        f"""
        SELECT a.credit_limit,
               ROUND(COALESCE(SUM(t.amount), 0), 2) AS spend_in_window,
               COUNT(t.txn_id) AS txn_count
        FROM accounts a
        LEFT JOIN transactions t
               ON t.account_id = a.account_id
              AND t.auth_result = 'approved'
              AND t.ts BETWEEN {ISO}?, ?) AND ?
        WHERE a.account_id = ?
        """,
        (end, f"-{days} days", end, account_id),
    )) or {}
    limit = result.get("credit_limit") or 0
    spend = result.get("spend_in_window") or 0
    result["pct_of_limit"] = round(100 * spend / limit, 1) if limit else None
    result["window_days"] = days
    return result


# ==========================================================================
# The free text. This is where the verdict usually is.
# ==========================================================================
#
# Two facts about this schema decide roughly a third of the queue:
#
# 1. `case_notes` and `prior_cases` are keyed on `customer_id`, not
#    `account_id`. Every query joins through `accounts` to make that hop. An
#    analyst that cannot make it returns nothing on every account whose
#    explanation was typed by a colleague.
#
# 2. *When* a note was written changes what it means. A note filed before the
#    alert is a pre-existing explanation and tends to exonerate. One filed
#    after is the customer's reaction, and "I did not make these" corroborates
#    fraud rather than explaining it. Language models are poor at date
#    arithmetic, so every row carries `days_before_alert` and a plain
#    `timing` label computed in SQL.

_TIMING = """
    ROUND(julianday(ref.t) - julianday({col}), 1) AS days_before_alert,
    CASE WHEN {col} <= ref.t THEN 'before_alert' ELSE 'after_alert' END AS timing
"""

_REF = "(SELECT MAX(triggered_at) AS t FROM alerts WHERE account_id = ?) ref"


def case_notes(account_id: str) -> list[dict]:
    """Everything staff wrote about this customer, newest first.

    The join through `accounts` is the hop the assignment calls the whole
    exercise. Without it this returns nothing on every account.
    """
    return _rows(db.query(
        f"""
        SELECT n.note_id, n.created_at, n.author, n.channel, n.note,
               {_TIMING.format(col="n.created_at")}
        FROM case_notes n
        JOIN accounts a ON a.customer_id = n.customer_id
        CROSS JOIN {_REF}
        WHERE a.account_id = ?
        ORDER BY n.created_at DESC
        """,
        (account_id, account_id),
    ))


def disputes(account_id: str) -> list[dict]:
    """The customer's own words about charges they are challenging.

    Disputing is not proof of fraud. 10.4 (unauthorised) points one way; 13.1
    (goods not received) is a merchant problem and 13.7 (cancelled) is often a
    subscription the customer forgot about.
    """
    return _rows(db.query(
        f"""
        SELECT d.dispute_id, d.txn_id, d.filed_at, d.reason_code,
               d.customer_statement, d.status,
               t.ts AS txn_ts, t.amount, t.ip_country,
               m.name AS merchant_name, m.category AS merchant_category,
               {_TIMING.format(col="d.filed_at")}
        FROM disputes d
        JOIN transactions t ON t.txn_id = d.txn_id
        LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
        CROSS JOIN {_REF}
        WHERE t.account_id = ?
        ORDER BY d.filed_at DESC
        """,
        (account_id, account_id),
    ))


def prior_cases(account_id: str) -> list[dict]:
    """Previous investigations and how they closed.

    Three prior false positives is a different customer from one with a
    confirmed compromise last year. Neither decides the case in front of you.
    """
    return _rows(db.query(
        """
        SELECT p.case_id, p.opened_date, p.closed_date, p.outcome, p.summary
        FROM prior_cases p
        JOIN accounts a ON a.customer_id = p.customer_id
        WHERE a.account_id = ?
        ORDER BY p.opened_date DESC
        """,
        (account_id,),
    ))


# ==========================================================================
# Cross-account structure
# ==========================================================================
#
# Sixteen devices in this book are shared between customers. Some are mule
# rings and some are married couples with a family tablet. These queries
# return the two facts that separate the cases - how long the sharing has gone
# on, and whether the other party has any history - rather than a score.
#
# Every query here is bounded. An unbounded self-join on a 108,000-row
# transactions table is a full scan per candidate, and across 276 accounts
# that is the difference between a sweep that finishes and one that does not.

def shared_devices(account_id: str) -> list[dict]:
    """Devices this customer shares with someone else, and since when.

    `days_shared_before_incident` is the deciding field. Sharing that predates
    the incident by months is a household; sharing that began days before it
    is not.
    """
    window = incident_window(account_id)
    anchor = window["incident_start"] if window else None
    return _rows(db.query(
        """
        SELECT d.device_id, d.os, d.device_type,
               d.first_seen         AS device_registered,
               mine.first_seen      AS our_first_seen,
               mine.last_seen       AS our_last_seen,
               theirs.customer_id   AS other_customer_id,
               other_c.full_name    AS other_customer_name,
               other_c.segment      AS other_segment,
               other_c.home_country AS other_home_country,
               theirs.first_seen    AS their_first_seen,
               MIN(mine.first_seen, theirs.first_seen) AS sharing_since,
               ROUND(julianday(?)
                     - julianday(MIN(mine.first_seen, theirs.first_seen)), 0)
                    AS days_shared_before_incident
        FROM accounts a
        JOIN customer_devices mine   ON mine.customer_id = a.customer_id
        JOIN devices d               ON d.device_id = mine.device_id
        JOIN customer_devices theirs ON theirs.device_id = mine.device_id
                                    AND theirs.customer_id != a.customer_id
        JOIN customers other_c       ON other_c.customer_id = theirs.customer_id
        WHERE a.account_id = ?
        ORDER BY sharing_since
        """,
        (anchor, account_id),
    ))


def device_peers(account_id: str) -> list[dict]:
    """The other accounts on those shared devices, with their own history.

    This is what separates a mule ring from a family. A peer with a confirmed
    compromise is a network signal; a spouse with a clean file is not.
    """
    return _rows(db.query(
        """
        SELECT peer_a.account_id,
               peer_c.full_name,
               peer_c.segment,
               peer_a.opened_date,
               MIN(theirs.first_seen) AS peer_device_since,
               COUNT(DISTINCT al.alert_id) AS peer_open_alerts,
               COUNT(DISTINCT CASE WHEN pc.outcome = 'confirmed_fraud'
                                   THEN pc.case_id END) AS peer_confirmed_fraud,
               COUNT(DISTINCT CASE WHEN pc.outcome = 'false_positive'
                                   THEN pc.case_id END) AS peer_false_positives
        FROM accounts a
        JOIN customer_devices mine   ON mine.customer_id = a.customer_id
        JOIN customer_devices theirs ON theirs.device_id = mine.device_id
                                    AND theirs.customer_id != a.customer_id
        JOIN accounts peer_a         ON peer_a.customer_id = theirs.customer_id
        JOIN customers peer_c        ON peer_c.customer_id = peer_a.customer_id
        LEFT JOIN alerts al          ON al.account_id = peer_a.account_id
        LEFT JOIN prior_cases pc     ON pc.customer_id = peer_a.customer_id
        WHERE a.account_id = ?
        GROUP BY peer_a.account_id
        ORDER BY peer_confirmed_fraud DESC, peer_open_alerts DESC
        """,
        (account_id,),
    ))


def merchant_overlap(account_id: str, days: int = 30, limit: int = 8) -> list[dict]:
    """High-risk merchants near the incident, with the fraud base rate attached.

    `accounts_with_confirmed_fraud` alone is meaningless: a busy merchant
    scores high because it is busy. Each row carries `total_accounts_using`
    and a `lift` - this merchant's fraud rate over the whole book's. A lift
    near 1.0 is exactly what popularity predicts and is not evidence.
    """
    window = incident_window(account_id)
    if not window:
        return []
    end = window["incident_end"]

    total_customers = db.scalar("SELECT COUNT(*) FROM customers") or 1
    fraud_customers = db.scalar(
        "SELECT COUNT(DISTINCT customer_id) FROM prior_cases WHERE outcome = 'confirmed_fraud'"
    ) or 0
    book_rate = fraud_customers / total_customers if total_customers else 0

    results = _rows(db.query(
        f"""
        WITH ours AS (
            SELECT DISTINCT t.merchant_id
            FROM transactions t
            JOIN merchants m ON m.merchant_id = t.merchant_id
            WHERE t.account_id = ?
              AND m.category IN ('crypto', 'giftcard', 'moneytransfer', 'gaming')
              AND t.ts BETWEEN {ISO}?, ?) AND ?
        )
        SELECT m.merchant_id, m.name, m.category, m.risk_score,
               COUNT(DISTINCT pt.account_id) AS total_accounts_using,
               COUNT(DISTINCT CASE WHEN pc.outcome = 'confirmed_fraud'
                                   THEN pt.account_id END)
                    AS accounts_with_confirmed_fraud
        FROM ours
        JOIN merchants m     ON m.merchant_id = ours.merchant_id
        JOIN transactions pt ON pt.merchant_id = ours.merchant_id
                             AND pt.account_id != ?
        JOIN accounts peer   ON peer.account_id = pt.account_id
        LEFT JOIN prior_cases pc ON pc.customer_id = peer.customer_id
        GROUP BY m.merchant_id
        ORDER BY accounts_with_confirmed_fraud DESC
        LIMIT ?
        """,
        (account_id, end, f"-{days} days", end, account_id, limit),
    ))

    for r in results:
        using = r.get("total_accounts_using") or 0
        fraud = r.get("accounts_with_confirmed_fraud") or 0
        rate = fraud / using if using else 0
        r["merchant_fraud_rate"] = round(rate, 3)
        r["book_fraud_rate"] = round(book_rate, 3)
        r["lift"] = round(rate / book_rate, 2) if book_rate else None
        r["reading"] = (
            "no more than popularity predicts"
            if r["lift"] is not None and r["lift"] < 1.5
            else "over-represented among fraud accounts"
        )
    return results


def shared_device_summary() -> list[dict]:
    """Every device used by more than one customer. Used by analysis, not agents."""
    return _rows(db.query(
        """
        SELECT cd.device_id,
               COUNT(DISTINCT cd.customer_id) AS customers,
               MIN(cd.first_seen) AS earliest_registration,
               GROUP_CONCAT(DISTINCT cd.customer_id) AS customer_ids
        FROM customer_devices cd
        GROUP BY cd.device_id
        HAVING customers > 1
        ORDER BY customers DESC
        """
    ))
