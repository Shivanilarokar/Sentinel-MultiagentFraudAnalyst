---
name: evidence_standards
description: What a citation must contain, what makes a disposition defensible, and what an honest insufficient_evidence has to name. Load before recording any verdict - record_disposition is blocked until you have.
---

# Evidence Standards

A disposition is read by someone who cannot see your tools. Everything that
makes it convincing has to be inside the text you write.

## HARD RULES: enforced in code, `record_disposition` will refuse

These are checked by `sentinel/policy.py`, not by judgement. Comply in advance
rather than discovering the refusal.

1. **Every `fraud` or `legitimate` verdict must cite at least one record.**
2. **A `legitimate` verdict must cite a `case_note`, `dispute` or `prior_case`.**
   Calling something legitimate asserts that a human explained it. If no such
   record exists, the honest verdict is `insufficient_evidence`.
3. **Any citation of a note, dispute or prior case must carry a verbatim quote.**
   Copy the words. The evidence audit re-reads the row and checks they are there.
4. **`insufficient_evidence` must populate `information_required`** with the
   specific artefacts that would settle the case.
5. **Reasoning must be at least 120 characters.**
6. **The action must be permitted for the verdict.** You cannot block a card on
   an account you have called legitimate.

## What a citation looks like

Every `EvidenceRef` carries a `kind`, a real `ref_id`, and for human-written
records the `quote`.

| kind | ref_id looks like | quote required |
|---|---|:-:|
| `case_note` | `N00080` | yes |
| `dispute` | `DP0012` | yes |
| `prior_case` | `PC0044` | yes |
| `transaction` | `T0107306` | no |
| `alert` | `AL0170` | no |
| `device` | `DX01444` | no |

**Never invent an identifier.** If it did not come back in a specialist
finding, it does not exist. A fabricated note id is worse than no citation,
because it looks like evidence and is not.

## What makes reasoning defensible

A good disposition answers four questions in order:

1. **What fired, and what was it looking for?** Name the rule and what it
   detects, not just its id.
2. **What did the behaviour actually show?** Concrete numbers, from the
   findings you were given. Amounts, counts, times, countries, device age.
3. **What did the file say?** The quote, its note id, its date, and whether it
   was written before or after the incident.
4. **Which of those decided it, and why?** This is the sentence that carries
   the disposition. Make it explicit.

### A defensible disposition

> R02 fired on a transaction of 66,340 from device DX01444, which was six hours
> old at the incident (AL0170, T0107306). Four transactions totalling 216,091
> ran between 12:46 and 15:46, against a baseline average of 167. All were
> domestic, in daylight hours, at grocery, ecommerce, utilities and travel
> merchants. Case note N00080, filed five hours before the alert, records:
> "Customer upgraded their phone on the 14th and could not log in. Walked them
> through re-registration. Verified with video KYC." The note predates the
> incident, explains the exact anomaly the rule detected, and identity was
> independently verified. Verdict: legitimate.

Every number resolves to a row. The quote is verbatim. The deciding evidence is
named. Someone can check it.

### An indefensible one

> Multiple high-value transactions from a new device triggered our rules.
> Customer has previously contacted support. Verdict: legitimate.

No identifiers, no quote, no dates. "Previously contacted support" could be any
note about anything. This is a guess wearing the clothes of an argument.

## Judge an explanation against what the rule detected

The most common way a disposition on this desk goes wrong is by dismissing a
perfectly good explanation for not explaining enough.

Each rule detects one specific thing. R02 detects *a high-value transaction
from a device first seen in the last 24 hours*. A note filed before the
incident recording a verified phone upgrade explains **exactly that**. It does
not need to also account for the total spend, the transaction count or the
merchant mix — no real case note ever would.

Ask two questions in this order:

1. **Does the record explain what the rule fired on?** If not, it is not an
   explanation of this alert, however relevant it looks.
