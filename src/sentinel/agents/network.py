"""The network analyst: is this account acting alone?

The smallest domain, and the one most easily over-read. Sixteen devices in this
database are shared between customers. Some are mule rings. Some are married
couples with a family tablet.

Telling those apart is a judgement rather than a count, which is why this
specialist reads the policy documents like the other two.
"""

from __future__ import annotations

from langchain.agents import create_agent

from sentinel.agents.common import FINAL_MESSAGE_RULE, specialist_middleware
from sentinel.config import date_context
from sentinel.middleware import PolicyState
from sentinel.tools.network_tools import NETWORK_TOOLS

PROMPT = (
    "You are Sentinel Bank's network analyst.\n\n"
    "One question: **is this account acting alone?**\n\n"
    "Workflow: `get_shared_devices`, then `get_device_peers` if anything is "
    "shared, then `get_merchant_overlap`.\n\n"
    "Sixteen devices in this database are shared between customers. Some are "
    "mule rings. Some are married couples with a family tablet. What separates "
    "them is who the peers are:\n"
    "  - peers who are THEMSELVES flagged this weekend, or who carry prior "
    "    confirmed fraud, look like a ring\n"
    "  - one peer, no alerts, no history, looks like a household\n\n"
    "Do not report a shared device as suspicious without saying what the peers "
    "look like. And when the account is isolated, say so clearly — 'no shared "
    "devices, no merchant overlap' is a real finding that argues against "
    "organised fraud." + FINAL_MESSAGE_RULE
)


def build(model):
    """The network specialist, holding only the linkage toolset."""
    return create_agent(
        model,
        tools=NETWORK_TOOLS,
        system_prompt=PROMPT + "\n\n" + date_context(),
        middleware=specialist_middleware(),
        state_schema=PolicyState,
    )
