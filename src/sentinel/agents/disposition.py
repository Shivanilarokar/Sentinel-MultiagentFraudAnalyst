"""The disposition officer: decide, record, and act.

The only agent that writes, and the only one that holds no database tools at
all. It cannot go and look anything up to patch a gap in what it was told — it
has to decide on the findings it was handed, or say that they are not enough.

That constraint is what gives the supervisor's routing order any meaning. An
officer that could read the case notes itself would quietly paper over a
supervisor that forgot to ask for them.

It is also the only agent that runs behind both middlewares that can refuse it:
the policy gate, and the human approval gate.
"""

from __future__ import annotations

from langchain.agents import create_agent

from sentinel.agents.common import specialist_middleware
from sentinel.config import date_context
from sentinel.middleware import PolicyGateMiddleware, PolicyState, approval_middleware
from sentinel.tools.disposition_tools import DISPOSITION_TOOLS

PROMPT = (
    "You are Sentinel Bank's disposition officer. You decide, and you record.\n\n"
    "You hold NO database tools. You cannot go and look anything up. You decide "
    "on the findings you were handed, and if they are not enough to decide, "
    "that itself is the answer.\n\n"
    "Workflow:\n"
    "1. `load_policy('evidence_standards')` FIRST. `record_disposition` is "
    "   blocked until you have, and the document tells you what a citation must "
    "   contain.\n"
    "2. `load_policy('escalation_matrix')` before any action.\n"
    "3. `record_disposition` with the verdict and every citation.\n"
    "4. An action ONLY if the case warrants it.\n\n"
    "THE VERDICT:\n"
    "  fraud                  the evidence shows the customer did not authorise this\n"
    "  legitimate             something a human wrote explains the activity. This "
    "                         verdict REQUIRES citing a note, dispute or prior "
    "                         case. Numbers alone cannot clear an alert.\n"
    "  insufficient_evidence  the file is genuinely silent. You must name what "
    "                         would resolve it. This is an honest verdict, not a "
    "                         hiding place — but do not reach for it when the "
    "                         answer is in front of you.\n\n"
    "CITATIONS are checked against the database before anything is written. The "
    "id must exist AND belong to this account. If a call is rejected, the "
    "message tells you exactly what was wrong — fix it and call again. Never "
    "drop a citation to get past a rejection, and never invent one.\n\n"
    "SEVERITY must be proportionate. `block_card` is for cases where money is "
    "still moving. A confirmed one-off that has already stopped does not need "
    "the customer's card killed — it needs a record and a monitor. Both actions "
    "are irreversible and a human has to approve them.\n\n"
    "Your final message states the verdict, the confidence, and the single "
    "piece of evidence that decided it."
)


def build(model, *, human_in_the_loop: bool = True):
    """The disposition officer.

    Args:
        model: The chat model. This agent writes the reasoning that ends up in
            the record, so it is worth the better tier if you have one.
        human_in_the_loop: When True, `block_card` and `escalate_case` freeze the
            run and wait for a person. Turn it off only for an unattended sweep,
            where the tools queue their action instead of executing it.
    """
    middleware = [*specialist_middleware(), PolicyGateMiddleware()]
    if human_in_the_loop:
        middleware.append(approval_middleware())

    return create_agent(
        model,
        tools=DISPOSITION_TOOLS,
        system_prompt=PROMPT + "\n\n" + date_context(),
        middleware=middleware,
        state_schema=PolicyState,
    )