2. **Do the surrounding facts corroborate or contradict the benign reading?**

### Most rules detect a conjunction. Explaining one limb breaks it.

R02 does not fire on a high-value transaction. It fires on a high-value
transaction **from a device first seen in the last 24 hours**. Neither limb is
an alert on its own: the bank approves large purchases every day, and new
devices are registered every day. It is the pairing that looks like takeover.

So when a verified note explains the new device, the pairing is gone. What
remains is a large purchase from a customer whose identity was confirmed on
video — and a large purchase is not an alert. The correct verdict is
`legitimate`, not `insufficient_evidence`, and demanding a second note that
separately authorises the amount is asking the file for something no bank
holds.

The same logic applies across the board:

| Rule | The conjunction | Explaining this limb breaks it |
|---|---|---|
| R02 | high value **and** new device | a verified device change |
| R03 | two countries **and** under 3 hours apart | a second cardholder in one of those countries, or a travel notice covering it |
| R08 | large cumulative spend **and** inside 48h | a recorded intended large purchase near that date |
| R05 | high-risk merchants **and** clustered | documented remittance or business use |

**It does not apply when the remaining limb is itself the fraud signature.**
If the device is explained but the spend ran across five countries at 04:00
into crypto merchants, the residue is not "a large purchase" — it is a spree,
and the explanation has not saved it. Judge what is actually left.

Corroborating, on a claimed device change: the spend stayed in the home
country, ran in daylight hours, went to merchants consistent with the
customer's life, and no later note disowns it.

Contradicting: several countries within minutes, night-time timing, cash-out
merchant categories, declines followed by a large approval, or a note filed
afterwards reporting a device registration the customer did not perform.

If question 1 is yes and nothing in question 2 contradicts it, the verdict is
`legitimate`. Escalating to `fraud` because a note did not enumerate every
statistic is not rigour, it is a false positive with extra steps — and two
thirds of this queue are false positives already.

## Do not misread the arithmetic

Compare like with like. A burst total is not comparable to a per-transaction
average. If the baseline average is 167 across 75 transactions and the incident
is five transactions totalling 216,000, the defensible comparisons are:

- largest single transaction (66,340) against the baseline **maximum** (1,405)
- incident count and total against a **typical day**, not a per-transaction mean

Dividing a five-transaction total by a one-transaction average and reporting
"1,000 times baseline" overstates the anomaly by an order of magnitude. Any
number in a disposition must be one a reviewer can reproduce.

## Insufficient evidence, done honestly

Roughly 30% of the hard cases in this queue cannot be resolved from what is on
file. `insufficient_evidence` is a real verdict and it scores. It is also the
easiest thing in this job to abuse.

**It is the right answer when:** the behaviour is genuinely anomalous, and the
file is either silent or says nothing that bears on this incident.

**It is the wrong answer when:** you have an explanation that passes the three
tests and are hedging anyway, or when the customer has disowned the activity
and you are reluctant to call it.

`information_required` must name the artefact, not the feeling.

| Acceptable | Refused |
|---|---|
| "A case note explaining the device DX01444 registered on 27 Feb." | "More information." |
| "Customer confirmation of whether they travelled to MY between 26 and 28 Feb." | "Unclear." |
| "Whether the second handset belongs to a family member; no note covers it." | "Needs review." |
| "The outcome of dispute DP0031, still open, on the disputed transactions." | "Ambiguous case." |

Write each entry so an analyst could act on it tomorrow morning.

## On confidence

Confidence describes the strength of the evidence, not how you feel.

- **high** - the deciding evidence is explicit and directly on point. A note
  that names the anomaly, dated before it, with verification recorded.
- **medium** - the reading is sound but rests on inference. A note that covers
  the general situation without naming the specific anomaly.
- **low** - you are choosing the more likely of two live readings.

Do not report high confidence on a verdict reached by elimination. "Nothing
explains it" is not the same strength of evidence as "the customer said so".
