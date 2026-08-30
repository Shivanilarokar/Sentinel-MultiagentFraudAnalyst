"""Tools for the Network specialist: cross-account structure only.

This agent answers one question - is this account acting alone? It can see
other customers' devices and merchants, and it deliberately cannot see this
account's own transaction history or its case notes. Those belong to
Behaviour and Context, and duplicating them here would blur who found what.

Sixteen devices in this book are shared between customers. Some of those are
mule rings and some are married couples with a family tablet. These tools
return the facts that separate the two rather than a score.
"""

from __future__ import annotations

from langchain.tools import tool

from sentinel import queries
from sentinel.tools import as_json, empty


@tool
def get_shared_devices(account_id: str) -> str:
    """Devices this customer shares with another customer, and since when.

    Use for: deciding whether device sharing is a household or a ring. The
    deciding field is days_shared_before_incident. A device shared since the
    account opened is a family tablet. One first shared days before the
    incident is not.

    Sharing a device is a signal, not an answer. Report the duration and let
    the supervisor weigh it against what Context found.

    Args:
        account_id: The flagged account, e.g. 'A00985'.
    """
    devices = queries.shared_devices(account_id)
    if not devices:
        return empty(
            f"No device belonging to {account_id} is used by any other customer. "
            f"On the device dimension this account is isolated, which is evidence "
            f"against a coordinated ring."
        )
    return as_json({"shared_devices": devices})


@tool
def get_device_peers(account_id: str) -> str:
    """The other accounts on those shared devices, and each one's own history.

    Use for: the question that actually separates a mule ring from a family.
    A peer with peer_confirmed_fraud above zero, or with open alerts of its
    own, is a network signal. A peer with a clean file and years of shared
    history is a spouse.

    Args:
        account_id: The flagged account.
    """
    peers = queries.device_peers(account_id)
    if not peers:
        return empty(
            f"{account_id} has no accounts linked to it by a shared device."
        )
    return as_json({"device_peers": peers})


@tool
def get_merchant_overlap(account_id: str) -> str:
    """High-risk merchants used near the incident, with the fraud base rate attached.

    Use for: cash-out and mule typologies. Read `lift`, not the raw count.
    A busy merchant is used by many fraud accounts simply because it is busy;
    lift compares this merchant's fraud rate against the whole book. Below
    about 1.5 the overlap is what popularity predicts and is not evidence.
    The `reading` field states which case each row falls into.

    Args:
        account_id: The flagged account.
    """
    overlap = queries.merchant_overlap(account_id)
    if not overlap:
        return empty(
            f"{account_id} used no high-risk merchants near the incident, so "
            f"there is no merchant overlap to assess."
        )
    return as_json({"merchant_overlap": overlap})


NETWORK_TOOLS = [
    get_shared_devices,
    get_device_peers,
    get_merchant_overlap,
]
