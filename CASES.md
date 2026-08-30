# Three worked cases

One obvious fraud, one convincing false positive, and one that could not be
resolved. Each is chosen from the recorded results by confidence and citation
depth, not hand-picked, and each shows exactly what the supervisor received
from every specialist.

Everything below is reproducible: run `sentinel case <id> --show-trail`.

---

## obvious fraud: `A00008`

**Verdict: `fraud`, confidence `high`, action `block_card`**

### What fired

| alert | rule | what the rule detects | severity | triggered |
|---|---|---|---|---|
| `AL0117` | R02 New device high value | Transaction above 25,000 from a device first seen in the last 24 hours. | high | 2026-02-28T01:21:10 |
| `AL0118` | R01 Velocity spike | More than 6 authorisations on one card within 60 minutes. | high | 2026-02-28T01:21:10 |
| `AL0119` | R03 Impossible travel | Two authorisations from different countries less than 3 hours apart. | high | 2026-02-28T01:21:10 |
| `AL0120` | R07 Night time high value | Transaction above 40,000 between 01:00 and 05:00 local. | high | 2026-02-28T01:21:10 |

Incident window: `2026-02-28T01:21:10` to `2026-02-28T01:39:10`.

### The transactions inside that window

| txn | time | amount | country | merchant | category | result |
|---|---|---:|---|---|---|---|
| `T0107081` | 2026-02-28T01:21:10 | 30,910.38 | GB | Electronics 399 | electronics | approved |
| `T0107082` | 2026-02-28T01:30:10 | 64,507.76 | DE | Gift cards 946 | giftcard | approved |
| `T0107083` | 2026-02-28T01:39:10 | 34,273.59 | AE | Crypto exchange 946 | crypto | declined |

### What the file said

**`N00051`** - 2026-02-28T09:21:10, P. Kaur (chat), 0.3 days after the incident

> Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card.


### What each specialist reported back

#### Behaviour

*10,830 characters produced inside this specialist, 2,896 crossed back to the supervisor (73% discarded).*

```
Four alerts fired on account A00008 over a short incident window (about 18 minutes on 2026-02-28 around 01:21-01:39):

- AL0117 (R02): New device high value, triggered by a large transaction (34,273.59) from a device first seen at the incident timestamp.
- AL0118 (R01): Velocity spike, more than 6 authorizations within 60 minutes (here 3 transactions in 18 minutes).
- AL0119 (R03): Impossible travel, transactions from three different countries (GB, DE, AE) within minutes.
- AL0120 (R07): Night time high value, transaction above 40,000 at night (01:21 local).

Incident transactions:

- 3 transactions over ~18 minutes, total 129,691.73, largest 64,507.76, from 3 countries (GB, DE, AE), all on the same new device DX01439 registered seconds before the incident (device age 0 hours).
- One transaction (34,273.59) declined; two others approved (30,910.38 and 64,507.76).
- All occurred at night (near 01:30).

Baseline:

- Customer averages 123 transactions over several months, average amount 278.02, max amount 4,950.94.
- Typical countries are 8 distinct with India (IN), Germany (DE), Singapore (SG), Netherlands (NL), Great Britain (GB), UAE (AE), Thailand (TH), USA (US), Malaysia (MY).
- The night transaction rate is low at 1.6% historically, but the incident was entirely nighttime.
- The customer's usual maximum single transaction (~4,951) is much lower than these incident amounts (30k to 64k).

Device:

- The incident device is brand new, registered exactly at incident start, with no history.
- Previously used device is much older, single iOS tablet with regular moderate spend.

Geography:

- Countries involved in incident (GB, DE, AE) are not new in customer's history.
- However, the speed of transactions from three different countries within less than 18 minutes triggers impossible travel.
- AE country was used before from 01 Jan 2026, GB and DE since February 2026.

Merchants:

- One transaction at electronics merchant, one at gift card merchant, one declined at crypto merchant.
- High-risk categories (gift card and crypto) are represented in incident.

Summary:

- The customer's typical transactions are much smaller in amount, with low night usage.
- The incident features three high-value transactions in different countries in very short time.
- The device used is brand new and used only in the incident.
- The velocity (number transactions per hour) is higher than baseline (3 in 18 minutes, where baseline avg daily txn count 123 over months, roughly 2 per day).
- The use of high-risk categories and declined transaction is potentially suspicious.

Assessment: The spending is anomalous compared to baseline on amounts, timing, device age and cross-country rapid sequence. The spending pattern fits known fraud signals but no direct evidence of benign explanation like known device or geographic consistency or regular night usage.

Therefore: anomalous
```

