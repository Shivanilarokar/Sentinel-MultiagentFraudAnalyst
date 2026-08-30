# Three worked cases

One obvious fraud, one convincing false positive, and one that could not be
resolved. Each is chosen from the recorded results by confidence and citation
depth, not hand-picked, and each shows exactly what the supervisor received
from every specialist.

Everything below is reproducible: run `sentinel case <id> --show-trail`.

---

## obvious fraud: `A00115`

**Verdict: `fraud`, confidence `high`, action `monitor`**

### What fired

| alert | rule | what the rule detects | severity | triggered |
|---|---|---|---|---|
| `AL0047` | R02 New device high value | Transaction above 25,000 from a device first seen in the last 24 hours. | high | 2026-03-01T04:06:29 |
| `AL0048` | R01 Velocity spike | More than 6 authorisations on one card within 60 minutes. | high | 2026-03-01T04:06:29 |
| `AL0049` | R03 Impossible travel | Two authorisations from different countries less than 3 hours apart. | high | 2026-03-01T04:06:29 |
| `AL0050` | R07 Night time high value | Transaction above 40,000 between 01:00 and 05:00 local. | high | 2026-03-01T04:06:29 |

Incident window: `2026-03-01T04:06:29` to `2026-03-01T04:51:29`.

### The transactions inside that window

| txn | time | amount | country | merchant | category | result |
|---|---|---:|---|---|---|---|
| `T0106861` | 2026-03-01T04:06:29 | 57,828.96 | US | Electronics 857 | electronics | approved |
| `T0106862` | 2026-03-01T04:15:29 | 52,733.49 | GB | Electronics 274 | electronics | approved |
| `T0106863` | 2026-03-01T04:24:29 | 53,192.12 | GB | Gift cards 508 | giftcard | approved |
| `T0106864` | 2026-03-01T04:33:29 | 87,243.30 | AE | Electronics 337 | electronics | approved |
| `T0106865` | 2026-03-01T04:42:29 | 65,010.36 | SG | Crypto exchange 266 | crypto | approved |
| `T0106866` | 2026-03-01T04:51:29 | 27,032.48 | US | Crypto exchange 230 | crypto | approved |

### What the file said

**`N00023`** - 2026-03-01T12:06:29, S. Iqbal (email), 0.3 days after the incident

> Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card.


### What each specialist reported back

#### Behaviour

*11,977 characters produced inside this specialist, 2,017 crossed back to the supervisor (83% discarded).*

```
Four alerts fired on account A00115 (AL0047, AL0048, AL0049, AL0050), indicating new device high value spend, velocity spike (more than 6 transactions in 60 minutes), impossible travel (different countries in under 3 hours), and high value night time transaction. The incident consisted of 6 transactions inside one hour, totaling approximately 343,041, with the largest transaction being 87,243.3. These 6 transactions happened over 4 countries and 1 device, with 6 transactions occurring at night (between 01:00 and 05:00). No declines were recorded.

Compared against the baseline excluding the 7 days prior, the customer normally has 48 transactions averaging 149.08 with a maximum of 2,325.79 and rarely transacts at night (night_txn_rate 0.021). The incident amounts are more than an order of magnitude above normal maximum single transactions and total spend in a short period. The incident occurred on a newly registered device (device age 0 hours), which is a strong signal of possible account takeover or device change. The geography shows multiple countries involved in the incident including US, GB, AE, SG - some of which appear first time during the incident window. This is consistent with the impossible travel alert. The incident features transactions in high-risk merchant categories of crypto and gift cards, normally associated with elevated fraud risk, while the baseline has negligible amounts in these categories.

Credit limit utilization is extreme: the customer’s credit limit is 201,000 but the incident spend over 48 hours is 343,838 (171.1% of limit), making this highly unusual spending.

Summary: The pattern of very high spend far above baseline, multiple countries seen for first time within the incident, very new device, high-risk merchant categories, high velocity in short time, night hours transactions, and credit limit breach is anomalous. No benign signals such as device tenure, familiar countries, or spending in normal categories offset these findings.

Verdict: anomalous.
```

#### Context

*3,547 characters produced inside this specialist, 1,054 crossed back to the supervisor (70% discarded).*

