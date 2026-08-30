# Dispositions

Every one of the 276 alerted accounts in `data/sentinel.db`.

| verdict | accounts | share |
|---|---:|---:|
| `fraud` | 1 | 12.5% |
| `legitimate` | 4 | 50.0% |
| `insufficient_evidence` | 3 | 37.5% |
| **total** | **8** | |

| confidence | accounts |
|---|---:|
| `high` | 4 |
| `medium` | 4 |
| `low` | 0 |

> 268 account(s) have no recorded disposition: A00041, A00050, A00056, A00057, A00058, A00085, A00086, A00087, A00090, A00097, A00100, A00102, A00103, A00105, A00112, A00115, A00118, A00121, A00134, A00139 ...

---

| account_id | verdict | confidence | action | reasoning | evidence |
|---|---|---|---|---|---|
| `A00000` | `insufficient_evidence` | `medium` | `monitor` | The alert (R02) flagged high-value transactions from a relatively new device and new country IP usage. The behaviour analyst found the spending (61,425.89 INR over 4 transactions in 12 hours) to be massively anomalous compared to the baseline and noted the new device and new IP country. The context analyst found a pre-existing case note (N00106, 2026-02-25) explaining the new device as belonging to the customer's son in Singapore, which partially explains the new device limb of the alert but does not explain the large transaction amounts or country IP usage. The note was filed before the incident, is specific, and verified identity, but it only explains the device change. Given the customer did not disown the activity and the network analyst found no linked fraud or network signals, the unexplained large transactions and foreign IP remain suspicious. Without further customer contact clarifying the large transaction amounts and the reason for new country IP use, the case lacks sufficient evidence to deem the activity legitimate or confirm fraud. Therefore, the disposition is insufficient evidence with medium confidence due to partial explanation but unresolved risk. **Needs:** Customer confirmation or case note explaining the large transaction amounts over a short period and the use of the new country IP in Singapore | `N00106` |
| `A00008` | `fraud` | `high` | `block_card` | The customer explicitly disowned the activity in case note N00051 filed on 2026-02-28 stating: "Inbound call from customer. They received an SMS about a device registration they did not perform. They have not travelled and still hold the physical card." This is a strong denial typed soon after the incident, indicating the transactions and device registration were unauthorized. Multiple alerts fired on the account indicating suspicious behavior: a new device registered seconds before a high-value transaction, a velocity spike of 3 transactions in 18 minutes, impossible travel across GB, DE, AE within minutes, and high-value night transactions far exceeding the previous maximum transaction amount. Behavior is clearly anomalous against the customer baseline and consistent with takeover fraud. Network analysis shows the account is isolated, limiting external network risk but not exculpating the activity. Combined, the disownment and behavioral anomaly conclusively indicate fraud. Action: block the card and escalate for investigation due to ongoing risk. | `N00051` |
| `A00013` | `legitimate` | `high` | `none` | Alert AL0326 fired under rule R02, detecting a high-value transaction from a new device within 24 hours. The total transaction amount was 116,031.79 with a largest single transaction of 114,017.20 from device D000130, all originating in India, which was outside the customer's baseline average transaction amount of 164.17 and maximum 1,462.66. Case note N00195, filed on 2026-02-27 before the transactions, explains: "Customer intends to buy jewellery for a wedding this week, value roughly 114,017. Advised the transaction may be flagged and asked them to keep the phone available for OTP." This pre-existing, specific explanation on file covers the exact anomaly the rule detected, and the customer identity was verified in branch, satisfying timing, subject and specificity tests. There is no network evidence of fraud involvement and no customer disputes. Therefore, the explanation breaks the alert's conjunction. Remaining behaviour is consistent with a legitimate, large purchase. Verdict is legitimate with high confidence. | `AL0326`, `N00195` |
| `A00022` | `legitimate` | `medium` | `monitor` | The impossible travel alert AL0394 was triggered by transactions in the US and India within hours, with anomalous spending total of $102,258.30 over 12 hours against a baseline max of $3,817.12 and increased night activity. Case note N00243 predates the alert and explains: "Customer explained the second device belongs to their son who is at university in US and uses the card for living costs. Arrangement noted on file." This explains the foreign geographic spend and device use, covering key anomaly aspects. Dispute DP0085 "I did make this purchase but the goods never arrived, so I want to raise a chargeback with the merchant," filed after the alert, does not counter the family use explanation. Network analysis shows isolated account with no fraud ring. Taken together, this weighs the evidence as legitimate usage with moderate confidence, given the partial explanation for the high amounts and mixed geography. | `AL0394`, `N00243`, `DP0085` |
| `A00025` | `insufficient_evidence` | `high` | `monitor` | An alert fired on strongly anomalous spending behaviour over 48 hours, crossing 3 countries including a new country NL, with a large gift card purchase. The largest transaction (10,088.47) was more than twice the baseline maximum (4,579.51) and total spend was 209 times the baseline average daily spend. The account is a student segment with full KYC and home country IN. The file is silent on any explanation: no case notes, no disputes, no prior investigations. As quoted: 'NONE FOUND. There are no case notes for the customer behind A00025. Nobody has recorded an explanation.' This fails all narrative reading tests for timing, subject, and specificity, leaving the anomaly unexplained. Network analysis found the account isolated with no signals mitigating suspicion. Given the strong anomaly and no explanation, the state is suspicious but unresolved, so insufficient evidence with high confidence is recorded. The recommended action is to monitor while seeking customer confirmation or a verifying case note. **Needs:** A case note or dispute explaining the anomalous spending pattern crossing three countries including the new country NL.; Customer confirmation of whether they authorised the large cumulative spending burst over 48 hours ending 2026-03-01. | - |
| `A00031` | `legitimate` | `medium` | `monitor` | Alert AL0306 fired due to a high-value transaction from a device first seen in 24 hours, indicating possible takeover (rule R02). However, the device D000310 used was old, registered over 320 days before the incident, removing the new device suspicion (Behaviour Analyst finding). Four transactions totaling 84,273.25 INR occurred during daytime in the customer's home country IN, consistent with known geography and time, though amounts were above baseline. Case note N00182, filed before the incident, recorded: "Branch visit. Customer intends to buy jewellery for a wedding this week, value roughly 84,170. Advised the transaction may be flagged and asked them to keep the phone available for OTP." This explains the anomaly detected by the rule before it happened and verifies customer intent. A dispute DP0068 filed after the incident states: "I recognise the merchant but the amount is higher than I expected. I would like this looked at." While this raises concern on amount, it does not disown the transactions. The network analysis found an isolated device and no significant fraud signal, with only a mild lift in the gift card merchant category not linked to alert AL0306. Taken together, the pre-existing verified explanation breaks the alert condition and no contradictions are present, so the transactions are legitimate. Monitoring is recommended until the dispute is resolved to confirm the amounts. | `AL0306`, `D000310`, `N00182`, `DP0068` |
| `A00032` | `legitimate` | `high` | `none` | Two medium severity alerts fired on 2026-02-28 for a velocity spike of 13 transactions within about an hour totaling 6,251.04 across India, Thailand, and Singapore, many in high-risk categories such as gift cards and gaming. Behaviour analysis determined that the device was old, the countries mostly familiar, and amounts consistent with the customer's historical maximums, indicating an anomalous but benign pattern. Context analyst found a prior note N00156 filed before the incident on 2026-02-27 stating: "No concerns raised. Customer historically increases spend sharply in this period each year, consistent with prior two years," which explains the specific anomaly and timing. Network analysis found the account to be isolated with no fraud-related device or merchant overlaps. Given this pre-existing, verified explanation supported by case note N00156, and the lack of contradictory network signals, the verdict is legitimate with high confidence. | `N00156` |
| `A00037` | `insufficient_evidence` | `medium` | `monitor` | Alert triggered on two transactions within 4 hours involving a £10,645.61 approved spend and £36,245.29 declined on 28 Feb 2026, far exceeding the customer's baseline max of £2,155.67 (behaviour analyst). Case note N00097 from 19 Feb 2026 states: "Customer confirmed their spouse uses the supplementary card on the same account. Both handsets are registered. This has been the pattern since the account opened," explaining the multiple devices but not the large spend or merchant risk. Network analysis found no device sharing beyond this account and indicated isolated network status with a moderate fraud lift (1.7) for one crypto exchange merchant involved. The behaviour is anomalous and partially explained but lacks any direct customer confirmation or disowning of the large unusual spend or the merchant risk. Therefore, verdict is insufficient evidence, with monitoring recommended to watch for further unusual activity. **Needs:** Customer confirmation on the legitimacy of the large transaction amounts and use of flagged merchants during the 28 Feb 2026 transactions | `N00097` |
| `A00041` | - | - | - | *no disposition recorded* | |
| `A00050` | - | - | - | *no disposition recorded* | |
| `A00056` | - | - | - | *no disposition recorded* | |
| `A00057` | - | - | - | *no disposition recorded* | |
| `A00058` | - | - | - | *no disposition recorded* | |
| `A00085` | - | - | - | *no disposition recorded* | |
| `A00086` | - | - | - | *no disposition recorded* | |
| `A00087` | - | - | - | *no disposition recorded* | |
| `A00090` | - | - | - | *no disposition recorded* | |
| `A00097` | - | - | - | *no disposition recorded* | |
| `A00100` | - | - | - | *no disposition recorded* | |
| `A00102` | - | - | - | *no disposition recorded* | |
| `A00103` | - | - | - | *no disposition recorded* | |
| `A00105` | - | - | - | *no disposition recorded* | |
| `A00112` | - | - | - | *no disposition recorded* | |
| `A00115` | - | - | - | *no disposition recorded* | |
| `A00118` | - | - | - | *no disposition recorded* | |
| `A00121` | - | - | - | *no disposition recorded* | |
| `A00134` | - | - | - | *no disposition recorded* | |
| `A00139` | - | - | - | *no disposition recorded* | |
| `A00146` | - | - | - | *no disposition recorded* | |
| `A00150` | - | - | - | *no disposition recorded* | |
| `A00152` | - | - | - | *no disposition recorded* | |
| `A00158` | - | - | - | *no disposition recorded* | |
| `A00160` | - | - | - | *no disposition recorded* | |
| `A00164` | - | - | - | *no disposition recorded* | |
| `A00168` | - | - | - | *no disposition recorded* | |
| `A00169` | - | - | - | *no disposition recorded* | |
| `A00170` | - | - | - | *no disposition recorded* | |
| `A00173` | - | - | - | *no disposition recorded* | |
| `A00176` | - | - | - | *no disposition recorded* | |
| `A00177` | - | - | - | *no disposition recorded* | |
| `A00181` | - | - | - | *no disposition recorded* | |
| `A00182` | - | - | - | *no disposition recorded* | |
| `A00184` | - | - | - | *no disposition recorded* | |
| `A00185` | - | - | - | *no disposition recorded* | |
| `A00186` | - | - | - | *no disposition recorded* | |
| `A00188` | - | - | - | *no disposition recorded* | |
| `A00191` | - | - | - | *no disposition recorded* | |
| `A00192` | - | - | - | *no disposition recorded* | |
| `A00204` | - | - | - | *no disposition recorded* | |
| `A00207` | - | - | - | *no disposition recorded* | |
| `A00219` | - | - | - | *no disposition recorded* | |
| `A00229` | - | - | - | *no disposition recorded* | |
| `A00232` | - | - | - | *no disposition recorded* | |
| `A00236` | - | - | - | *no disposition recorded* | |
| `A00237` | - | - | - | *no disposition recorded* | |
| `A00244` | - | - | - | *no disposition recorded* | |
| `A00246` | - | - | - | *no disposition recorded* | |
| `A00251` | - | - | - | *no disposition recorded* | |
| `A00253` | - | - | - | *no disposition recorded* | |
| `A00258` | - | - | - | *no disposition recorded* | |
| `A00264` | - | - | - | *no disposition recorded* | |
| `A00268` | - | - | - | *no disposition recorded* | |
| `A00271` | - | - | - | *no disposition recorded* | |
| `A00272` | - | - | - | *no disposition recorded* | |
| `A00273` | - | - | - | *no disposition recorded* | |
| `A00280` | - | - | - | *no disposition recorded* | |
| `A00283` | - | - | - | *no disposition recorded* | |
| `A00292` | - | - | - | *no disposition recorded* | |
| `A00297` | - | - | - | *no disposition recorded* | |
| `A00298` | - | - | - | *no disposition recorded* | |
| `A00305` | - | - | - | *no disposition recorded* | |
| `A00307` | - | - | - | *no disposition recorded* | |
| `A00308` | - | - | - | *no disposition recorded* | |
| `A00316` | - | - | - | *no disposition recorded* | |
| `A00320` | - | - | - | *no disposition recorded* | |
| `A00326` | - | - | - | *no disposition recorded* | |
| `A00327` | - | - | - | *no disposition recorded* | |
| `A00333` | - | - | - | *no disposition recorded* | |
| `A00340` | - | - | - | *no disposition recorded* | |
| `A00343` | - | - | - | *no disposition recorded* | |
| `A00346` | - | - | - | *no disposition recorded* | |
| `A00356` | - | - | - | *no disposition recorded* | |
| `A00359` | - | - | - | *no disposition recorded* | |
| `A00367` | - | - | - | *no disposition recorded* | |
| `A00368` | - | - | - | *no disposition recorded* | |
| `A00371` | - | - | - | *no disposition recorded* | |
| `A00396` | - | - | - | *no disposition recorded* | |
| `A00404` | - | - | - | *no disposition recorded* | |
| `A00410` | - | - | - | *no disposition recorded* | |
| `A00423` | - | - | - | *no disposition recorded* | |
| `A00428` | - | - | - | *no disposition recorded* | |
| `A00430` | - | - | - | *no disposition recorded* | |
| `A00436` | - | - | - | *no disposition recorded* | |
| `A00437` | - | - | - | *no disposition recorded* | |
| `A00440` | - | - | - | *no disposition recorded* | |
| `A00446` | - | - | - | *no disposition recorded* | |
| `A00458` | - | - | - | *no disposition recorded* | |
| `A00460` | - | - | - | *no disposition recorded* | |
| `A00463` | - | - | - | *no disposition recorded* | |
| `A00464` | - | - | - | *no disposition recorded* | |
| `A00465` | - | - | - | *no disposition recorded* | |
| `A00466` | - | - | - | *no disposition recorded* | |
| `A00481` | - | - | - | *no disposition recorded* | |
| `A00484` | - | - | - | *no disposition recorded* | |
| `A00486` | - | - | - | *no disposition recorded* | |
| `A00488` | - | - | - | *no disposition recorded* | |
| `A00490` | - | - | - | *no disposition recorded* | |
| `A00491` | - | - | - | *no disposition recorded* | |
| `A00495` | - | - | - | *no disposition recorded* | |
| `A00498` | - | - | - | *no disposition recorded* | |
| `A00501` | - | - | - | *no disposition recorded* | |
| `A00513` | - | - | - | *no disposition recorded* | |
| `A00516` | - | - | - | *no disposition recorded* | |
| `A00517` | - | - | - | *no disposition recorded* | |
| `A00520` | - | - | - | *no disposition recorded* | |
| `A00525` | - | - | - | *no disposition recorded* | |
| `A00531` | - | - | - | *no disposition recorded* | |
| `A00534` | - | - | - | *no disposition recorded* | |
| `A00535` | - | - | - | *no disposition recorded* | |
| `A00538` | - | - | - | *no disposition recorded* | |
| `A00554` | - | - | - | *no disposition recorded* | |
| `A00559` | - | - | - | *no disposition recorded* | |
| `A00560` | - | - | - | *no disposition recorded* | |
| `A00561` | - | - | - | *no disposition recorded* | |
| `A00564` | - | - | - | *no disposition recorded* | |
| `A00565` | - | - | - | *no disposition recorded* | |
| `A00572` | - | - | - | *no disposition recorded* | |
| `A00583` | - | - | - | *no disposition recorded* | |
| `A00588` | - | - | - | *no disposition recorded* | |
| `A00589` | - | - | - | *no disposition recorded* | |
| `A00590` | - | - | - | *no disposition recorded* | |
| `A00591` | - | - | - | *no disposition recorded* | |
| `A00593` | - | - | - | *no disposition recorded* | |
| `A00594` | - | - | - | *no disposition recorded* | |
| `A00595` | - | - | - | *no disposition recorded* | |
| `A00598` | - | - | - | *no disposition recorded* | |
| `A00603` | - | - | - | *no disposition recorded* | |
| `A00605` | - | - | - | *no disposition recorded* | |
| `A00609` | - | - | - | *no disposition recorded* | |
| `A00610` | - | - | - | *no disposition recorded* | |
| `A00616` | - | - | - | *no disposition recorded* | |
| `A00619` | - | - | - | *no disposition recorded* | |
| `A00625` | - | - | - | *no disposition recorded* | |
| `A00628` | - | - | - | *no disposition recorded* | |
| `A00629` | - | - | - | *no disposition recorded* | |
| `A00632` | - | - | - | *no disposition recorded* | |
| `A00638` | - | - | - | *no disposition recorded* | |
| `A00642` | - | - | - | *no disposition recorded* | |
| `A00647` | - | - | - | *no disposition recorded* | |
| `A00649` | - | - | - | *no disposition recorded* | |
| `A00650` | - | - | - | *no disposition recorded* | |
| `A00655` | - | - | - | *no disposition recorded* | |
| `A00659` | - | - | - | *no disposition recorded* | |
| `A00660` | - | - | - | *no disposition recorded* | |
| `A00665` | - | - | - | *no disposition recorded* | |
| `A00673` | - | - | - | *no disposition recorded* | |
| `A00675` | - | - | - | *no disposition recorded* | |
| `A00679` | - | - | - | *no disposition recorded* | |
| `A00683` | - | - | - | *no disposition recorded* | |
| `A00692` | - | - | - | *no disposition recorded* | |
| `A00693` | - | - | - | *no disposition recorded* | |
| `A00697` | - | - | - | *no disposition recorded* | |
| `A00698` | - | - | - | *no disposition recorded* | |
| `A00707` | - | - | - | *no disposition recorded* | |
| `A00713` | - | - | - | *no disposition recorded* | |
| `A00715` | - | - | - | *no disposition recorded* | |
| `A00716` | - | - | - | *no disposition recorded* | |
| `A00717` | - | - | - | *no disposition recorded* | |
| `A00718` | - | - | - | *no disposition recorded* | |
| `A00719` | - | - | - | *no disposition recorded* | |
| `A00727` | - | - | - | *no disposition recorded* | |
| `A00731` | - | - | - | *no disposition recorded* | |
| `A00736` | - | - | - | *no disposition recorded* | |
| `A00742` | - | - | - | *no disposition recorded* | |
| `A00746` | - | - | - | *no disposition recorded* | |
| `A00751` | - | - | - | *no disposition recorded* | |
| `A00752` | - | - | - | *no disposition recorded* | |
| `A00758` | - | - | - | *no disposition recorded* | |
| `A00768` | - | - | - | *no disposition recorded* | |
| `A00770` | - | - | - | *no disposition recorded* | |
| `A00775` | - | - | - | *no disposition recorded* | |
| `A00776` | - | - | - | *no disposition recorded* | |
| `A00779` | - | - | - | *no disposition recorded* | |
| `A00780` | - | - | - | *no disposition recorded* | |
| `A00782` | - | - | - | *no disposition recorded* | |
| `A00786` | - | - | - | *no disposition recorded* | |
| `A00787` | - | - | - | *no disposition recorded* | |
| `A00789` | - | - | - | *no disposition recorded* | |
| `A00794` | - | - | - | *no disposition recorded* | |
| `A00795` | - | - | - | *no disposition recorded* | |
| `A00797` | - | - | - | *no disposition recorded* | |
| `A00804` | - | - | - | *no disposition recorded* | |
| `A00807` | - | - | - | *no disposition recorded* | |
| `A00809` | - | - | - | *no disposition recorded* | |
| `A00817` | - | - | - | *no disposition recorded* | |
| `A00818` | - | - | - | *no disposition recorded* | |
| `A00820` | - | - | - | *no disposition recorded* | |
| `A00825` | - | - | - | *no disposition recorded* | |
| `A00831` | - | - | - | *no disposition recorded* | |
| `A00832` | - | - | - | *no disposition recorded* | |
| `A00845` | - | - | - | *no disposition recorded* | |
| `A00847` | - | - | - | *no disposition recorded* | |
| `A00857` | - | - | - | *no disposition recorded* | |
| `A00861` | - | - | - | *no disposition recorded* | |
| `A00862` | - | - | - | *no disposition recorded* | |
| `A00868` | - | - | - | *no disposition recorded* | |
| `A00869` | - | - | - | *no disposition recorded* | |
| `A00876` | - | - | - | *no disposition recorded* | |
| `A00877` | - | - | - | *no disposition recorded* | |
| `A00879` | - | - | - | *no disposition recorded* | |
| `A00881` | - | - | - | *no disposition recorded* | |
| `A00884` | - | - | - | *no disposition recorded* | |
| `A00890` | - | - | - | *no disposition recorded* | |
| `A00900` | - | - | - | *no disposition recorded* | |
| `A00909` | - | - | - | *no disposition recorded* | |
| `A00912` | - | - | - | *no disposition recorded* | |
| `A00914` | - | - | - | *no disposition recorded* | |
| `A00915` | - | - | - | *no disposition recorded* | |
| `A00916` | - | - | - | *no disposition recorded* | |
| `A00920` | - | - | - | *no disposition recorded* | |
| `A00922` | - | - | - | *no disposition recorded* | |
| `A00925` | - | - | - | *no disposition recorded* | |
| `A00934` | - | - | - | *no disposition recorded* | |
| `A00939` | - | - | - | *no disposition recorded* | |
| `A00944` | - | - | - | *no disposition recorded* | |
| `A00948` | - | - | - | *no disposition recorded* | |
| `A00952` | - | - | - | *no disposition recorded* | |
| `A00957` | - | - | - | *no disposition recorded* | |
| `A00959` | - | - | - | *no disposition recorded* | |
| `A00969` | - | - | - | *no disposition recorded* | |
| `A00972` | - | - | - | *no disposition recorded* | |
| `A00974` | - | - | - | *no disposition recorded* | |
| `A00975` | - | - | - | *no disposition recorded* | |
| `A00985` | - | - | - | *no disposition recorded* | |
| `A00986` | - | - | - | *no disposition recorded* | |
| `A00990` | - | - | - | *no disposition recorded* | |
| `A00991` | - | - | - | *no disposition recorded* | |
| `A00993` | - | - | - | *no disposition recorded* | |
| `A01000` | - | - | - | *no disposition recorded* | |
| `A01002` | - | - | - | *no disposition recorded* | |
| `A01005` | - | - | - | *no disposition recorded* | |
| `A01014` | - | - | - | *no disposition recorded* | |
| `A01018` | - | - | - | *no disposition recorded* | |
| `A01020` | - | - | - | *no disposition recorded* | |
| `A01026` | - | - | - | *no disposition recorded* | |
| `A01032` | - | - | - | *no disposition recorded* | |
| `A01034` | - | - | - | *no disposition recorded* | |
| `A01039` | - | - | - | *no disposition recorded* | |
| `A01045` | - | - | - | *no disposition recorded* | |
| `A01052` | - | - | - | *no disposition recorded* | |
| `A01054` | - | - | - | *no disposition recorded* | |
| `A01055` | - | - | - | *no disposition recorded* | |
| `A01065` | - | - | - | *no disposition recorded* | |
| `A01069` | - | - | - | *no disposition recorded* | |
| `A01084` | - | - | - | *no disposition recorded* | |
| `A01085` | - | - | - | *no disposition recorded* | |
| `A01091` | - | - | - | *no disposition recorded* | |
| `A01105` | - | - | - | *no disposition recorded* | |
| `A01110` | - | - | - | *no disposition recorded* | |
| `A01116` | - | - | - | *no disposition recorded* | |
| `A01123` | - | - | - | *no disposition recorded* | |
| `A01128` | - | - | - | *no disposition recorded* | |
| `A01131` | - | - | - | *no disposition recorded* | |
| `A01134` | - | - | - | *no disposition recorded* | |
| `A01135` | - | - | - | *no disposition recorded* | |
| `A01137` | - | - | - | *no disposition recorded* | |
| `A01143` | - | - | - | *no disposition recorded* | |
| `A01146` | - | - | - | *no disposition recorded* | |
| `A01156` | - | - | - | *no disposition recorded* | |
| `A01157` | - | - | - | *no disposition recorded* | |
| `A01166` | - | - | - | *no disposition recorded* | |
| `A01170` | - | - | - | *no disposition recorded* | |
| `A01173` | - | - | - | *no disposition recorded* | |
| `A01175` | - | - | - | *no disposition recorded* | |
| `A01184` | - | - | - | *no disposition recorded* | |
| `A01194` | - | - | - | *no disposition recorded* | |