#### Context

*2,734 characters produced inside this specialist, 861 crossed back to the supervisor (69% discarded).*

```
Customer profile: Segment retail, KYC level full, home country India (A00008).

Case note N00051 dated 2026-02-28 with timing after the alert (-0.3 days before alert): "Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card." 

This fails the timing test for explanation as it is after the incident (timing: after_alert), so it is a reaction, not a pre-existing explanation. It disowns the new device limb of the alert (new device usage).

No notes mention multiple countries or high-value night transactions that could explain the incident.

No disputes exist on this account.

No prior cases or investigations exist on this account.

Assessment: disowned (customer denies making these transactions or device registrations; no pre-existing explanation found).
```

#### Network

*2,915 characters produced inside this specialist, 765 crossed back to the supervisor (74% discarded).*

```
Account A00008 is isolated on the device dimension; none of its devices are shared with any other customers, which argues against involvement in a mule or fraud ring.

Regarding merchant overlap, A00008 transacted with some high-risk merchants, notably "Crypto exchange 918" (M0355) with a lift of 1.82, meaning this merchant is significantly over-represented among fraud accounts. Other merchants related to money transfer, gaming, and gift cards show lifts close to or below 1.5, indicating no abnormal fraud association beyond popularity.

No evidence from device sharing or merchant overlap indicates that A00008 is linked to other accounts with confirmed fraud or open alerts. The account appears network-wise isolated despite the suspicious transaction flags.
```

#### Disposition

*30,643 characters produced inside this specialist, 1,656 crossed back to the supervisor (95% discarded).*

```
The customer explicitly disowned the activity associated with account A00008 in case note N00051 dated 2026-02-28, stating: "Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card." This is a strong post-incident denial indicating unauthorized device registration and transactions.

Behavior analysis found multiple alerts firing just before the denial: a new device registered seconds before a high-value transaction, a velocity spike (3 transactions in 18 minutes), impossible travel across Great Britain, Germany, and the UAE in minutes, and high-value night transactions vastly exceeding the customer's historic maximum transaction (~30k to 64k vs ~4,951). These are clear anomalies consistent with account takeover fraud.

No prior case notes or disputes explain these anomalies. Network analysis shows the account is isolated, reducing risk of a wider fraud ring but not negating fraud on this account.

Given the customer's denial combined with multiple strong behavioral anomalies matching typical fraud typologies, the verdict is fraud with high confidence.

The appropriate action is to block the card to stop ongoing losses and escalate the case for further human investigation to leverage powers beyond this desk.

The block and escalation requests have been queued for analyst review and have not yet executed, as per policy.

Evidence cited: case note N00051 verbatim. All other behavior evidence is summarized from the brief.

This disposition follows policies in evidence standards, narrative reading, risk appetite, and escalation matrix.
```

### How the supervisor weighed them

The customer explicitly disowned the activity in case note N00051 filed on 2026-02-28 stating: "Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card." This is a strong denial typed soon after the incident, indicating the transactions and device registration were unauthorized. Multiple alerts fired on the account indicating suspicious behavior: a new device registered seconds before a high-value transaction, a velocity spike of 3 transactions in 18 minutes, impossible travel across GB, DE, AE within minutes, and high-value night transactions far exceeding the previous maximum transaction amount. Behavior is clearly anomalous against the customer baseline and consistent with takeover fraud. Network analysis shows the account is isolated, limiting external network risk but not exculpating the activity. Combined, the disownment and behavioral anomaly conclusively indicate fraud. Action: block the card and escalate for investigation due to ongoing risk.

