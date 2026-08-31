---
name: risk_appetite
description: Verdict thresholds, how much weight each kind of evidence carries, and what normal looks like per customer segment and KYC level. Load when the verdict is not clear-cut.
---

# Risk Appetite

Sentinel Bank's position, in one sentence: **a defensible wrong call is worth
more than a lucky right one**, because the desk is audited on its reasoning and
customers are harmed by careless blocks.

Two thirds of this queue did nothing wrong. Flagging everything is not caution,
it is a failure to do the job.

## The order of evidence

When sources conflict, this is the ranking the desk applies.

1. **The customer disowning the activity**, in a note or a `10.4 unauthorised`
   dispute. Nothing outranks the account holder saying it was not them.
2. **A pre-existing explanation with identity verification.** A note filed
   before the incident recording a verified device change or a travel notice.
3. **A pre-existing explanation without verification.** Same, but nobody
   confirmed who they were speaking to.
4. **Behavioural anomaly against the customer's own baseline.** Strong, but it
   is what fired the rule in the first place, so it cannot also be the answer.
5. **Network links.** An escalator, rarely a verdict on its own.
6. **Prior case history.** Sets a prior. Never decides.
7. **Which rule fired.** The weakest signal on the desk. The best rule is right
   59% of the time.

**Context outranks behaviour when the explanation fits.** The numbers cannot
tell a phone upgrade from a takeover. A colleague who verified identity on
video can.

## Verdict thresholds

### fraud, high confidence

Either the customer has disowned the activity, or **all** of:
- the behaviour is clearly anomalous against this customer's own baseline, and
- nothing on file explains it, and
- the pattern matches a typology cleanly, or the network evidence is strong.

### fraud, medium confidence

The behaviour is anomalous and unexplained, but the typology match is partial,
or the anomaly could plausibly be a benign event nobody happened to record.

### legitimate, high confidence

A record on file explains the anomaly and passes all three tests in
`narrative_reading` - timing, subject, specificity - and identity was verified,
and there is no network signal.

### legitimate, medium confidence

An explanation exists and fits, but is unverified, vague, or covers most of the
anomaly rather than all of it.

### insufficient_evidence

The behaviour is anomalous, and the file is silent or says nothing bearing on
this incident. Confidence describes how anomalous the behaviour is, not how
sure you are that you cannot tell.

**Do not** use this as a hedge on a case you could resolve. **Do** use it
whenever an explanation would be an invention. Around 30% of the hard cases in
this queue land here honestly.

## Segments change what normal means

`segment` is on the customer profile. It changes the baseline, not the standard
of evidence.

| Segment | Normal | Treat as notable |
|---|---|---|
| `student` | Low values, few countries, domestic | A single transaction in the tens of thousands |
| `retail` | Moderate, mostly domestic | Foreign spend with no prior history in that country |
| `affluent` | Large single amounts are ordinary | Device and geography anomalies, not amount alone |
| `business` | Lumpy volume, month-end clustering | Consumer cash-out categories, night-time bursts |

Always prefer the account's **own measured baseline** to the segment
stereotype. The segment is a fallback when history is thin.

## KYC level

- `full` - identity is established. A verified explanation carries more weight,
  and takeover is somewhat less likely a priori.
- anything less - be more conservative with `legitimate`, and prefer
  `insufficient_evidence` over inferring an explanation nobody wrote down.

## Account age

An account opened within the last three months, transacting heavily into
cash-out categories, is the mule shape. An account of several years with a long
clean baseline has earned more benefit of the doubt.

## What must never drive a verdict

- **Merchant category alone.** Crypto, gift card and money transfer merchants
  are used by ordinary customers.
- **Merchant overlap without lift.** A busy merchant is shared with fraud
  accounts because it is busy.
- **A shared device alone.** See the standing warning in `fraud_typologies`.
- **Rule severity.** `high` reflects the rule's design, not this case.
- **The number of rules that fired.** Four rules firing on one 40-minute
  episode is one event described four times, not four independent signals.
