"""Tools for the Context specialist: the free text, and nothing else.

This agent holds no transaction tools at all. It cannot compute a velocity or
see an amount, which is deliberate - its job is to report what people wrote,
not to re-litigate whether the spending looks odd.

Every query here joins `case_notes`, `disputes` and `prior_cases` back to the
account through `customers`. Those tables are keyed on customer_id, not
account_id. An analyst that cannot make that hop returns nothing on every
account whose explanation was typed by a colleague, which is roughly a third of
this queue.
"""

from __future__ import annotations

from langchain.tools import tool

from sentinel.repositories import customer_repo, narrative_repo
from sentinel.tools._render import as_json, empty

TIMING_NOTE = (
    "TIMING IS EVIDENCE. Each record carries `timing` and `days_before_alert`. "
    "A record filed BEFORE the incident is a pre-existing explanation and tends "
    "to exonerate: a travel notice, a verified phone upgrade. A record filed "
    "AFTER the incident is the customer's reaction to it, and 'I did not make "
    "these' is corroboration of fraud, not an explanation of it. Positive "
    "days_before_alert means before; negative means after."
)


@tool
def get_customer_profile(account_id: str) -> str:
    """Who this customer is: segment, KYC level, home country, tenure, credit limit.

    Use for: establishing what normal means before you read anything else. A
    student and a business customer have different baselines, and a fully
    KYC-verified customer of two years is a different prior from a thin file.

    Args:
        account_id: The flagged account, e.g. 'A00985'.
    """
    profile = customer_repo.profile(account_id)
    if not profile:
        return empty(f"No customer found for {account_id}.")
    return as_json(profile)


@tool
def get_case_notes(account_id: str) -> str:
    """Everything bank staff wrote about this customer, with timing against the incident.

    Use for: the single most important question in this job - did the customer
    already explain this? Read every note in full. Quote the deciding sentence
    verbatim in your finding and name its note_id, because the supervisor
    cannot see this tool result.

    Check three things on any note that appears to explain the incident:
      1. Timing - was it written before the incident, or after it?
      2. Subject - does it explain THIS anomaly? A travel notice to the
         Netherlands does not explain transactions from the UAE.
      3. Dates - a note saying the phone was upgraded 'on the 14th' only
         explains a new device that appeared around the 14th.

    Args:
        account_id: The flagged account.
    """
    notes = narrative_repo.case_notes(account_id)
    if not notes:
        return empty(
            f"There are no case notes for the customer behind {account_id}. "
            f"Nobody has recorded an explanation. If the behaviour is anomalous "
            f"and nothing else explains it, this silence is what makes the case "
            f"unresolvable rather than fraudulent."
        )
    return as_json({"case_notes": notes}, note=TIMING_NOTE)


@tool
def get_disputes(account_id: str) -> str:
    """Charges this customer has formally challenged, in their own words.

    Use for: hearing the customer directly. Read reason_code carefully, because
    disputing a charge is not proof of fraud:
      10.4 unauthorised        - the customer denies making it. Fraud-leaning.
      13.1 goods not received  - a merchant problem, not an account compromise.
      13.7 cancelled           - often a subscription or an order they cancelled.

    A dispute filed on the incident's own transactions is far stronger evidence
    than an unrelated dispute from two months earlier, so check which
    transactions the dispute actually covers.

    Args:
        account_id: The flagged account.
    """
    disputes = narrative_repo.disputes(account_id)
    if not disputes:
        return empty(
            f"{account_id} has no disputes on file. The customer has not "
            f"challenged any transaction on this account."
        )
    return as_json({"disputes": disputes}, note=TIMING_NOTE)


@tool
def get_prior_cases(account_id: str) -> str:
    """How previous investigations into this customer closed.

    Use for: setting the prior. Outcomes are confirmed_fraud, false_positive or
    insufficient_evidence. A customer with three prior false positives is
    behaving the way they always have. One with a confirmed compromise last
    year deserves less benefit of the doubt.

    This is context, not a verdict. A prior confirmed fraud does not make this
    incident fraud, and prior false positives do not make it legitimate.

    Args:
        account_id: The flagged account.
    """
    cases = narrative_repo.prior_cases(account_id)
    if not cases:
        return empty(
            f"{account_id} has no prior investigations. There is no history to "
            f"weigh either way."
        )
    return as_json({"prior_cases": cases})


CONTEXT_TOOLS = [
    get_customer_profile,
    get_case_notes,
    get_disputes,
    get_prior_cases,
]