```
Customer profile for A00115: retail segment, simplified KYC, home country India.

Case notes: One note (N00023, 2026-03-01, after alert) states: "Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card." This fails the timing test (written after the incident), and it disowns the new device limb of the alert. It is specific to device registration but is not an explanation of the transactions or travel anomaly.

Disputes: One open dispute (DP0015, filed 2026-03-02) on a transaction flagged (T0106865, timestamp 2026-03-01) says: "I received no OTP for any of these. Somebody else has access to my account." This is after the incident and disowns the transactions, indicating fraud rather than providing explanation.

Prior cases: none on record for this customer.

Assessment: The customer denies and disowns the transactions and device registration but does not provide any pre-existing explanation for the anomalies. Therefore, the case is disowned.
```

#### Network

*2,717 characters produced inside this specialist, 615 crossed back to the supervisor (77% discarded).*

```
This account A00115 has no shared devices with any other customers, indicating device-wise isolation from other flagged accounts. Examination of merchant overlaps in high-risk cash-out categories such as crypto and gift cards shows only lifts between 0.7 and 1.15 for all merchants used, with readings stating "no more than popularity predicts." This means the merchant overlaps are consistent with normal customer behavior and do not indicate a connection to a fraud network.

Overall, account A00115 appears isolated, with no device sharing or high-risk merchant overlaps linking it to any other flagged accounts.
```

#### Disposition

*28,094 characters produced inside this specialist, 1,269 crossed back to the supervisor (95% discarded).*

```
Verdict: fraud with high confidence. Multiple fraud detection alerts triggered on this account, showing suspicious activity such as a high-value transaction on a newly registered device, velocity spikes, impossible travel across countries, and high-value night-time transactions far outside the customer's baseline behaviour. The customer explicitly disowned all transactions and the device registration in a case note (N00023) and a dispute (DP0015), stating the card was still physically with them and no OTP was received, which decisively indicates fraud. There is no legitimate explanation on file, and network analysis shows the account is isolated, consistent with an independent takeover.

Action: The account will be monitored and simultaneously escalated to investigations for further human review. The escalation has been queued for analyst approval and has not yet executed.

Evidence cited includes alerts AL0047, AL0048, AL0049, AL0050; case note N00023 verbatim quoting the customer's claim of no device registration; and dispute DP0015 quoting the customer denying OTP receipt and access.

No card block was applied at this stage since the incident appears historical rather than ongoing money movement, but further action may follow after investigation.
```

### How the supervisor weighed them

Four alerts fired on account A00115: AL0047 flagged a high-value transaction from a device registered within 24 hours, AL0048 detected a velocity spike, AL0049 observed impossible travel across multiple countries, and AL0050 identified a high-value night-time transaction. The incident involved six transactions totaling approximately 343,041 units across four countries at night, while the customer's usual maximum transaction is 2,325.79 with rare night activity and no prior device younger than the current one. The customer is retail segment with simplified KYC and domiciled in India. Crucially, the customer explicitly disowned this activity and device registration in case note N00023 and dispute DP0015, stating the card remains physically with them and no OTP was received, indicating fraud. No legitimate pre-existing explanation is on file. Network analysis shows isolation, supporting an independent fraudulent takeover. The customer denial decisively outweighs behavioural anomaly, resulting in a high confidence fraud verdict.

### Evidence cited

| kind | id | quote or detail |
|---|---|---|
| alert | `AL0047` |  |
| alert | `AL0048` |  |
| alert | `AL0049` |  |
| alert | `AL0050` |  |
| case_note | `N00023` | Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card. |
| dispute | `DP0015` | I received no OTP for any of these. Somebody else has access to my account. |

---

## convincing false positive: `A00271`

**Verdict: `legitimate`, confidence `high`, action `none`**

### What fired

| alert | rule | what the rule detects | severity | triggered |
|---|---|---|---|---|
| `AL0343` | R05 High risk merchant burst | Three or more transactions at crypto, gift card or money transfer merchants in 24 hours. | high | 2026-02-27T10:35:24 |
| `AL0344` | R08 Limit approach | Cumulative spend crosses 90 percent of credit limit within 48 hours. | high | 2026-02-27T10:35:24 |

Incident window: `2026-02-27T10:35:24` to `2026-02-27T22:35:24`.

### The transactions inside that window

