"""Cross-account structure: who else touches this account's devices and merchants.

Sixteen devices in this dataset are shared between customers. Some of those are
mule rings and some are married couples with a family tablet. Sharing a device
is a signal, not an answer, so these queries return the two facts that actually
separate the cases - how long the sharing has been going on, and whether the
other party has any history - rather than a score.

The merchant query deserves a warning that is built into its output. Asking
"how many confirmed-fraud accounts also used this merchant?" produces a large
number for any *popular* merchant, whether or not it means anything. So every
row carries the base rate alongside the raw count, and a `lift` figure
comparing the two. Without that, a shared money-transfer merchant used by half
the bank reads as a network signal when it is only a busy shop.

Every query here is bounded. An unbounded self-join on a 108,000-row
transactions table is a full scan per candidate, and across 276 accounts that
is the difference between a sweep that finishes and one that does not.
"""

from __future__ import annotations

from sentinel.db import db
from sentinel.repositories._rows import rows
from sentinel.repositories.alerts_repo import incident_window


def shared_devices(account_id: str) -> list[dict]:
    """Devices this customer shares with someone else, and since when.

    `sharing_since` is the earlier of the two registration dates, and
    `days_shared_before_incident` turns it into the number that decides the
    case. A device shared since the account opened is a household. One first
    shared days before the alert is not.
    """
    window = incident_window(account_id)
    anchor = window["incident_start"] if window else None
    return rows(
        db.query(
            """
            SELECT d.device_id, d.os, d.device_type,
                   d.first_seen        AS device_registered,
                   mine.first_seen     AS our_first_seen,
                   mine.last_seen      AS our_last_seen,
                   theirs.customer_id  AS other_customer_id,
                   other_c.full_name   AS other_customer_name,
                   other_c.segment     AS other_segment,
                   other_c.home_country AS other_home_country,
                   theirs.first_seen   AS their_first_seen,
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
        )
    )


def device_peers(account_id: str) -> list[dict]:
    """The other accounts on those shared devices, with their own history.

    This is the query that separates a mule ring from a household. A peer with
    a confirmed_fraud prior case and open alerts of their own is a network
    signal; a spouse with a clean file is not.
    """
    return rows(
        db.query(
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
        )
    )


def merchant_overlap(account_id: str, days: int = 30, limit: int = 8) -> list[dict]:
    """High-risk merchants used near the incident, with the fraud base rate attached.

    `accounts_with_confirmed_fraud` on its own is meaningless: a busy merchant
    scores high because it is busy. Each row therefore also carries
    `total_accounts_using` and a `lift` - the fraud rate among this merchant's
    customers divided by the fraud rate across the whole book. A lift near 1.0
    means the overlap is exactly what popularity predicts and is not evidence.
    """
    window = incident_window(account_id)
    if not window:
        return []
    end = window["incident_end"]

    # Base rate across the whole customer book, computed once.
    total_customers = db.scalar("SELECT COUNT(*) FROM customers") or 1
    fraud_customers = (
        db.scalar(
            "SELECT COUNT(DISTINCT customer_id) FROM prior_cases "
            "WHERE outcome = 'confirmed_fraud'"
        )
        or 0
    )
    book_rate = fraud_customers / total_customers if total_customers else 0

    results = rows(
        db.query(
            """
            WITH ours AS (
                SELECT DISTINCT t.merchant_id
                FROM transactions t
                JOIN merchants m ON m.merchant_id = t.merchant_id
                WHERE t.account_id = ?
                  AND m.category IN ('crypto', 'giftcard', 'moneytransfer', 'gaming')
                  AND t.ts BETWEEN strftime('%Y-%m-%dT%H:%M:%S', ?, ?) AND ?
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
        )
    )

    for r in results:
        using = r.get("total_accounts_using") or 0
        fraud = r.get("accounts_with_confirmed_fraud") or 0
        merchant_rate = fraud / using if using else 0
        r["merchant_fraud_rate"] = round(merchant_rate, 3)
        r["book_fraud_rate"] = round(book_rate, 3)
        r["lift"] = round(merchant_rate / book_rate, 2) if book_rate else None
        r["reading"] = (
            "no more than popularity predicts"
            if r["lift"] is not None and r["lift"] < 1.5
            else "over-represented among fraud accounts"
        )
    return results


def shared_device_summary() -> list[dict]:
    """Every device in the book used by more than one customer.

    Used by the lookalike analysis and by `sentinel doctor`, not by an agent.
    """
    return rows(
        db.query(
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
        )
    )