### Evidence cited

| kind | id | quote or detail |
|---|---|---|
| case_note | `N00051` | Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card. |

---

## convincing false positive: `A00013`

**Verdict: `legitimate`, confidence `high`, action `none`**

### What fired

| alert | rule | what the rule detects | severity | triggered |
|---|---|---|---|---|
| `AL0326` | R02 New device high value | Transaction above 25,000 from a device first seen in the last 24 hours. | high | 2026-02-28T08:21:33 |

Incident window: `2026-02-28T08:21:33` to `2026-02-28T08:21:33`.

### The transactions inside that window

| txn | time | amount | country | merchant | category | result |
|---|---|---:|---|---|---|---|
| `T0107758` | 2026-02-28T08:21:33 | 114,017.20 | IN | Jewellery 660 | jewellery | approved |

### What the file said

**`N00195`** - 2026-02-27T16:21:33, R. Menon (branch), 0.7 days before the incident

> Branch visit. Customer intends to buy jewellery for a wedding this week, value roughly 114,017. Advised the transaction may be flagged and asked them to keep the phone available for OTP.


### What each specialist reported back

#### Behaviour

*4,510 characters produced inside this specialist, 1,165 crossed back to the supervisor (74% discarded).*

```
One alert fired: AL0326 under rule R02 ("New device high value"), triggered by a transaction of 114,017.20 on 2026-02-28 08:21:33 from device D000130.

Incident in brief: 3 transactions totaling 116,031.79 within 24 hours, with the largest single transaction at 114,017.20, all from India (IN), on one device, none declined, none at night.

Baseline analysis: Normal average transaction amount is 164.17 with maximum 1,462.66; transaction count baseline is 75 over a similar but longer period excluding last 7 days. Night transaction rate is 4%, but none in incident.

Device D000130 is actually old for this customer, registered on 2023-03-21 with about 25,808 hours (nearly 3 years) before the incident, used previously for 79 transactions totaling 128,817.79.

The incident's largest spend (114k) massively exceeds past maximum (1.4k), and the total of 116k in 3 transactions is well beyond baseline transaction amounts and counts, indicating heavy spending unusually large compared to historical behavior.

No night transactions and all from previously used device and country suggest consistency, but the magnitude alone looks alarming.

Assessment: anomalous.
```

#### Context

*2,664 characters produced inside this specialist, 706 crossed back to the supervisor (73% discarded).*

```
Segment: retail, KYC level: simplified, home country: IN.

Case note N00195, dated 2026-02-27, before the incident: "Branch visit. Customer intends to buy jewellery for a wedding this week, value roughly 114,017. Advised the transaction may be flagged and asked them to keep the phone available for OTP." This explanation covers the largest single transaction limb of the alert and passes timing, subject and specificity tests, with verification by branch visit and OTP advice.

There are no disputes filed by the customer denying or questioning the transaction.

A prior case PC0109 closed on 2025-09-13 as false_positive, where the customer confirmed all transactions were their own.

Finding: explained.
```

#### Network

*1,862 characters produced inside this specialist, 422 crossed back to the supervisor (77% discarded).*

```
Account A00013 is acting alone. There are no devices shared with other customers, indicating no direct peer connections. The merchants used by A00013 in high-risk categories such as money transfer, gaming, and gift cards show lift values below 1.5 (1.38, 1.03, and 1.13 respectively), meaning these overlaps are no more than what popularity predicts and do not indicate a fraud network. Therefore, the account is isolated.
```

#### Disposition

*22,481 characters produced inside this specialist, 971 crossed back to the supervisor (96% discarded).*

```
The alert AL0326 fired under rule R02, which identifies high-value transactions from a device first seen within 24 hours. The transactions totaled 116,031.79, with the largest single transaction at 114,017.20 from device D000130, all from India. This was anomalous compared to the customer's baseline average transaction of 164.17 and max 1,462.66.

However, case note N00195 dated before the incident explains the anomaly specifically: "Customer intends to buy jewellery for a wedding this week, value roughly 114,017. Advised the transaction may be flagged and asked them to keep the phone available for OTP." This note covers the exact anomaly discovered by the rule and shows the customer disclosed and verified the transaction beforehand. The network analysis shows account isolation, reducing fraud concerns.

Because the explanation fits the alert's conjunction and identity is verified, the verdict is legitimate with high confidence. No further action is needed.
```

