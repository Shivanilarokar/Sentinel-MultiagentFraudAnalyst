"""Network tools: is this account acting alone?

The smallest domain, and the one most easily over-read. 16 devices in this
database are shared between customers. Some of those are mule rings. Some are
married couples with a family tablet.

Sharing is a signal, not an answer. These tools therefore return the peers and
what is known about them, never a conclusion. What distinguishes a ring from a
household is whether the peers are strangers who are also flagged.
"""

from __future__ import annotations

from langchain.tools import tool

from sentinel import queries


@tool
def get_shared_devices(account_id: str) -> str:
    """Devices this customer shares with at least one other customer.

    Most accounts share nothing, and that is a finding in itself: an isolated
    account is unlikely to be part of an organised ring.

    Args:
        account_id: The account under investigation, e.g. 'A00985'.
    """
    rows = queries.get_shared_devices(account_id)
    if not rows:
        return (
            "(no shared devices — every device this customer uses is theirs alone. "
            "This account is not linked to others by hardware.)"
        )

    out = [f"{len(rows)} shared device(s):"]
    for r in rows:
        out.append(
            f"  {r['device_id']}  {r['device_type'] or '-'} / {r['os'] or '-'}  "
            f"used by {r['customers_on_device']} customers  "
            f"(this customer since {r['first_seen']}, last {r['last_seen']})"
        )
    return "\n".join(out)


@tool
def get_device_peers(account_id: str) -> str:
    """Who else uses this customer's devices, and whether they are flagged too.

    This is the question that separates the two readings of a shared device:

      - peers who are ALSO alerted this weekend, especially with prior confirmed
        fraud, look like a ring
      - a single peer with no alerts and no history looks like a household

    Args:
        account_id: The account under investigation.
    """
    rows = queries.get_device_peers(account_id)
    if not rows:
        return "(no other customers use this customer's devices)"

    out = [f"{len(rows)} peer(s) on shared devices:"]
    for r in rows:
        flags = []
        if r["peer_alert_count"]:
            flags.append(f"{r['peer_alert_count']} alert(s) this weekend")
        if r["peer_confirmed_fraud"]:
            flags.append(f"{r['peer_confirmed_fraud']} prior confirmed fraud")
        out.append(
            f"  {r['customer_id']}  {r['full_name']}  ({r['segment']}, "
            f"{r['home_country']})  on device {r['device_id']} since "
            f"{r['peer_first_seen']}\n"
            f"      {'; '.join(flags) if flags else 'no alerts, no prior fraud'}"
        )
    return "\n".join(out)


@tool
def get_merchant_overlap(account_id: str) -> str:
    """Merchants hit during this incident that other flagged accounts also hit.

    A merchant several flagged accounts touched in the same weekend can be a
    cash-out point. A supermarket everybody uses is not, which is why the count
    shown is of *other alerted accounts* rather than raw popularity.

    Args:
        account_id: The account under investigation.
    """
    rows = queries.get_merchant_overlap(account_id)
    if not rows:
        return "(no merchant activity in the incident window)"

    shared = [r for r in rows if r["other_alerted_accounts"]]
    out = [
        f"{len(rows)} merchant(s) used during the incident; "
        f"{len(shared)} also used by other flagged accounts:"
    ]
    for r in rows:
        marker = (f"  <- shared with {r['other_alerted_accounts']} other flagged account(s)"
                  if r["other_alerted_accounts"] else "")
        out.append(
            f"  {r['merchant']} ({r['category']}, {r['country']}, "
            f"risk {r['risk_score']})  our spend {r['our_spend']:,.0f}{marker}"
        )
    if not shared:
        out.append(
            "\nNo merchant overlap with other flagged accounts. On its own this "
            "points away from a coordinated ring."
        )
    return "\n".join(out)


# The registry. Read-only, and disjoint from every other domain.
NETWORK_TOOLS = [
    get_shared_devices,
    get_device_peers,
    get_merchant_overlap,
]
