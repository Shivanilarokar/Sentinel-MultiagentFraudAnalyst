"""Tools for the Behaviour specialist: transaction history only.

This agent answers one question - is this spending normal *for this customer* -
and it holds nothing that could answer any other. It cannot read a case note,
cannot see another account, and cannot write anything.

Every window is anchored on the incident, not on today. See
`repositories/alerts_repo` for why that distinction decides the numbers.
"""

from __future__ import annotations

from langchain.tools import tool

from sentinel.repositories import alerts_repo, transactions_repo
from sentinel.tools._render import as_json, empty


@tool
def get_alerts(account_id: str) -> str:
    """Which rules fired on this account, when, and what each rule looks for.

    Use for: establishing what you are actually being asked to explain. Always
    call this first. The rule descriptions tell you what a false positive of
    that rule would look like, which is usually more useful than the alert.

    Args:
        account_id: The flagged account, e.g. 'A00985'.
    """
    alerts = alerts_repo.for_account(account_id)
    if not alerts:
        return empty(f"{account_id} has no alerts.")
    window = alerts_repo.incident_window(account_id)
    return as_json(
        {"incident_window": window, "alerts": alerts},
        note=(
            "NOTE: triggered_at marks the START of the flagged episode. The "
            "transaction named by trigger_txn_id usually happens after it. "
            "Reason about the whole incident window, not a single instant."
        ),
    )


@tool
def get_incident_activity(account_id: str) -> str:
    """Every transaction inside the flagged episode, plus the ones that tripped the rules.

    Use for: seeing exactly what happened - amounts, times, countries,
    merchants, approve/decline. This is the set you will be citing, so read it
    before forming a view.

    Args:
        account_id: The flagged account.
    """
    triggers = alerts_repo.trigger_transactions(account_id)
    incident = transactions_repo.incident_transactions(account_id)
    if not incident and not triggers:
        return empty(f"No transactions found in the incident window for {account_id}.")
    return as_json({"trigger_transactions": triggers, "incident_transactions": incident})


@tool
def get_spending_baseline(account_id: str) -> str:
    """The customer's normal spending, next to what happened in the incident.

    Use for: deciding whether the incident is actually abnormal. The baseline
    deliberately excludes the seven days before the incident, so it is not
    contaminated by the event you are judging. Compare avg_amount and
    max_amount against the incident's largest_amount, and night_txn_rate
    against night_txns.

    Args:
        account_id: The flagged account.
    """
    return as_json(
        {
            "baseline_excluding_incident": transactions_repo.baseline(account_id),
            "incident_window_24h": transactions_repo.velocity(account_id, 24),
            "incident_window_1h": transactions_repo.velocity(account_id, 1),
        }
    )


@tool
def get_device_history(account_id: str) -> str:
    """Devices this account transacted from, and how old each was at the incident.

    Use for: any alert mentioning a new device (R02). The field that decides it
    is device_age_hours_at_incident. A device registered hours before the spend
    is the account-takeover signature; it is also the signature of somebody who
    upgraded their phone, so this tool tells you the age and not the answer.

    Args:
        account_id: The flagged account.
    """
    devices = transactions_repo.device_usage(account_id)
    if not devices:
        return empty(f"No device history for {account_id}.")
    return as_json({"devices": devices})


@tool
def get_geography(account_id: str) -> str:
    """Every country this account has ever transacted from, with first and last use.

    Use for: impossible-travel and foreign-IP alerts (R03). first_seen is the
    field that matters: a country used for months is not the same fact as one
    that appears for the first time inside the incident. Home country is IN.

    Args:
        account_id: The flagged account.
    """
    geo = transactions_repo.geo_pattern(account_id)
    if not geo:
        return empty(f"No transactions for {account_id}.")
    return as_json({"countries": geo})


@tool
def get_high_risk_merchant_activity(account_id: str) -> str:
    """Crypto, gift card, money transfer and gaming spend near the incident.

    Use for: R05 (high risk merchant burst) and for any case where money looks
    like it is being moved out rather than spent. These categories carry the
    highest risk scores in the book and are also used by ordinary customers, so
    treat volume and timing as the signal, not the category alone.

    Args:
        account_id: The flagged account.
    """
    rows = transactions_repo.high_risk_merchant_activity(account_id)
    if not rows:
        return empty(
            f"{account_id} made no crypto, gift card, money transfer or gaming "
            f"transactions in the 30 days before the incident ended. That absence "
            f"is itself evidence against a cash-out typology."
        )
    return as_json({"high_risk_transactions": rows})


@tool
def get_limit_utilisation(account_id: str) -> str:
    """Approved spend against the credit limit over the closing 48 hours.

    Use for: R08 (limit approach), which fires at 90 percent of the limit in 48
    hours. pct_of_limit above 100 means the episode exceeded the whole limit,
    which is a strong signal on its own.

    Args:
        account_id: The flagged account.
    """
    return as_json(transactions_repo.limit_utilisation(account_id))


BEHAVIOUR_TOOLS = [
    get_alerts,
    get_incident_activity,
    get_spending_baseline,
    get_device_history,
    get_geography,
    get_high_risk_merchant_activity,
    get_limit_utilisation,
]
