"""Behaviour tools: is this spending normal *for this customer*?

Layer 1. Exact arguments in, real rows out. No judgement is made here — these
tools report what happened and leave what it means to the specialist.

Every tool formats its rows as compact text rather than JSON. Across 276
accounts the difference is thousands of tokens per run, and a model reads an
aligned table at least as well as it reads a nested object.
"""

from __future__ import annotations

from langchain.tools import tool

from sentinel import queries


def _none(what: str) -> str:
    """One consistent way of saying nothing was found.

    Silence is a finding. An account with no baseline is a new account, and the
    specialist needs to be told that plainly rather than handed an empty table.
    """
    return f"(no {what} found)"


@tool
def get_alerts(account_id: str) -> str:
    """What the rules engine flagged on this account, and what each rule looks for.

    Start here. The rule description tells you what a *false positive* of that
    rule looks like, which is what you are really being asked to judge.

    Args:
        account_id: The account under investigation, e.g. 'A00985'.
    """
    rows = queries.get_alerts(account_id)
    if not rows:
        return _none("alerts")

    out = [f"{len(rows)} alert(s) on {account_id}:"]
    for r in rows:
        out.append(
            f"\n  {r['alert_id']}  {r['rule_id']} {r['rule_name']}  "
            f"[{r['severity']}]  fired {r['triggered_at']}"
        )
        out.append(f"    rule looks for : {r['rule_description']}")
        if r["trigger_txn_id"]:
            out.append(
                f"    trigger txn    : {r['trigger_txn_id']} at {r['trigger_txn_ts']}, "
                f"{r['trigger_amount']:,.0f}, {r['trigger_channel']}, "
                f"ip={r['trigger_ip_country']}, merchant={r['trigger_merchant']} "
                f"({r['trigger_merchant_category']})"
            )
    out.append(
        "\nNote: the trigger transaction often happens AFTER triggered_at. "
        "Use get_incident_activity for the full episode."
    )
    return "\n".join(out)


@tool
def get_incident_activity(account_id: str) -> str:
    """Every transaction in the incident window, oldest first.

    This is the episode the alerts are about. The window spans both the alert
    timestamps and their trigger transactions, so it contains activity a simple
    lookback from the alert time would miss.

    Args:
        account_id: The account under investigation.
    """
    rows = queries.get_incident_activity(account_id)
    if not rows:
        return _none("transactions in the incident window")

    lo, hi = queries.incident_window(account_id)
    total = sum(r["amount"] for r in rows)
    approved = sum(1 for r in rows if r["auth_result"] == "approved")

    out = [
        f"Incident window {lo} -> {hi}",
        f"{len(rows)} transactions ({approved} approved), total {total:,.0f}",
        "",
        f"{'txn_id':<10} {'timestamp':<20} {'amount':>10} {'ch':<13} "
        f"{'ip':<3} {'auth':<9} {'device':<8} merchant",
    ]
    for r in rows:
        out.append(
            f"{r['txn_id']:<10} {r['ts']:<20} {r['amount']:>10,.0f} "
            f"{r['channel']:<13} {r['ip_country']:<3} {r['auth_result']:<9} "
            f"{r['device_id'] or '-':<8} {r['merchant'] or '-'} "
            f"({r['category'] or '-'}, risk {r['risk_score'] if r['risk_score'] is not None else '-'})"
        )
    return "\n".join(out)


@tool
def get_spending_baseline(account_id: str) -> str:
    """What this customer's normal spending looked like over the previous 90 days.

    Abnormality is relative. 200,000 is a spree on a student account and a
    Tuesday on a business one, so compare the incident against THIS baseline
    rather than against a general idea of a large amount.

    Args:
        account_id: The account under investigation.
    """
    b = queries.get_spending_baseline(account_id)
    if not b or not b.get("txn_count"):
        return (
            "(no baseline: this account has no approved transactions in the 90 days "
            "before the incident. A new or dormant account is itself a finding.)"
        )

    hours = ", ".join(f"{h['hour']:02d}:00" for h in b.get("usual_hours", []))
    return "\n".join([
        f"Baseline for {account_id}, 90 days before {b['window_start']}:",
        f"  transactions   : {b['txn_count']} over {b['active_days']} active days",
        f"  median amount  : {b['median_amount']:,.0f}"
        if b.get("median_amount") else "  median amount  : -",
        f"  mean amount    : {b['mean_amount']:,.0f}",
        f"  largest ever   : {b['max_amount']:,.0f}",
        f"  total spend    : {b['total_amount']:,.0f}",
        f"  countries used : {b['countries_used']}",
        f"  devices used   : {b['devices_used']}",
        f"  usual hours    : {hours or '-'}",
    ])