| txn | time | amount | country | merchant | category | result |
|---|---|---:|---|---|---|---|
| `T0107810` | 2026-02-27T10:35:24 | 183,518.35 | IN | Money transfer 354 | moneytransfer | approved |
| `T0107811` | 2026-02-27T13:35:24 | 160,705.08 | IN | Money transfer 927 | moneytransfer | approved |
| `T0107812` | 2026-02-27T16:35:24 | 195,800.41 | IN | Money transfer 372 | moneytransfer | approved |
| `T0107813` | 2026-02-27T19:35:24 | 145,229.42 | IN | Money transfer 389 | moneytransfer | approved |
| `T0107814` | 2026-02-27T22:35:24 | 178,264.30 | IN | Money transfer 752 | moneytransfer | approved |

### What the file said

**`N00206`** - 2026-02-22T10:35:24, R. Menon (chat), 5.0 days before the incident

> Customer runs a small trading business and settles supplier invoices through the account at month end. Volumes are lumpy by design. Source of funds documented.


### What each specialist reported back

#### Behaviour

*8,527 characters produced inside this specialist, 1,667 crossed back to the supervisor (80% discarded).*

```
Two high-severity alerts fired on account A00271 for a high risk merchant burst (AL0343) and limit approach (AL0344) starting 2026-02-27 10:35, both triggered by a transaction at a money transfer merchant in India.

The incident on 2026-02-27 includes 5 approved transactions totaling INR 863,517.56, all at money transfer merchants in India using device D002710, over 12 hours. The largest single transaction was INR 195,800.41. No night transactions or declines occurred.

Comparing to baseline excluding the week before incident: the customer averages 139.82 per transaction with a max single txn of 2,111.07 from 136 prior transactions over ~3.5 months. Incident largest amount is ~93x higher, and total spend in 24h is 6,000x higher than average. Typical night txn rate is low (1.5%), and no night txns occurred in incident.

Device D002710 used for all transactions is old (over 26,500 hours, registered in Feb 2023) and used throughout the history for 149 txns in total, so device age does not explain risk.

Country India (IN) has been used consistently since account inception; no new geography is involved.

All incident transactions are at high-risk merchant categories (moneytransfer), a significant jump from baseline. Credit limit approach alert reflects very high utilisation in short period.

In summary, the incident shows a sudden burst of very high-value transactions exclusively at risky merchant categories, massively exceeding baseline amounts, but on a familiar device and country, and during daytime. The transaction velocity, amounts, merchant type, and limit utilization are anomalous for this customer's usual behavior.

Verdict: anomalous.
```

#### Context

*4,039 characters produced inside this specialist, 1,100 crossed back to the supervisor (73% discarded).*

```
Customer profile: business segment, full KYC level, home country India.

Case note N00206 dated 2026-02-22, five days before the incident, states: "Customer runs a small trading business and settles supplier invoices through the account at month end. Volumes are lumpy by design. Source of funds documented." This note explains the high volume and value of transactions, covering the high-value money transfer limb of the alert. It passes timing (before alert), subject (explains high transaction volume in the usual geography, India), and specificity (mentions lumpy volumes and documented source of funds).

There is a dispute DP0077 filed on 2026-03-01, after the alert, about one transaction on 2026-02-27 for a money transfer, reason "13.1 goods not received," which is a merchant issue, not denial or explanation of origin of transactions.

Prior case PC0133 closed 2025-07-10 was a false positive where customer confirmed all prior transactions were their own.

Assessment: explained. The customer's business nature and prior documentation sufficiently explain the anomalous transaction burst.
```

#### Network

*3,688 characters produced inside this specialist, 588 crossed back to the supervisor (84% discarded).*

```
Account A00271 is isolated in terms of device usage: none of its devices are shared with any other customer, ruling out a coordinated mule ring through device sharing. On the merchant dimension, all high-risk merchants this account used have a lift below 1.5, with readings stating "no more than popularity predicts." This means the merchant overlaps do not exceed the base fraud rate and provide no network signals of suspicious associations. 

In conclusion, account A00271 is acting alone and shows no network signals from shared devices or merchant overlaps. The finding is: isolated.
```

#### Disposition

*27,491 characters produced inside this specialist, 1,025 crossed back to the supervisor (96% discarded).*

