# Three worked cases

Each one shows what every specialist found, in full, and how the supervisor weighed them. The findings are reproduced verbatim from the `findings` table — this is exactly what crossed the isolation boundary.

---

## An obvious fraud — `A00008`

**Verdict:** `fraud` (high confidence)

### What fired

| alert | rule | fired | severity |
|---|---|---|---|
| `AL0117` | R02 New device high value | 2026-02-28T01:21:10 | high |
| `AL0118` | R01 Velocity spike | 2026-02-28T01:21:10 | high |
| `AL0119` | R03 Impossible travel | 2026-02-28T01:21:10 | high |
| `AL0120` | R07 Night time high value | 2026-02-28T01:21:10 | high |

### The network specialist reported

```
Account A00008 uses 3 devices, all exclusively owned by them with no sharing recorded. There is no link to other flagged accounts via devices.

However, during the incident, the account made transactions at 3 merchants also used by other flagged accounts over the weekend:
- Crypto exchange 946 (risk 0.62), shared with 9 other flagged accounts.
- Gift cards 946 (risk 0.78), shared with 8 other flagged accounts.
- Electronics 399 (risk 0.25), shared with 8 other flagged accounts.

While device sharing is absent, merchant overlap with multiple flagged accounts at higher-risk categories like crypto and gift cards suggests some connection to broader suspicious activity. The account is not acting entirely alone given this merchant pattern, though no evidence of device-level collusion or mule rings is found.
```

### The context specialist reported

```
The behaviour analyst found suspicious activity on account A00008 related to an unexpected device registration, which the customer did not perform. The case note (id: N00051) is labeled "after_incident" and states verbatim: "Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card."

Applying the policy tests:

- Timing: The note is "after_incident," meaning the customer is reacting to the alert, so it is not a pre-existing explanation.
- Subject: The note directly addresses the device registration flagged by the analyst.
- Specificity: The note is specific and clear, stating that the customer did not perform the device registration, has not travelled, and still holds the physical card.

Therefore, the customer did not explain or accept the flagged activity; instead, they disowned it, which corroborates fraud rather than explains it.

No disputes were filed by the customer for this account. There are no prior investigations on record.

In summary: The behaviour analyst flagged a device registration the customer did not perform. The customer called in after the incident and said: "They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card." (note id N00051) This note disowns, rather than explains, the flagged activity.
```

### The behaviour specialist reported

```
The account A00008 triggered 4 high-severity alerts:

1. AL0117 (R02 New device high value): Fired on a transaction (T0107083) of 34,274 on 2026-02-28 at 01:39:10 from a device first seen a few minutes before (mobile iOS 17 device DX01439 first seen 2026-02-28T01:21:10).
   - This rule triggers on transactions above 25,000 from a device new within 24 hours.

2. AL0118 (R01 Velocity spike): Fires when more than 6 authorisations occur in 60 minutes.
   - Incident window shows 3 transactions, 2 approved, none exceeding 6 in 60 minutes.

3. AL0119 (R03 Impossible travel): Two authorisations from different countries less than 3 hours apart.
   - Incident transactions from GB, DE, and AE within minutes.

4. AL0120 (R07 Night time high value): Transaction above 40,000 between 01:00 and 05:00 local.
   - Incident has one approved transaction of 64,508 at 01:30.

Spending baseline for this customer over prior 90 days:
- 103 transactions over 61 active days.
- Median amount: 77, mean: 282.
- Largest ever before incident: 4,951.
- Total spend 29,079.
- 1 device used consistently.
- Usual countries: 8, with AE (UAE) having only 1 transaction, biggest 26.
- Usual active hours: spread around daytime and evening but not early morning.

Incident activity details:
- 3 transactions within about 2 hours totaling 129,692 (much higher than normal).
- Devices: Only device used in incident is DX01439, brand new during incident (first seen at 01:21).
- Geography: Transactions from GB, DE, and AE (United Arab Emirates).
- All three countries were used before but with varying transaction counts: GB (2 prior, small amounts), DE (3 very small prior), AE (only 1 transaction, amount 26).
- Transaction categories include electronics (30,910 approved), gift cards (64,508 approved), crypto exchange (34,274 declined).
- High-risk categories (crypto and gift cards) used before but at much lower volumes (crypto 3 txns for 3,850 total, money transfer 2 txns for 1,393 total).

Summary:
- The transaction amounts during the incident are roughly 7-20 times larger than any previous transaction, exceeding the customer's largest prior transaction of 4,951 by a large margin.
- The device for these transactions is brand new and was first seen within minutes of the incident transactions.
- Geography usage includes countries seen before, but with little prior activity and very small amounts.
- The timing is unusual (night hours, 01:21-01:39) compared to the customer's usual transaction times.
- There is a velocity spike alert but the actual count of transactions in the incident window is 3 (below the 6 threshold that triggers the alert, may relate to other activity outside the incident window).
- The customer shows prior usage of high-risk merchants (crypto, gift cards) but at much smaller amounts.
- Overall, the pattern suggests a sudden high value, out-of-character spree on a brand new device at unusual hours and split across multiple countries used rarely or with very low amounts before.

Conclusion:
This spending behavior is abnormal and not normal for customer A00008 given their historical spending patterns, device usage, timing, geography, and transaction amounts. The high transaction amounts on a brand new device combined with the unusual timing and multiple countries in a short timeframe indicate a deviation from baseline behaviour.
```

