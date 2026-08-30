# Write-up

Models: `gpt-4.1-mini` for the specialists, `gpt-4.1-mini` for the supervisor and disposition officer.

## 1. What the sweep actually processed

Counted from the provider's own `usage_metadata` on every message, summed per
agent per account. Not an estimate.

| agent | invocations | tokens | chars produced inside | chars crossed back |
|---|---:|---:|---:|---:|
| disposition | 259 | 11,845,715 | 6,605,401 | 295,543 |
| behaviour | 267 | 4,084,010 | 2,222,904 | 475,341 |
| context | 267 | 1,583,267 | 1,040,945 | 254,985 |
| network | 267 | 1,074,737 | 660,463 | 153,562 |
| **total** | **1,060** | **18,587,729** | **10,529,713** | **1,179,431** |

- Accounts worked: **267**
- Tokens per account: **69,616**
- Estimated cost at list rates: **$8.55**

### The boundary

**88.8% of everything the specialists
produced never reached the supervisor.** Each specialist runs on a fresh message
list; its tool results - hundreds of database rows - die with that list when the
wrapper returns `result["messages"][-1]`. That single line is the entire
isolation mechanism, and the two columns above are it, measured.

## 2. What one agent holding every tool would have cost

Derived, not quoted. A single agent with all read tools does not read an
account's material once - it re-sends everything it has already seen with each
subsequent call. For an agent making `n` tool calls returning `r1..rn` tokens:

```
processed = SUM over i of ( system + tool_schemas + SUM over j<i of rj )
```

which is quadratic in the material. Measured with `tiktoken` against the real
tool outputs for 10 sampled accounts:

| | |
|---|---:|
| tool schemas re-sent on every call | 3,554 tokens |
| median source material per account | 2,945 tokens |
| median processed per account, single agent | 100,178 tokens |
| projected for the 276-account queue | **27,649,128 tokens** |
| projected cost | **$12.72** |

| measured, this system | **18,587,729 tokens** |
|---|---:|
| ratio | **1.5x** |

The estimate is deliberately charitable to the single agent: it assumes each
read tool is called exactly once per account, with no repeated calls and no
wasted turns. A real one-agent run would be worse.

### Where the cost actually went, and why the ratio is not larger

The honest reading of the table above is that this system did **not** achieve
the order-of-magnitude saving the architecture is capable of, and the reason is
worth stating plainly because it is the same failure the design exists to
prevent - just relocated.

| agent | invocations | tokens | per invocation |
|---|---:|---:|---:|
| disposition | 259 | 11,845,715 | **45,736** |
| behaviour | 267 | 4,084,010 | **15,295** |
| context | 267 | 1,583,267 | **5,929** |
| network | 267 | 1,074,737 | **4,025** |

The three reading specialists are cheap - 4,000 to 15,000 tokens each. The
**disposition officer is not**, and it accounts for roughly two thirds of the
entire sweep. It loaded 3.4 policy documents per account, and in the run
measured above it loaded them **one tool call at a time**.

Every one of those calls re-sends everything already in context. Four documents
totalling ~7,800 tokens, loaded across four turns, cost far more than 7,800
tokens - they cost the running sum. That is precisely the quadratic accumulation
described at the top of this section, occurring *inside* a specialist, with
policy documents as the accumulating material instead of database rows.

The isolation between specialists worked exactly as designed: 88% of what they
produced was discarded at the boundary. The waste is one level down, and the
boundary measurement does not surface it - which is itself a lesson about what
that metric does and does not tell you.

**The fix, now implemented:** `load_policy` takes a list, so the four documents
arrive in a single tool call and the accumulation collapses from four turns to
one. The prompt asks for them in one call and explains why. This was found by
reading the measured ledger after the sweep rather than by inspection, and the
figures above are from *before* the fix - they are reported as measured rather
than re-run, because the sweep exhausted the account's API credits.

## 3. Verdicts

| verdict | accounts | share |
|---|---:|---:|
| `fraud` | 87 | 33.7% |
| `legitimate` | 117 | 45.3% |
| `insufficient_evidence` | 54 | 20.9% |
| **total** | **258** / 276 | |

