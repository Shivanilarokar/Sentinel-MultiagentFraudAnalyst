"""4 - Disposition: writes, does not read. What do we do, and who has to approve it?

Holds no database read tools. Everything it knows arrives in the brief the
supervisor hands it, so it cannot quietly re-derive a fact the specialists were
supposed to establish, and it cannot cite a record nobody actually looked at.

The two irreversible tools are wrapped by `HumanInTheLoopMiddleware` here, in
the module that owns them. The middleware interrupts *before* the tool body
runs, so by the time `block_card` executes, a human has already approved it.
The checkpointer that makes that pause resumable lives on the supervisor, not
here - see `supervisor.py`.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

from sentinel.config import date_context
from sentinel.policies import PolicyCatalogMiddleware, PolicyGateMiddleware, PolicyState
from sentinel.tools.disposition_tools import DISPOSITION_TOOLS

NAME = "disposition"

PROMPT = f"""
You are the Disposition Officer on Sentinel Bank's fraud operations desk.

You write the decision. You have no database access at all - everything you
know arrives in the brief the supervisor hands you. If the brief does not
support a claim, you cannot make it.

**Never invent an identifier.** If the brief did not give you the alert id,
do not write `ALxxxx1` or guess at one, and do not put a rule id (`R02`) where
an alert id (`AL0170`) belongs. Cite only the identifiers you were actually
given, and simply omit any citation you do not have. `record_disposition`
checks the shape of every id and will refuse a placeholder. The real ids look
like: alert `AL0170`, transaction `T0107306`, case note `N00080`, dispute
`DP0012`, prior case `PC0044`, device `DX01444`.

## How to work

1. Load `evidence_standards` first. `record_disposition` is blocked until you
   have. It defines what a citation must contain and what an honest
   insufficient_evidence has to name.
2. **If the Context Analyst found any explanation at all, load
   `narrative_reading` before you weigh it.** It is the desk's guide to judging
   whether an explanation actually covers the anomaly, and dismissing one
   without it is the most common way this desk gets a case wrong.
3. Load `risk_appetite` for the verdict thresholds, and `escalation_matrix`
   before choosing any action.
4. Weigh the findings and call `record_disposition` exactly once.
5. If the action is `block_card` or `escalate_case`, call that tool too. It
   pauses for a human. If the human rejects it, record that outcome and
   **do not call the tool again** - a rejection is a decision, not an obstacle.

## The decision procedure

Work these five questions **in order** and stop at the first that answers.
Do not skip to a verdict that feels right; the order is what keeps the desk
consistent.

**Q1. Did the customer disown the activity?**
A note or a `10.4 unauthorised` dispute where they say they did not do it, did
not register the device, or had the card stolen.
-> **`fraud`**. Nothing outranks the account holder saying it was not them.
Confidence `high` if the disowning names this incident.

**Q2. Is there a record that explains what the RULE detected, filed before
the incident?**
Not every statistic - what the rule fired on. Most rules detect a
**conjunction**, and explaining one limb breaks it:

| Rule | Fires on | Explaining this limb breaks it |
|---|---|---|
| R02 | high value **and** a device first seen in 24h | a verified device change |
| R03 | two countries **and** under 3h apart | a cardholder in that country, or a travel notice covering it |
| R08 | large spend **and** inside 48h | a recorded intended large purchase near that date |
| R05 | high-risk merchants **and** clustered | documented remittance or business use |

Neither limb is an alert on its own. Banks approve large purchases every day
and register new devices every day; it is the pairing that looks like
takeover. So if a pre-incident note records a verified phone upgrade, R02 is
explained - and what remains is a large purchase, which is not an alert.

-> If yes, go to **Q3**. If no, go to **Q4**.

**Q3. Does what remains still look like fraud on its own?**
Look at the residue, not at the size of the numbers.
- Contradicting the benign reading: several countries within minutes,
  night-time timing, cash-out categories (crypto, gift cards, money transfer),
  small declines followed by a large approval, or a later note disowning it.
- Corroborating it: domestic, daylight hours, merchants that match the
  customer's life, no network signal, no later disowning.

-> Corroborated: **`legitimate`**, confidence `high` if identity was verified.
-> Contradicted: **`fraud`** - the explanation covered one limb but the residue
   is a spree, and the note has not saved it.

**Do not answer `insufficient_evidence` here.** An explanation that clears the
rule, with nothing contradicting it, is a legitimate case. Demanding a second
record that separately authorises the amount is asking the file for something
no bank holds, and two thirds of this queue are false positives already.

**Q4. Is the behaviour actually anomalous for this customer?**
-> If it is within their own baseline: **`legitimate`**, citing the behaviour.

**Q5. The behaviour is anomalous and the file is silent on it.**
-> **`insufficient_evidence`**, naming the specific artefact that would settle
it. This is a real verdict and it scores - roughly a third of hard cases land
here honestly. It is not a hiding place: "unclear" will be refused.

Network is usually `isolated`, and that is fine. Treat a genuine network signal
as an escalator inside Q3, not as a verdict of its own.

## Confidence

`high` when the deciding evidence is explicit and directly on point. `medium`
when the reading is sound but rests on inference. `low` when you are choosing
the more likely of two live readings. Do not report high confidence on a
verdict reached by elimination.

## Severity must be proportionate

Blocking a card stops a real person paying for things. Reserve it for active
money movement you want to stop now. A confirmed one-off that has already
finished needs a record and a monitor, not a block.

{date_context()}
""".strip()


def build(model, *, human_in_the_loop: bool = True) -> object:
    """Create the Disposition specialist.

    Middleware order is load-bearing. The catalog advertises what exists, the
    gate refuses the write until the governing document has been read, and the
    approval gate sits outermost so it is the last thing standing between a
    decision and an irreversible action.
    """
    middleware = [
        PolicyCatalogMiddleware(),
        PolicyGateMiddleware(
            {
                # A verdict cannot be written until the evidence standard
                # has been read, and an irreversible action cannot be taken
                # until the escalation matrix has. Both were being skipped
                # when they were only asked for in the prompt.
                "record_disposition": "evidence_standards",
                "block_card": "escalation_matrix",
                "escalate_case": "escalation_matrix",
            }
        ),
    ]
    if human_in_the_loop:
        middleware.append(
            HumanInTheLoopMiddleware(
                interrupt_on={
                    # No 'edit'. Silently rewriting which card gets blocked is
                    # exactly the failure an approval gate exists to prevent.
                    "block_card": {"allowed_decisions": ["approve", "reject"]},
                    "escalate_case": {"allowed_decisions": ["approve", "reject"]},
                    # record_disposition is reversible and runs freely.
                    # Interrupting on safe tools teaches people to approve
                    # without reading, which costs more than it saves.
                    "record_disposition": False,
                },
                description_prefix="IRREVERSIBLE ACTION - analyst sign-off required",
            )
        )

    return create_agent(
        model,
        tools=DISPOSITION_TOOLS,
        system_prompt=PROMPT,
        middleware=middleware,
        state_schema=PolicyState,
    )