### The disposition specialist reported

```
The verdict for account A00008 is fraud with high confidence. The deciding evidence is the customer's call disowning the new device registration, quoted verbatim from case note N00051: "Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card." This note directly contradicts any legitimate use of the new device tied to suspicious high-value transactions across multiple countries and unusual hours. The escalation has been made to the fraud investigations team to handle potential broader suspicious activity connected to this account.
```

### The disposition

The R02 rule detected a high-value transaction of 34,274 from device DX01439, which was new and first seen within minutes of the transaction (AL0117, T0107083). Multiple transactions totaling 129,692 occurred in a two-hour window, far exceeding historical maximums (largest prior 4,951). Transactions happened across GB, DE, and AE, rarely used countries by the customer, during unusual night hours. Case note N00051, filed after the incident, states: "Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card." This note explicitly disowns the device registration and correlates with the suspicious pattern. The customer's disowning of the new device and absence of travel explains the fraudulent nature of the activity. Therefore, the verdict is fraud with high confidence, decided by the customer call disowning the device registration (note N00051).

### Evidence cited

| kind | id | quoted words |
|---|---|---|
| alert | `AL0117` | — |
| transaction | `T0107083` | — |
| note | `N00051` | Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card. |

---

## A convincing false positive — `A00000`

**Verdict:** `legitimate` (high confidence)

### What fired

| alert | rule | fired | severity |
|---|---|---|---|
| `AL0201` | R03 Impossible travel | 2026-03-01T17:29:52 | medium |

### The network specialist reported

```
Account A00000 is not linked to any other flagged accounts by shared devices; in fact, this customer uses devices exclusively owned by them. There are no shared devices or device peers involved.

Regarding merchant overlap, this account transacted with 4 merchants also used by other flagged accounts over the weekend:
- Electronics 331 with 15 other flagged accounts
- Grocery 271 with 9 other flagged accounts
- Electronics 252 with 7 other flagged accounts
- Fuel 808 with 5 other flagged accounts

Despite this merchant overlap, shared devices and device peers are absent, which reduces the likelihood of organised fraud rings through device sharing. The merchant evidence alone does not conclusively link this account to other flagged accounts in an organised fraud network.

In conclusion, account A00000 is acting alone in terms of device usage and peers. The moderate merchant overlap alone is not definitive evidence of linkage to a ring.
```

### The context specialist reported

```
The customer under account A00000 provided one relevant explanation before the incident occurred, passing the timing test. The note with ID N00106 dated 2026-02-25, authored by T. Fernandes via chat, states:

"Customer explained the second device belongs to their son who is at university in SG and uses the card for living costs. Arrangement noted on file."

This note specifically covers a second device usage by the customer's son in Singapore, explaining recurring foreign spend in that country. It is specific and names the device user and country, so it also passes the subject and specificity tests for that portion of flagged activity.

There are no disputes filed on this account explaining or contradicting the flagged activity.

The customer's profile shows a long tenure (open since 2020-02-27) and full KYC level, with a high credit limit of 99,000. Prior investigations exist but are irrelevant to this specific flagged activity.

Summary: The customer has provided a prior, specific, and relevant explanation for part of the flagged suspicious activity—usage from a second device in Singapore by their son for living costs, as stated in case note N00106 filed before the incident.
```

### The behaviour specialist reported

