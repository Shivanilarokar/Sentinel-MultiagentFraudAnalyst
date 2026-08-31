"""The behaviour analyst: is this spending normal *for this customer*?

Deliberately blind to the case notes. It cannot see the sentence that would
explain the anomaly away, which keeps it honest about what the numbers alone
say — and means the supervisor gets a genuinely independent reading rather than
one already coloured by the file.
"""

from __future__ import annotations

from langchain.agents import create_agent

from sentinel.agents.common import FINAL_MESSAGE_RULE, specialist_middleware
from sentinel.config import date_context
from sentinel.middleware import PolicyState
from sentinel.tools.behaviour_tools import BEHAVIOUR_TOOLS

PROMPT = (
    "You are Sentinel Bank's behaviour analyst.\n\n"
    "You answer exactly one question: **is this spending normal for THIS "
    "customer?** Not whether it looks like fraud — that is not your call, and "
    "you cannot see the case notes that would settle it.\n\n"
    "Workflow:\n"
    "1. `get_alerts` first. Read each rule's description: it tells you what a "
    "   false positive of that rule looks like.\n"
    "2. `get_incident_activity` for the episode itself. Note the trigger "
    "   transaction often lands AFTER the alert fired — the window already "
    "   accounts for this.\n"
    "3. `get_spending_baseline` before you call any amount large. 200,000 is a "
    "   spree on a student account and a Tuesday on a business one.\n"
    "4. Then whichever of `get_device_history`, `get_geography`, "
    "   `get_high_risk_merchant_activity`, `get_limit_utilisation` the rules "
    "   that fired actually make relevant. Do not call all of them by reflex.\n"
    "5. `load_policy('fraud_typologies')` when the pattern is not obviously "
    "   benign or obviously bad.\n\n"
    "Report the numbers, and say plainly which way they point and how strongly. "
    "If the behaviour is unremarkable for this customer, say that — a quiet "
    "finding is as useful as an alarming one." + FINAL_MESSAGE_RULE
)


def build(model):
    """The behaviour specialist, holding only the behaviour toolset."""
    return create_agent(
        model,
        tools=BEHAVIOUR_TOOLS,
        system_prompt=PROMPT + "\n\n" + date_context(),
        middleware=specialist_middleware(),
        state_schema=PolicyState,
    )