### How the supervisor weighed them

Alert AL0326 fired under rule R02, detecting a high-value transaction from a new device within 24 hours. The total transaction amount was 116,031.79 with a largest single transaction of 114,017.20 from device D000130, all originating in India, which was outside the customer's baseline average transaction amount of 164.17 and maximum 1,462.66. Case note N00195, filed on 2026-02-27 before the transactions, explains: "Customer intends to buy jewellery for a wedding this week, value roughly 114,017. Advised the transaction may be flagged and asked them to keep the phone available for OTP." This pre-existing, specific explanation on file covers the exact anomaly the rule detected, and the customer identity was verified in branch, satisfying timing, subject and specificity tests. There is no network evidence of fraud involvement and no customer disputes. Therefore, the explanation breaks the alert's conjunction. Remaining behaviour is consistent with a legitimate, large purchase. Verdict is legitimate with high confidence.

### Evidence cited

| kind | id | quote or detail |
|---|---|---|
| alert | `AL0326` | R02 New device high value anomaly detection |
| case_note | `N00195` | Customer intends to buy jewellery for a wedding this week, value roughly 114,017. Advised the transaction may be flagged and asked them to keep the phone available for OTP. |

---

## could not be resolved: `A00025`

**Verdict: `insufficient_evidence`, confidence `high`, action `monitor`**

### What fired

| alert | rule | what the rule detects | severity | triggered |
|---|---|---|---|---|
| `AL0063` | R08 Limit approach | Cumulative spend crosses 90 percent of credit limit within 48 hours. | high | 2026-03-01T09:01:55 |

Incident window: `2026-03-01T09:01:55` to `2026-03-02T03:01:55`.

### The transactions inside that window

| txn | time | amount | country | merchant | category | result |
|---|---|---:|---|---|---|---|
| `T0106925` | 2026-03-01T09:01:55 | 6,881.49 | US | Gift cards 841 | giftcard | approved |
| `T0106926` | 2026-03-01T12:01:55 | 4,850.56 | IN | Jewellery 660 | jewellery | approved |
| `T0106927` | 2026-03-01T15:01:55 | 6,775.16 | IN | Jewellery 874 | jewellery | approved |
| `T0002601` | 2026-03-01T16:36:33 | 31.50 | IN | Transport 131 | transport | approved |
| `T0106928` | 2026-03-01T18:01:55 | 6,752.82 | IN | Electronics 198 | electronics | approved |
| `T0106929` | 2026-03-01T21:01:55 | 7,079.12 | IN | Jewellery 883 | jewellery | declined |
| `T0106930` | 2026-03-02T00:01:55 | 6,586.07 | NL | Jewellery 907 | jewellery | approved |
| `T0106931` | 2026-03-02T03:01:55 | 10,088.47 | IN | Electronics 857 | electronics | declined |

### What the file said

Nothing. There are no case notes.


### What each specialist reported back

#### Behaviour

*8,493 characters produced inside this specialist, 1,535 crossed back to the supervisor (82% discarded).*

```
The single alert fired is AL0063 for rule R08 (Limit approach), indicating the cumulative spend crossed 90% of the credit limit within 48 hours.

Incident summary (8 transactions, 24-hour span): total spend 49,045.19, largest single transaction 10,088.47, from 3 countries (IN, US, NL), 1 device (D000250), 1 night transaction, with 2 declined transactions. The largest transaction (10,088.47) is more than twice the baseline maximum of 4,579.51 and the total spend is approximately 209 times the baseline average daily spend of 234.43.

The customer's baseline shows activity mainly from 1 device (D000250), which is well established, registered over 44,000 hours prior to the incident. Baseline includes transactions from 5 countries including IN and US (both also seen in the incident). However, the NL country transaction is new, seen first during this incident.

The incident involved high-risk merchant categories, notably a large gift card purchase (6,881.49, merchant risk 0.66) from the US, outside the home country IN, and typically large shopping transactions in jewellery and electronics categories.

Credit limit utilization was significant but below the 90% threshold in the last 48 hours (66.4% on a 48,000 limit).

Given the much higher transaction amounts and total volume in a compressed timeframe, coupled with a new country detected in the incident and significant transaction at a high-risk merchant category, the spending is anomalous compared to this customer's historical baseline.

Final assessment: anomalous.
```