```
The alert AL0201 R03 Impossible travel (medium severity) fired on account A00000 because there were two authorizations from different countries less than 3 hours apart. The trigger transaction was T0107395 at 2026-03-02 05:29:52 from country SG (Singapore) at Grocery 271 for amount 14,493.

Incident activity in the alert window (2026-03-01T15:29:52 to 2026-03-02T07:29:52):
- 4 transactions, all approved, total 61,426
- Transactions:
  - T0107392: 10,263 in electronics at SG on 2026-03-01 17:29:52
  - T0107393: 20,979 in electronics at SG on 2026-03-01 21:29:52
  - T0107394: 15,692 in fuel at SG on 2026-03-02 01:29:52
  - T0107395: 14,493 in grocery at SG on 2026-03-02 05:29:52
- All used same device DX01459
- All transactions from country SG during the incident

Baseline spending for the customer over the previous 90 days before incident:
- 21 transactions over 19 active days
- Median amount: 31
- Mean amount: 115
- Largest single transaction ever: 1,515
- Total spending: 2,406
- Countries used: 2 (IN and TH)
- Devices used: 1
- Usual transaction hours: mostly between 17:00 and 20:00, and once at 10:00
- Country presence: Mostly IN (India) with 18 transactions totaling 2,312, and TH (Thailand) with 3 transactions totaling 94

The presence of Singapore (SG) as transaction country is new for this account, with 4 transactions totaling 61,426 in just about 12 hours. This compares with much smaller and less frequent spend in the customer's usual two countries. The transaction amounts in the incident (all between 10,263 and 20,979) are massively higher than the customer's previous largest transaction of 1,515, and total spend in the incident window is about 25 times the entire 90-day total spend that preceded it.

Summary: The customer's recent activity shows a sudden and significant change in geography, spending amounts, and frequency compared to their past 90-day behavior. The alert of impossible travel is accurate in that there are transactions from countries previously unseen within a short time window. The magnitude and geography change strongly suggest this is not normal spending behavior for this customer.
```

### The disposition specialist reported

```
The verdict for account A00000 is legitimate with high confidence. Alert AL0201 R03 flagged impossible travel due to transactions from two countries less than 3 hours apart, highlighting unusual and high spending in Singapore. However, note N00106 dated 2026-02-25, authored by T. Fernandes, explicitly explains that the customer's son, who is studying in Singapore, uses the card for living costs, clarifying the foreign activity. This note predates the incident and directly accounts for the unusual geographic and spending pattern, overriding suspicion. Thus, the activity is explained and not fraudulent. The deciding evidence is the case note N00106 stating: "Customer explained the second device belongs to their son who is at university in SG and uses the card for living costs. Arrangement noted on file."
```

### The disposition

Alert AL0201 R03 Impossible travel fired due to two authorisations from different countries less than 3 hours apart, flagging sudden foreign spend in Singapore with 4 transactions totalling 61,426, much higher than the customer's previous max transaction of 1,515 and a new country usage. The file includes note N00106 dated 2026-02-25, authored by T. Fernandes, explaining the card use by the customer's son in Singapore: "Customer explained the second device belongs to their son who is at university in SG and uses the card for living costs. Arrangement noted on file." This note predated the incident and specifically explains the Singapore spend and second device usage, fully accounting for the anomaly. The merchant overlap and device exclusivity do not contradict this explanation. The note N00106 is the deciding evidence establishing legitimacy of this activity.

### Evidence cited

| kind | id | quoted words |
|---|---|---|
| note | `N00106` | Customer explained the second device belongs to their son who is at university in SG and uses the card for living costs. Arrangement noted on file. |
| alert | `AL0201` | — |
| transaction | `T0107395` | — |

---

## One that could not be resolved — `A00025`

**Verdict:** `insufficient_evidence` (high confidence)

### What fired

| alert | rule | fired | severity |
|---|---|---|---|
| `AL0063` | R08 Limit approach | 2026-03-01T09:01:55 | high |

### The network specialist reported

```
Account A00025 is not sharing any devices with other customers, indicating isolation from direct network connections by hardware. However, this account has overlapping merchant activity with flagged accounts at 8 merchants used in the incident. Significant overlaps are seen at electronics merchants 198 and 857, and several jewellery merchants (660, 883, 907, 874), as well as gift card merchant 841 and a transport merchant 131. The number of other flagged accounts transacting at these merchants range from 5 to 15. 

In summary, A00025 is acting alone in terms of device usage but shares merchant overlap with multiple other flagged accounts. This suggests no direct organised fraud ring connection via shared devices but some connection through merchant usage patterns with other flagged accounts this weekend.
```

### The behaviour specialist reported

