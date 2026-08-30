---
name: narrative_reading
description: How to read case notes, disputes and prior cases - timing, subject and specificity tests, and how to tell a customer explaining their activity from a customer disowning it. Load before concluding on any account with free text.
---

# Reading the File

The database will tell you that an account made six transactions in forty
minutes from a foreign IP. It will not tell you that a colleague typed an
explanation two weeks ago. Finding that sentence, and judging whether it
actually covers the anomaly, is what separates a system that reads from one
that counts.

Grid-searching numeric rules over this queue tops out around 78% accuracy.
Reading the notes properly reaches about 92%. This document is about those
fourteen points.

## The three tests

An explanation only exonerates if it passes all three. Always state which ones
it passed, and which it failed.

### 1. Timing

Every record carries `timing` and `days_before_alert`. Positive means the
record predates the incident; negative means it came after.

- **Filed before the incident** - a pre-existing explanation. Someone recorded
  the reason before there was anything to excuse. This is the strongest kind of
  exculpatory evidence, because it cannot have been written to explain away a
  loss.
- **Filed after the incident** - the customer's reaction to it. Read the
  content carefully, because this cuts both ways. A customer saying *"I did not
  make these transactions"* is **corroborating fraud**, not explaining it. A
  customer calmly confirming a purchase is weaker than a note filed in advance,
  but still evidence.

The single most common error in this queue is treating any note as exculpatory
because a note exists. A note filed the day after a spree, reporting the spree,
is the opposite of an explanation.

### 2. Subject

Does the record explain *this* anomaly?

- A travel notice for the Netherlands does not explain transactions from the
  United Arab Emirates.
- A note about a spouse using a supplementary card does not explain a device
  registered at 03:41 followed by spending across four countries.
- A note about a planned jewellery purchase explains a large amount. It does
  not explain a new device.

Match the explanation to the specific thing the rule detected. If it covers
part of the anomaly and not the rest, say exactly which part.

### 3. Specificity

Compare:

> "Customer confirmed spend is expected."

against

> "Customer upgraded their phone on the 14th and could not log in. Walked them
> through re-registration. Verified with video KYC."

The second names a date, a mechanism and an identity check. The first could
have been written about anything. Both are notes; they are not the same
evidence, and confidence should reflect that.

Verification language matters. Phrases like *verified with video KYC*,
*identity verified in branch with passport*, *verified identity with OTP and
last four digits* mean a human checked who they were talking to. That is
materially stronger than an unverified inbound claim.

## Two families of note

Notes on this desk broadly do one of two things, and the difference usually is
the case.

### The customer explains

Recurring shapes worth recognising, and what each one covers:

| The note says | It explains | It does NOT explain |
|---|---|---|
| Phone upgraded / handset lost, re-registered, identity verified | a newly registered device | spending in countries never used before |
| Travel notice, flying to a named country on a named date | foreign transactions **in that country, around that date** | a different country, or a different month |
| Son or daughter at university abroad uses the card | recurring foreign spend in that one country | a burst across several countries in minutes |
| Spouse holds a supplementary card, both handsets registered | a second device, and a second spending pattern | a device registered hours before a spree |
| Planned large purchase - jewellery for a wedding, a laptop | a single large amount, near that date | velocity, or high-risk merchant categories |
| Business settles supplier invoices at month end | lumpy volume and value | night-time activity from new devices |
| Seasonal or festival spending, consistent with prior years | sustained elevated spend over weeks | a 40-minute burst |
| Joint household, shared family tablet, both identities verified | a **shared device** flagged by network analysis | anything about amounts |

### The customer disowns

These are corroboration of fraud, not explanations of it:

- Does not recognise several small amounts; card still in their possession.
  (Card-not-present compromise, and it fits card-testing patterns.)
- Received an SMS about a device registration they did not perform; has not
  travelled; still holds the card. (Account takeover, stated plainly.)
- Wallet stolen on a named date, card blocked at their request, police report
  filed. (Card theft. Check the transaction dates against the stated theft date.)
- Did not make any of these transactions and did not change their password.

### A third family: the mule pattern

Some notes are neither. A customer who was **evasive about the source of
incoming transfers**, or who says a friend asked them to receive money and
forward it on, is describing money-mule activity. That is not an explanation
and not a denial. Flag it as its own finding, and expect the network analysis
to matter more than usual.

## Disputes

A dispute is the customer's own words, but filing one is not proof of fraud.
Read `reason_code`:

| Code | Meaning | Weight |
|---|---|---|
| `10.4 unauthorised` | The customer denies making it | Fraud-leaning, strong |
| `13.1 goods not received` | The merchant did not deliver | A merchant problem, not a compromise |
| `13.7 cancelled` | A cancelled order or subscription | Usually benign |

Check *which transactions* the dispute covers. A dispute filed against the
incident's own transactions is far stronger than an unrelated one from two
months earlier.

## Prior cases

Outcomes are `confirmed_fraud`, `false_positive` and `insufficient_evidence`.

Prior cases set a prior, and nothing more. A customer with three prior false
positives is behaving the way they always have, which makes a fourth false
positive more plausible. A customer with a confirmed compromise last year
deserves less benefit of the doubt. Neither decides the case in front of you,
and neither is a substitute for evidence about this incident.

## When the file is silent

Some accounts have no case notes at all, and some have notes that say nothing
about the incident. Say so plainly. Do not stretch an unrelated record to fit
the shape of the anomaly - a note about festival shopping does not become a
travel notice because you need one.

An honest `silent` finding is what allows the disposition officer to reach
`insufficient_evidence` correctly, and that verdict scores. A stretched
explanation produces a confident wrong answer, which does not.