```
The account triggered alerts AL0343 and AL0344 due to a burst of 5 high-value money transfer transactions in India on 2026-02-27, totaling INR 863,517.56, which was anomalous compared to the customer's usual amounts. The behaviour was anomalous but used a familiar old device and normal geography. Case note N00206, dated 2026-02-22, predating the incident, states: "Customer runs a small trading business and settles supplier invoices through the account at month end. Volumes are lumpy by design. Source of funds documented." This explains the high volume and value anomaly that triggered the alerts. The dispute DP0077 filed 2026-03-01 concerns goods not received and does not disown the transactions or legitimacy. Prior case PC0133 confirms customer ownership of transactions with no action needed. Network analysis shows the account isolated without suspicious links. The pre-existing verified business explanation and consistency with alert evidence lead to a high-confidence verdict of legitimate. No action is taken.
```

### How the supervisor weighed them

Alerts AL0343 and AL0344 fired on a burst of 5 high-value transactions in India on 2026-02-27, totaling INR 863,517.56 at high-risk merchants. These amounts are anomalous compared to the customer's baseline, but the transactions occurred using a familiar old device within the usual geography. Case note N00206, filed on 2026-02-22, states: "Customer runs a small trading business and settles supplier invoices through the account at month end. Volumes are lumpy by design. Source of funds documented." This note was made before the incident, explaining the high-volume anomaly consistent with the alert. A dispute DP0077 dated 2026-03-01 states: "I did make this purchase but the goods never arrived, so I want to raise a chargeback with the merchant," unrelated to ownership or legitimacy of the transactions underlying the alert. A prior false positive case PC0133 says: "Customer confirmed all transactions were their own. Alert closed with no action." The network analysis shows this account is isolated, with no suspicious links. The pre-existing verified business explanation in N00206, aligned with the alert characteristics and no contradictory evidence, leads to a verdict of legitimate with high confidence.

### Evidence cited

| kind | id | quote or detail |
|---|---|---|
| alert | `AL0343` |  |
| alert | `AL0344` |  |
| case_note | `N00206` | Customer runs a small trading business and settles supplier invoices through the account at month end. Volumes are lumpy by design. Source of funds documented. |
| dispute | `DP0077` | I did make this purchase but the goods never arrived, so I want to raise a chargeback with the merchant. |
| prior_case | `PC0133` | Customer confirmed all transactions were their own. Alert closed with no action. |

---

## could not be resolved: `A00152`

**Verdict: `insufficient_evidence`, confidence `high`, action `monitor`**

### What fired

| alert | rule | what the rule detects | severity | triggered |
|---|---|---|---|---|
| `AL0345` | R03 Impossible travel | Two authorisations from different countries less than 3 hours apart. | medium | 2026-02-28T20:59:38 |

Incident window: `2026-02-28T20:59:38` to `2026-03-01T04:59:38`.

### The transactions inside that window

| txn | time | amount | country | merchant | category | result |
|---|---|---:|---|---|---|---|
| `T0107815` | 2026-02-28T20:59:38 | 20,652.58 | GB | Grocery 200 | grocery | approved |
| `T0107816` | 2026-03-01T00:59:38 | 39,005.99 | GB | Fuel 979 | fuel | approved |
| `T0107817` | 2026-03-01T04:59:38 | 33,951.40 | GB | Jewellery 660 | jewellery | approved |

### What the file said

**`N00207`** - 2026-02-20T20:59:38, T. Fernandes (chat), 8.0 days before the incident

> Customer explained the second device belongs to their son who is at university in GB and uses the card for living costs. Arrangement noted on file.


### What each specialist reported back

#### Behaviour

*6,903 characters produced inside this specialist, 1,424 crossed back to the supervisor (79% discarded).*