## 4. Did it read, or did it count?

### Citations, re-checked against the database

- 505 citations across 258 accounts
- **505 verified (100.0%)**

Each cited identifier is resolved back to a row, confirmed to belong to the
account it was cited on, and - for anything a human wrote - checked that the
quoted words appear in that record. Full detail in `reports/evidence_audit.md`.

Two guards run at write time, before a bad citation can land:

- **shape** - `AL0170` is an alert id; `R02` is a rule id and `ALxxxx1` is a
  placeholder. Both are refused.
- **ownership** - `AL0001` is a perfectly valid alert id that belongs to a
  different account. Refused.

### Lookalike pairs

A signature is built from the numeric facts alone - which rules fired, the
transaction-count and country buckets, whether any device was under 24 hours
old, whether anything ran at night, and the incident-to-baseline ratio.
Deliberately no case notes: the point is to group accounts the arithmetic
cannot separate.

| | |
|---|---:|
| signatures shared by two or more accounts | 62 |
| accounts inside a collision group | 214 / 276 |
| pairs we called **differently** | **95** |
| of those, pairs where both sides cite a specific record | **69** |

Run `sentinel analyse lookalikes` for the pairs themselves.

## 5. The call this system is most exposed on

**`A00881` - `fraud`, confidence `high`.**

There is no ground truth in this repository, so "most wrong" cannot be
looked up. What can be identified is the call most exposed to being wrong:
a high-confidence fraud verdict reached **without a single human-written
record to lean on**. The reasoning rests entirely on behaviour.

> Alert AL0016 for rule R04 detected a card testing pattern of 10 transactions under one hour on 2026-03-01, including many small transactions and one large electronic purchase of 104,971.26 across two countries (India known to customer, and newly seen Singapore). Device is old and established. Behaviour was highly anomalous compared to customer baseline showing much smaller amounts and usual locations. Context finds no prior explanation; a post-alert note states: "the customer disowns several small transactions but does not account for the large high-value purchase or the new country. The note states the card is in customer possession and no recent online purchases." This is a direct disowning of the flagged activity. Network analysis shows isolation, no mitigating links. The customer disowning the activity outweighs other evidence; verdict is fraud, high confidence. Given no ongoing movement, the action is monitor.

If this is wrong, it is wrong loudly - and the failure would be exactly the
one the assignment is built around: the numbers screaming while a fact
nobody wrote down would have explained them. The honest reading is that a
verdict resting only on behaviour should rarely carry high confidence, and
this is the case where that shows.

### Which specialist held the deciding evidence, and why it did not reach the supervisor

On accounts of this shape the Context Analyst is the specialist that would
settle it, and it returns `silent`. That is not a bug - the file genuinely
holds nothing. But it exposes the architecture's one real cost: **the
supervisor sees a summary, not the records.** If the Context Analyst reads a
note, decides it is not relevant, and does not quote it, the supervisor
never learns the note existed and cannot overrule that judgement. The
boundary that buys the token saving is the same boundary that makes a
specialist's omission unrecoverable.

The mitigation in place is the finding schema: specialists are required to
quote verbatim and cite note ids, and `reports/evidence_audit.md` verifies
the quotes. What it cannot detect is a record a specialist chose not to
mention at all.

## 6. Honest limitations

- **No ground truth.** Every accuracy claim in this repository is about
  internal consistency - that citations resolve, that quotes match, that
  lookalike pairs were separated with named evidence - not about being right.
- **A specialist's omission is invisible.** See section 5.
- **The single-agent figure is a model, not a measurement.** The formula and
  the measured inputs are both stated above so it can be checked.
- **Rate limits shaped the model choice.** `gpt-4.1` is capped at 30,000 tokens
  per minute on this key against 200,000 for `gpt-4.1-mini`, and one account
  costs 20,000-60,000 tokens. A two-tier configuration cannot sustain a
  276-account sweep, so both tiers run on the mini model. On the two cases with
  a known answer in the brief, mini reaches the same verdicts.

