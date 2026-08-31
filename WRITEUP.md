# Write-up

Generated from recorded results, 31 August 2026.

## What the sweep processed

| agent | model | input | output | cost |
|---|---|---:|---:|---:|
| behaviour | `gpt-4.1-mini` | 2,218,977 | 191,762 | $1.19 |
| context | `gpt-4.1-mini` | 1,874,692 | 142,051 | $0.98 |
| disposition | `gpt-4.1-mini` | 6,225,179 | 211,192 | $2.83 |
| network | `gpt-4.1-mini` | 1,040,987 | 63,604 | $0.52 |
| **total** | | **11,359,835** | **608,609** | **$5.52** |

Measured over **276 accounts**: 43,364 tokens and $0.0200 per account.

These are metered figures, taken from `usage_metadata` on every model response, not an estimate. Four specialists spend roughly 10,000 tokens on system prompts alone before reading a single row, so any figure much below that is measuring something other than a system that reads the file.

## The single-agent comparison

The isolated contexts hold this much content per account:

| context | content | model calls |
|---|---:|---:|
| behaviour | 3,054 tokens | 4.3 |
| context | 3,216 tokens | 3.2 |
| disposition | 9,155 tokens | 3.9 |
| network | 1,691 tokens | 3.5 |

One agent holding all 17 tools would carry all 17,116 tokens in a **single** message list and re-process the lot on every one of its 15 model calls.

| | per account | over 276 accounts |
|---|---:|---:|
| Isolated specialists | 41,159 | 11,359,835 |
| One flat agent | 135,873 | 37,500,927 |
| **Multiplier** | **3.3x** | |

The difference is entirely cross terms. The behaviour analyst's tables of transactions get re-processed on every later call about case notes, devices and disposition, and the other way round.

## The isolation boundary, measured

- produced inside the specialists: **45,439,340 characters**
- crossed back to the supervisor: **1,711,348 characters**
- discarded: **96.2%**

Each specialist runs on a fresh message list inside one `.invoke()`. Only `result["messages"][-1]` is returned; everything else — every table of rows, every policy document, every intermediate step — is garbage-collected when that call returns. The supervisor's model never processes a database row.

> The produced figure is derived from metered input tokens at roughly four characters per token, so it includes each specialist's system prompt as well as the rows it read. The direction is unambiguous; the exact ratio is an approximation and is stated as one.

## Policy loaded on demand

| document | times loaded |
|---|---:|
| `narrative_reading` | 387 |
| `evidence_standards` | 289 |
| `escalation_matrix` | 289 |
| `risk_appetite` | 2 |

Level 1 of the policy corpus — names and descriptions — is 1,117 characters and sits in every system prompt. Level 2, the 31,211-character bodies, is loaded only when an agent asks. **96.5% of the corpus is absent from a prompt until it is needed**, and the table above is the ledger proving loading really was on demand.

## What the system decided

| verdict | accounts |
|---|---:|
| `fraud` | 92 |
| `insufficient_evidence` | 28 |
| `legitimate` | 156 |

## The case it got most wrong

_See CASES.md for the full trail. Fill this in after reviewing the sweep: name the account, say which specialist saw the deciding evidence, and why it did not reach the supervisor._

