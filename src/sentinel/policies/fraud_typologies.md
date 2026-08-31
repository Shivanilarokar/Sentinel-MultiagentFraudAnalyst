---
name: fraud_typologies
description: The desk's current fraud typologies - the signature of each, what a false positive of it looks like, and which evidence actually decides between them. Load when a behavioural pattern is not obviously benign or obviously bad.
---

# Fraud Typologies

Eight rules fired on this queue. **None of them is reliable.** Measured true
positive rates:

| Rule | What it detects | Fired | True positive |
|---|---|---:|---:|
| R01 | More than 6 authorisations on one card within 60 minutes | 66 | 59% |
| R07 | Transaction above 40,000 between 01:00 and 05:00 | 37 | 59% |
| R08 | Cumulative spend crosses 90% of credit limit within 48 hours | 47 | 51% |
| R04 | Five or more authorisations under 100 within 30 minutes | 49 | 45% |
| R05 | Three or more crypto, gift card or money transfer txns in 24 hours | 41 | 44% |
| R03 | Two authorisations from different countries less than 3 hours apart | 83 | 24% |
| R02 | Transaction above 25,000 from a device first seen in the last 24 hours | 88 | 23% |

The two rules that fire most are the two least reliable. **Which rule fired
tells you what to investigate, never what to conclude.**

Each typology below is written the same way: the signature, what a false
positive of that signature looks like, and the evidence that separates them.

---

## 1. Account takeover

**Signature.** A device registered within hours of the spend, followed
immediately by high-value transactions. Often at night, often across countries
the account has never used, often at merchants outside the customer's history.

**What a false positive looks like.** Identical. Someone who upgraded their
phone, re-registered the app, and then bought something expensive produces the
same device age, the same amount, the same rule.

**What decides it.**
- A case note recording a device change, **filed before the incident**, ideally
  with identity verification (video KYC, branch passport check, OTP).
- Whether the spend stayed in the home country and in daylight hours. A phone
  upgrade does not usually come with four countries in thirty minutes.
- Whether the merchants match the customer's history or are cash-out
  categories.
- A note **after** the incident reporting an unrequested device registration
  SMS turns this from ambiguous to confirmed.

**Rules that fire:** R02, R07.

---

## 2. Card testing

**Signature.** Several small authorisations in quick succession, frequently
declined, then a larger approved one. Card-not-present. Often at gaming, gift
card or ecommerce merchants.

**What a false positive looks like.** Genuine small repeat purchases - transit
top-ups, in-app purchases, a customer retrying a failing payment.

**What decides it.**
- The **decline pattern**. Testing produces declines; a customer retrying their
  own card usually produces one or two, not five.
- Whether a larger transaction follows the small ones. That escalation is the
  point of testing.
- A note where the customer reports small amounts they do not recognise while
  still holding the card. That is this typology, confirmed.

**Rules that fire:** R04, sometimes R01.

---

## 3. Spree after compromise

**Signature.** Six or more transactions inside an hour, values far above the
customer's baseline, frequently across multiple countries, frequently at night.

**What a false positive looks like.** A family holiday, a festival shopping
day, or a business settling several supplier invoices in one session.

**What decides it.**
- **Geographic coherence.** A holiday happens in one or two countries. Five
  countries in thirty minutes is not travel, it is a card being used
  simultaneously in several places.
- Whether the countries appear in `first_seen` history or are new.
- A travel notice **naming the country and a date range that covers the spend**.
- Merchant mix. Restaurants and hotels look like travel. Crypto and gift cards
  do not.

**Rules that fire:** R01, R03, R05, R08.

---

## 4. Impossible travel

**Signature.** Two authorisations from different countries less than three
hours apart.

**What a false positive looks like.** This is the least reliable rule on the
desk at 24%. Legitimate causes are everywhere: a VPN, a supplementary card held
by a family member abroad, a child at university overseas, a subscription
billed from a foreign entity, or a customer genuinely in transit.

**What decides it.**
- A note explaining a second cardholder abroad - a son or daughter at
  university in a named country - which explains **recurring** spend in **that
  one country**, and nothing else.
- Whether the foreign country has months of `first_seen` history.
- Transaction size. Small, regular foreign amounts look like a subscription or
  a student. Large ones during a burst do not.
- Whether the pattern is two countries or five. Two can be explained. Five
  inside an hour cannot.

**Rules that fire:** R03.

---

## 5. Limit exhaustion

**Signature.** Cumulative spend driving toward or past the credit limit inside
48 hours.

**What a false positive looks like.** A planned large purchase. Jewellery for a
wedding, a laptop for a child's course, a home appliance. Affluent and business
customers legitimately move large amounts.

**What decides it.**
- A note recording an intended large purchase, near the date, ideally with the
  approximate value.
- Customer **segment**. For an affluent or business customer a large amount is
  ordinary; for a student it is not.
- Whether the spend is one large transaction or a rapid series. A wedding
  purchase is usually one or two payments to a jeweller.
- Merchant category. Jewellery and electronics fit the benign story. Gift cards
  and money transfer do not.

**Rules that fire:** R08, often alongside R01.

---

## 6. Money mule

**Signature.** Incoming funds moved straight out through money transfer, crypto
or gift card merchants. Often on an account sharing a device with other
accounts. Often a recently opened account.

**What a false positive looks like.** A genuine remittance user, or a business
account with lumpy month-end flows and documented sources.

**What decides it.**
- A note where the customer was **evasive about the source of incoming
  transfers**, or says a friend asked them to receive money and forward it on.
  That is this typology stated in the customer's own words.
- Device sharing with accounts that carry confirmed fraud, where the sharing
  **began shortly before** the incident.
- Merchant `lift` above the base rate, not merely a shared merchant.

**Rules that fire:** R05, sometimes R01 and R08. Often the network evidence
matters more than any single rule.

---

## 7. Card theft

**Signature.** Card-present transactions in a burst, in the home country,
starting at a point in time and stopping.

**What a false positive looks like.** Ordinary in-person spending.

**What decides it.**
- A note reporting a **wallet or card stolen on a named date**, usually with a
  police report reference. Compare the stated date against the transaction
  timestamps: spending after the theft is fraud, spending before it is the
  customer's own.
- Whether the card was blocked at the customer's request, and when.

**Rules that fire:** R01, R04, R08.

---

## Shared devices: the standing warning

Sixteen devices in this book are used by more than one customer. Some are mule
rings. **Some are married couples with a family tablet**, and there are notes on
file saying exactly that, with both identities verified in branch.

Sharing a device is a signal, not an answer. The two fields that decide it are
how long the sharing predates the incident, and whether the other party has any
fraud history of their own.
