"""Context tools: did the customer already explain this?

This is the module the assignment is really about. The database will readily
report six transactions in forty minutes from a new device. What it will not
volunteer is that a colleague typed an explanation two weeks earlier.

Every narrative row carries a `timing` label computed in SQL:

    before_incident   a pre-existing explanation. The strongest evidence there is.
    during_incident   filed while the episode was running.
    after_incident    the customer's reaction. "I did not make these transactions"
                      CORROBORATES fraud. It does not explain it away.

That distinction is not decoration. Read the wrong way round, the same sentence
flips the verdict, and models are poor enough at date arithmetic that the label
is computed for them rather than left to be inferred.
"""

from __future__ import annotations

from langchain.tools import tool

from sentinel import queries


@tool
def get_customer_profile(account_id: str) -> str:
    """Who this customer is: segment, KYC level, tenure, limit and cards.

    Read this before judging any amount. Segment drives the credit limit and the
    normal spending pattern, and a customer who signed up three weeks ago has no
    baseline to be abnormal against.

    Args:
        account_id: The account under investigation, e.g. 'A00985'.
    """
    p = queries.get_customer_profile(account_id)
    if not p:
        return f"(no customer found for account {account_id})"

    cards = ", ".join(
        f"{c['card_id']} (…{c['last4']}, {c['status']}, issued {c['issued_date']})"
        for c in p["cards"]
    ) or "none"

    return "\n".join([
        f"  customer       : {p['customer_id']}  {p['full_name']}",
        f"  segment        : {p['segment']}   KYC level {p['kyc_level']}",
        f"  home country   : {p['home_country']}",
        f"  signed up      : {p['signup_date']}  ({p['days_since_signup']:.0f} days ago)",
        f"  account        : {p['account_id']}  {p['product']}, {p['status']}, "
        f"opened {p['opened_date']}",
        f"  credit limit   : {p['credit_limit']:,.0f}",
        f"  cards          : {cards}",
    ])


@tool
def get_case_notes(account_id: str) -> str:
    """Everything a colleague wrote about this customer, with timing labels.

    THE MOST IMPORTANT TOOL YOU HAVE. Read every note in full and quote the
    words that matter.

    Check `timing` on each note before you rely on it:
      - before_incident: the customer explained this in advance. Travel notices,
        phone upgrades, expected large purchases. This can settle a case.
      - after_incident: the customer is reacting to what already happened. A
        report of unrecognised charges is evidence OF fraud, not against it.

    If the notes are silent on what the alert flagged, say so — that is what
    'insufficient_evidence' is for.

    Args:
        account_id: The account under investigation.
    """
    rows = queries.get_case_notes(account_id)
    if not rows:
        return (
            "(no case notes exist for this customer. Nobody has written anything "
            "explaining this activity. If the behaviour is unexplained and nothing "
            "else resolves it, 'insufficient_evidence' is the honest verdict — and "
            "you should name what would settle it.)"
        )

    out = [f"{len(rows)} case note(s):"]
    for r in rows:
        days = r["days_before_alert"]
        when = (f"{days:.1f} days before the incident" if days and days > 0
                else f"{abs(days):.1f} days after the incident" if days
                else "at the incident")
        out.append(
            f"\n  {r['note_id']}  {r['created_at']}  [{r['timing']}]  "
            f"{when}\n"
            f"    author  : {r['author']} via {r['channel']}\n"
            f"    note    : \"{r['note']}\""
        )
    return "\n".join(out)


@tool
def get_disputes(account_id: str) -> str:
    """Charges this customer has formally challenged, in their own words.

    Disputing is NOT proof of fraud. Some disputes are chargebacks over goods
    that never arrived; some are a family member who used the card. The
    `customer_statement` is what separates them, so read it rather than counting
    disputes.

    Args:
        account_id: The account under investigation.
    """
    rows = queries.get_disputes(account_id)
    if not rows:
        return "(no disputes filed on this account)"

    out = [f"{len(rows)} dispute(s):"]
    for r in rows:
        out.append(
            f"\n  {r['dispute_id']}  filed {r['filed_at']}  [{r['timing']}]  "
            f"status {r['status']}\n"
            f"    about   : txn {r['txn_id']} on {r['txn_ts']}, "
            f"{r['amount']:,.0f} at {r['merchant'] or '-'} ({r['category'] or '-'})\n"
            f"    reason  : {r['reason_code']}\n"
            f"    says    : \"{r['customer_statement']}\""
        )
    return "\n".join(out)


@tool
def get_prior_cases(account_id: str) -> str:
    """Previous investigations into this customer, and how each one closed.

    A customer with three prior false positives is a different proposition from
    one with a confirmed compromise last year. `outcome` is one of
    confirmed_fraud, false_positive or insufficient_evidence.

    Args:
        account_id: The account under investigation.
    """
    rows = queries.get_prior_cases(account_id)
    if not rows:
        return "(no prior investigations — this customer has not been reviewed before)"

    tally: dict[str, int] = {}
    for r in rows:
        tally[r["outcome"]] = tally.get(r["outcome"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in tally.items())

    out = [f"{len(rows)} prior case(s): {summary}"]
    for r in rows:
        out.append(
            f"\n  {r['case_id']}  {r['opened_date']} -> {r['closed_date'] or 'open'}  "
            f"[{r['outcome']}]\n"
            f"    {r['summary']}"
        )
    return "\n".join(out)


# The registry. Disjoint from behaviour, network and disposition by construction.
CONTEXT_TOOLS = [
    get_customer_profile,
    get_case_notes,
    get_disputes,
    get_prior_cases,
]
