"""The customer and account behind an alerted account id.

Almost every other query needs the customer_id, because the free text is keyed
on the customer rather than the account. This module is where that hop starts.
"""

from __future__ import annotations

from sentinel.db import db
from sentinel.repositories._rows import row


def profile(account_id: str) -> dict | None:
    """Customer and account attributes that change what 'normal' means.

    Segment drives the expected spending pattern and credit limit; KYC level
    changes how much weight an unexplained anomaly should carry.
    """
    return row(
        db.one(
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
        )
    )


def customer_id(account_id: str) -> str | None:
    return db.scalar("SELECT customer_id FROM accounts WHERE account_id = ?", (account_id,))


def cards(account_id: str) -> list[dict]:
    return [dict(r) for r in db.query(
        "SELECT card_id, last4, issued_date, status FROM cards WHERE account_id = ?",
        (account_id,),
    )]