```
One alert fired: AL0345 under rule R03 "Impossible travel", triggered by two authorisations less than 3 hours apart from different countries.

Incident (2026-02-28 20:59 to 2026-03-01 04:59) shows 3 transactions totaling 93,610 with largest single 39,006, all from 1 country (GB). Incident transactions recently appeared from GB for the first time on 2026-02-28. Before this, activity was mostly from IN and several other countries, but not GB. Only one device (DX01490) used in incident, device age 720 hours (~1 month), younger than existing device D001520 (over 2 years old).

Baseline excludes last 7 days, shows 62 transactions averaging 337 with max 7,721, in multiple countries except GB, on mostly older device D001520. No night transactions historically, but incident includes 1 night tx. Credit limit 203,000 with 46% used in 48h span including incident.

Magnitude of incident transactions is roughly 28x baseline max amount; total and velocity are dramatically elevated. New country IP seen first time in incident period. Device age moderate but newer than baseline device, consistent with device change less than two months prior.

In summary: spending amount and velocity far exceed baseline, at night, and from a new country IP appearing first time. Device is not brand new but much younger than baseline device. This spending appears anomalous given the magnitude and geography change.

Assessment: anomalous
```

#### Context

*2,879 characters produced inside this specialist, 1,018 crossed back to the supervisor (65% discarded).*

```
Segment: retail, KYC level: full, home country: IN.

Case note N00207, dated 2026-02-20, 8 days before the alert, states: "Customer explained the second device belongs to their son who is at university in GB and uses the card for living costs. Arrangement noted on file." This note passes the timing test (before the incident), clearly explains the new device limb of the alert, and is specific in identifying the person (son) and reason (university living costs). It thus covers the new device and country anomaly (GB) limb.

There are no disputes filed by the customer on this account, so no direct customer words disowning or explaining transactions.

There are no prior investigations or case outcomes on record.

Assessment: partially-explained. The new device and IP in GB limb of the alert is explained by this verified note about the son’s use at university. The sudden high spending and velocity, especially the impulse of large transactions up to 39,006, is not explicitly explained in the notes or disputes.
```

#### Network

*2,339 characters produced inside this specialist, 598 crossed back to the supervisor (74% discarded).*

```
Account A00152 does not share any devices with other customers, indicating it is isolated on the device dimension. Regarding merchant overlap, this account uses several merchants in gaming and money transfer categories, but all have lift values around or below 1.24, with the reading stating "no more than popularity predicts." This means the merchant overlap does not exceed expectations and does not indicate linked fraud activity.

In conclusion, account A00152 shows no evidence of device sharing with fraud-flagged accounts nor suspicious merchant overlap. The account is assessed as isolated.
```

#### Disposition

*22,858 characters produced inside this specialist, 793 crossed back to the supervisor (97% discarded).*

```
The disposition for account A00152 is insufficient_evidence with high confidence. Rule R03 "Impossible travel" fired due to transactions in two countries (GB, IN) within 3 hours, using a new device DX01490 for GB. The case note N00207 from before the incident explains the new device and new geography, as it belongs to the customer's son in GB, passing timing, subject, and specificity tests. However, there is no explanation for the sudden high spending amount, velocity, or night transactions, which remain anomalous. The network analysis found the account isolated. Thus, part of the alert is explained, but the central concern—the large rapid transactions—lacks justification on file. Monitoring is appropriate while seeking a case note or customer communication explaining this spending.
```

### How the supervisor weighed them

Rule R03 'Impossible travel' fired on two transactions less than 3 hours apart from different countries (GB and IN) for account A00152 (AL0345). The behaviour shows three transactions totaling 93,610 with a largest single of 39,006 from a new country GB and a new device DX01490 about one month old used in the incident, contrasting with baseline device over 2 years old, and historical maximum transaction 7,721 with no night transactions. Case note N00207 from 2026-02-20, filed before the incident, explains the new device and geography limb: 'Customer explained the second device belongs to their son who is at university in GB and uses the card for living costs. Arrangement noted on file.' This passes timing, subject, and specificity tests and verifies the new device and geography anomaly. However, it does not explain the sudden high spending magnitude, velocity, or night transactions. The network analysis found the account isolated with no suspicious links. Therefore, while part of the rule trigger is explained legitimately, the key anomaly of large, rapid, and night spending remains unexplained on file, leading to an honest verdict of insufficient_evidence. The artefact needed to settle this case is a customer or case note explaining the large sudden transaction amounts in the short time frame.

### Evidence cited

| kind | id | quote or detail |
|---|---|---|
| alert | `AL0345` |  |
| device | `DX01490` |  |
| case_note | `N00207` | Customer explained the second device belongs to their son who is at university in GB and uses the card for living costs. Arrangement noted on file. |

### What would resolve this case

- A case note or customer communication explaining the large sudden transactions in the short time frame.

---

