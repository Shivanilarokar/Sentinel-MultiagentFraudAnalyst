"""The free text. This is where the verdict usually is.

Two facts about this schema decide roughly a third of the queue:

1.  `case_notes` and `prior_cases` are keyed on `customer_id`, not
    `account_id`. Every query here joins through `accounts` to make that hop.
    An analyst that cannot make it fails on every case whose explanation was
    typed by a colleague.

2.  *When* a note was written changes what it means. A note filed before the
    alert is a pre-existing explanation and tends to exonerate: a travel
    notice, a phone upgrade verified by video KYC. A note filed after the
    alert is the customer's reaction, and "I did not make these transactions"
    is corroboration of fraud, not an explanation of it.

Language models are poor at date arithmetic, so rather than hand over two
timestamps and hope, every row carries `days_before_alert` and a plain-English
`timing` label computed in SQL.
"""

from __future__ import annotations

from sentinel.db import db
from sentinel.repositories._rows import rows

# Positive days_before_alert  -> written BEFORE the rule fired (pre-existing)
# Negative days_before_alert  -> written AFTER  the rule fired (a reaction)
_TIMING = """
    ROUND(julianday(ref.t) - julianday({col}), 1) AS days_before_alert,
    CASE WHEN {col} <= ref.t THEN 'before_alert' ELSE 'after_alert' END AS timing
"""

_REF = """
    (SELECT MAX(triggered_at) AS t FROM alerts WHERE account_id = ?) ref
"""


def case_notes(account_id: str) -> list[dict]:
    """Everything staff wrote about this customer, newest first.

    The join through `accounts` is the hop the assignment calls the whole
    exercise. Without it this returns nothing on every account.
    """
    sql = f"""
        SELECT n.note_id, n.created_at, n.author, n.channel, n.note,
               {_TIMING.format(col="n.created_at")}
        FROM case_notes n
        JOIN accounts a ON a.customer_id = n.customer_id
        CROSS JOIN {_REF}
        WHERE a.account_id = ?
        ORDER BY n.created_at DESC
    """
    return rows(db.query(sql, (account_id, account_id)))


def disputes(account_id: str) -> list[dict]:
    """The customer's own words about charges they are challenging.

    Disputing a charge is not proof of fraud. Reason code 10.4 (unauthorised)
    points one way; 13.1 (goods not received) is a merchant problem and 13.7
    (cancelled) is often a subscription the customer forgot about.
    """
    sql = f"""
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
    """
    return rows(db.query(sql, (account_id, account_id)))


def prior_cases(account_id: str) -> list[dict]:
    """Previous investigations and how they closed.

    Three prior false positives is a different customer from one with a
    confirmed compromise last year. Outcomes are confirmed_fraud,
    false_positive or insufficient_evidence.
    """
    return rows(
        db.query(
            """
            SELECT p.case_id, p.opened_date, p.closed_date, p.outcome, p.summary
            FROM prior_cases p
            JOIN accounts a ON a.customer_id = p.customer_id
            WHERE a.account_id = ?
            ORDER BY p.opened_date DESC
            """,
            (account_id,),
        )
    )


def has_any_narrative(account_id: str) -> bool:
    """True if there is any free text at all. False means the file is silent."""
    return bool(case_notes(account_id) or disputes(account_id) or prior_cases(account_id))
