"""The state every agent in this system carries.

Kept in its own module because three different middlewares and four agents all
need to agree on its shape, and a circular import between them would be the
alternative.
"""

from __future__ import annotations

from typing import Annotated, NotRequired

from langchain.agents.middleware import AgentState


def merge_unique(a: list[str] | None, b: list[str] | None) -> list[str]:
    """Union of two lists, order preserved, duplicates dropped."""
    return list(dict.fromkeys((a or []) + (b or [])))


def merge_dict(a: dict | None, b: dict | None) -> dict:
    """Later keys win. Used to accumulate one finding per specialist."""
    return {**(a or {}), **(b or {})}


class PolicyState(AgentState):
    """What a specialist carries: which policies it has read, and its case.

    `account_id` rides along so every ledger row can be attributed to the case it
    belongs to, which is what makes the policy-load ledger auditable afterwards.
    """

    policies_loaded: NotRequired[Annotated[list[str], merge_unique]]
    account_id: NotRequired[str]

    # True during a queue sweep, where there is nobody to ask for approval. The
    # irreversible tools read this and QUEUE their action instead of executing
    # it. An unattended run that could block 276 cards is a worse system than
    # one that cannot.
    unattended: NotRequired[bool]


class SupervisorState(PolicyState):
    """What the supervisor carries between turns.

    `findings` is the interesting field. Each specialist's full finding is stored
    on a **state key**, never in the message list, so the supervisor's model
    never re-reads it on later turns — but the report writer and the evidence
    audit can pull it out afterwards. Context isolation for the model, full
    detail for the record.

    `specialists_consulted` is what makes ordering enforceable rather than merely
    requested: the disposition wrapper reads it and refuses if context is missing.
    """

    specialists_consulted: NotRequired[Annotated[list[str], merge_unique]]
    findings: NotRequired[Annotated[dict, merge_dict]]