```
The alert AL0063 "Limit approach" fired on account A00025 due to cumulative spend crossing 90% of credit limit within 48 hours. The trigger transaction was T0106931 at 2026-03-02T03:01:55 for 10,088 at an Electronics merchant.

Reviewing the incident activity on the account:
- There were 8 transactions totaling 49,045 over roughly 2 days.
- Transactions ranged from 32 to 10,088 in amount.
- Transaction channels included app, card_present, and ecom.
- The device used throughout the incident is D000250, a mobile Android device seen first in 2021, used in 63 transactions prior, showing a long-established device.
- Geographic activity during the incident included US (1 txn), IN (6 txns), and NL (1 txn). NL is new to this customer.
- Baseline over the prior 90 days showed:
  - 42 transactions in 34 active days, total spend 11,640, mean 277, median 51, largest ever 4,580.
  - Usually transacts in 5 countries including IN and US.
  - Uses a single device, same D000250.
  - Usual transaction times cluster around midday and early evening.
- The incident spend of 49,045 is significantly higher than the customer's 90-day total spend of 11,640, and the largest transaction during incident (10,088) is more than twice their previous largest transaction (4,580).
- The spike in cumulative spend triggering the limit approach is therefore unusual in terms of amount.
- The device consistency and partly consistent geography (mostly IN and US present historically) reduces concern but the appearance of a new country NL during the incident is notable.

Overall, the spending pattern during the incident is markedly above this customer's historical norms in terms of total and per-transaction amounts and includes a new geographic country. Device use is consistent with history. This suggests the spending is not normal for this customer.
```

### The context specialist reported

```
For account A00025 (customer Chen Reddy), there are no case notes at all that explain the flagged activity or the behaviour analyst's findings. Specifically, there are:

- No case notes written explaining or justifying the flagged behaviour.
- No disputes filed on the account.
- No prior investigations for this customer.

Because there are no explanations (no narrative notes filed before or after the incident) it means no exculpatory evidence passes the timing, subject, or specificity tests listed by the narrative_reading policy.

What would settle this case in this file is any one of the following:
- A note recorded before the incident explaining why the flagged transactions or behavior is expected (e.g., a travel notice covering the countries and dates of the transaction).
- A note recorded after the incident where the customer calmly confirms those transactions or activity, specifically naming them and verifying identity.
- A relevant dispute filed by the customer explicitly naming the flagged transactions and confirming they authorized them.
- Prior cases or notes that document a pattern of the customer regularly engaging in similar activity with verification.

Since none of those exist here, the file is silent on the explanation for the flagged activity. An honest and policy-consistent disposition would therefore be insufficient_evidence, explicitly noting that no prior or contemporaneous note explains the anomaly.
```

### The disposition specialist reported

```
The verdict for account A00025 is insufficient_evidence with high confidence. The decisive evidence is the alert AL0063 triggered by a high cumulative spend well above the customer's historical baseline, including transactions in a new country, combined with the complete absence of any explanatory case notes, disputes, or prior cases that would explain or confirm the flagged activity. This silence in the file leaves the behaviour suspicious but unproven as fraud, meeting the policy standards for an honest insufficient_evidence disposition. To resolve this definitively, a case note or customer communication in advance or contemporaneous to the incident explicitly confirming the transactions and new country use is required. No further action is taken now.
```

### The disposition

Alert AL0063 fired due to a cumulative spend crossing 90% of credit limit within 48 hours, triggered by a transaction of 10,088 at an Electronics merchant (T0106931). Behaviour data shows 8 transactions totaling 49,045 over 2 days, far above the customer's baseline of 11,640 in 90 days with usual maximum 4,580, plus new country usage (NL). The account used a long-established device D000250, so device is consistent, but the spend pattern is anomalous. The account file has no case notes, disputes, or prior cases explaining or confirming the flagged activity, failing timing, subject and specificity tests for exculpatory evidence (per narrative_reading). Network reports do not implicate device sharing but note merchant overlap with flagged accounts. Without any customer communication or notes explaining the anomaly, the file is silent. The deciding factor is the absence of any explanatory case note or dispute covering the flagged transactions or new country spend. This leaves the behaviour suspicious but unproven fraud. This meets the evidence_standards for insufficient_evidence, with a high confidence verdict due to explicit anomaly and no exculpation.

**What would resolve it:** A case note explaining the high-value transactions and new country spending recorded before the incident, or a customer note or dispute explicitly confirming these transactions.

### Evidence cited

| kind | id | quoted words |
|---|---|---|
| alert | `AL0063` | — |
| transaction | `T0106931` | — |