#### Context

*2,046 characters produced inside this specialist, 787 crossed back to the supervisor (62% discarded).*

```
Segment: student, KYC level: full, home country: IN.

There are no case notes for A00025; nobody has recorded an explanation or any statement related to the alert. The exact quote: "NONE FOUND. There are no case notes for the customer behind A00025. Nobody has recorded an explanation."

There are no disputes filed by this customer on this account, so no customer-provided explanation or disowning of transactions.

There are no prior investigations for this account, meaning no previous fraud or false positive cases to inform this investigation.

This account file is silent on the anomalous spending pattern. There is no recorded explanation from the customer or colleagues regarding the new device or transactions from multiple countries including the Netherlands.

Verdict: silent.
```

#### Network

*1,405 characters produced inside this specialist, 484 crossed back to the supervisor (66% discarded).*

```
Account A00025 is isolated on the device dimension; no devices are shared with other customers, which argues against participation in a coordinated mule ring. Regarding merchant overlap, the account transacted at a gift card merchant (M0346), but the lift is 1.13 and the reading states "no more than popularity predicts," indicating no unusual overlap with flagged accounts or excess risk beyond the base fraud rate. Thus, this account appears to be isolated with no network signals.
```

#### Disposition

*25,192 characters produced inside this specialist, 1,381 crossed back to the supervisor (95% discarded).*

```
The alert identified a strongly anomalous spending pattern for account A00025, with cumulative spend over 48 hours crossing 90% of the credit limit, involving transactions from three countries including a new one (NL), and high-risk merchant categories including a large gift card purchase. The largest transaction was 10,088.47, more than twice the historical maximum of 4,579.51, and the total spend was about 209 times the baseline average daily spend of 234.43. The customer is a student with full KYC and home country IN.

The account file is silent on any explanation: there are no case notes, disputes, or prior investigations explaining this behaviour, as quoted: "NONE FOUND. There are no case notes for the customer behind A00025. Nobody has recorded an explanation." This fails the narrative reading criteria on timing, subject, and specificity. Network analysis found no unusual device or merchant links.

Given the clear anomaly and absence of any mitigating context, the file lacks sufficient evidence to determine fraud or legitimacy. The verdict is insufficient_evidence with high confidence. The recommended action is to monitor the account while obtaining a case note or dispute explaining the anomalous spending or customer confirmation that these transactions were authorised.

No alert or note identifiers were provided, so no specific citations were included.
```

### How the supervisor weighed them

An alert fired on strongly anomalous spending behaviour over 48 hours, crossing 3 countries including a new country NL, with a large gift card purchase. The largest transaction (10,088.47) was more than twice the baseline maximum (4,579.51) and total spend was 209 times the baseline average daily spend. The account is a student segment with full KYC and home country IN. The file is silent on any explanation: no case notes, no disputes, no prior investigations. As quoted: 'NONE FOUND. There are no case notes for the customer behind A00025. Nobody has recorded an explanation.' This fails all narrative reading tests for timing, subject, and specificity, leaving the anomaly unexplained. Network analysis found the account isolated with no signals mitigating suspicion. Given the strong anomaly and no explanation, the state is suspicious but unresolved, so insufficient evidence with high confidence is recorded. The recommended action is to monitor while seeking customer confirmation or a verifying case note.

### Evidence cited

| kind | id | quote or detail |
|---|---|---|

### What would resolve this case

- A case note or dispute explaining the anomalous spending pattern crossing three countries including the new country NL.
- Customer confirmation of whether they authorised the large cumulative spending burst over 48 hours ending 2026-03-01.

---