@tool
def get_device_history(account_id: str) -> str:
    """Devices this customer has used, and how old each was when the alert fired.

    `age_days_at_incident` is the number rule R02 turns on. A device first seen
    hours before the incident is a different story from one seen for months —
    but a genuinely new device is also what a phone upgrade looks like.

    Args:
        account_id: The account under investigation.
    """
    rows = queries.get_device_history(account_id)
    if not rows:
        return _none("devices")

    out = [
        f"{'device':<9} {'type':<8} {'os':<10} {'first seen':<20} "
        f"{'age at incident':>16} {'txns':>6}"
    ]
    for r in rows:
        age = r["age_days_at_incident"]
        age_txt = f"{age:.1f} days" if age is not None else "-"
        out.append(
            f"{r['device_id']:<9} {r['device_type'] or '-':<8} {r['os'] or '-':<10} "
            f"{r['customer_first_seen']:<20} {age_txt:>16} {r['txns_on_device']:>6}"
        )
    return "\n".join(out)


@tool
def get_geography(account_id: str) -> str:
    """Where this account normally transacts, against where it just did.

    A foreign country is only a signal if it is new. Compare the two lists
    before concluding anything: 'IN' is the home country.

    Args:
        account_id: The account under investigation.
    """
    g = queries.get_geography(account_id)
    if not g:
        return _none("geography")

    out = ["Baseline, 90 days before the incident:"]
    out += [
        f"  {r['ip_country']}  {r['n']:>4} txns  {r['total']:>12,.0f}"
        for r in g["baseline_90d"]
    ] or ["  (none)"]

    out.append("\nDuring the incident window:")
    out += [
        f"  {r['ip_country']}  {r['n']:>4} txns  {r['total']:>12,.0f}  "
        f"{r['first_ts']} -> {r['last_ts']}"
        for r in g["incident"]
    ] or ["  (none)"]

    seen = {r["ip_country"] for r in g["baseline_90d"]}
    new = [r["ip_country"] for r in g["incident"] if r["ip_country"] not in seen]
    out.append(
        f"\nCountries new to this account during the incident: "
        f"{', '.join(new) if new else 'none'}"
    )
    return "\n".join(out)


@tool
def get_high_risk_merchant_activity(account_id: str) -> str:
    """Crypto, gift card and money transfer spend, incident against history.

    Legitimate customers use these categories. What separates a cash-out from a
    habit is whether this customer has ever used them before, so both are shown.

    Args:
        account_id: The account under investigation.
    """
    h = queries.get_high_risk_merchant_activity(account_id)
    if not h:
        return _none("high-risk merchant activity")

    out = ["During the incident:"]
    out += [
        f"  {r['ts']}  {r['amount']:>10,.0f}  {r['auth_result']:<9} "
        f"{r['merchant']} ({r['category']}, {r['country']}, risk {r['risk_score']})"
        for r in h["incident"]
    ] or ["  (none)"]

    out.append("\nSame categories in the 90 days before:")
    out += [
        f"  {r['category']:<14} {r['n']:>4} txns  {r['total']:>12,.0f}"
        for r in h["history_90d"]
    ] or ["  (none — these categories are new to this account)"]
    return "\n".join(out)


@tool
def get_limit_utilisation(account_id: str) -> str:
    """Incident spend measured against the account's credit limit and segment.

    Rule R08 fires on limit approach. Whether that is alarming depends on the
    limit, which depends on the segment, so all three are returned together.

    Args:
        account_id: The account under investigation.
    """
    u = queries.get_limit_utilisation(account_id)
    if not u:
        return _none("limit information")

    lines = [
        f"  segment        : {u['segment']}  (kyc {u['kyc_level']})",
        f"  product        : {u['product']}, account status {u['status']}",
        f"  credit limit   : {u['credit_limit']:,.0f}",
    ]
    if u.get("incident_spend"):
        lines += [
            f"  incident spend : {u['incident_spend']:,.0f} "
            f"over {u['incident_txns']} approved transactions",
            f"  utilisation    : {u.get('utilisation_pct', 0)}% of the limit",
        ]
    else:
        lines.append("  incident spend : none approved in the window")
    return "\n".join(lines)


# The registry. `tools/__init__.py` asserts this set is disjoint from every
# other domain's, so a tool cannot quietly end up in two specialists.
BEHAVIOUR_TOOLS = [
    get_alerts,
    get_incident_activity,
    get_spending_baseline,
    get_device_history,
    get_geography,
    get_high_risk_merchant_activity,
    get_limit_utilisation,
]
