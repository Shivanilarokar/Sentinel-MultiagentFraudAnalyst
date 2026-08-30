# Evidence audit

Every citation on every recorded disposition, resolved back to a row in
`data/sentinel.db`. Three questions per citation: does the identifier exist,
does it belong to the account it was cited on, and - for case notes, disputes
and prior cases - are the quoted words actually in that record?

| | |
|---|---:|
| accounts audited | 8 |
| citations checked | 13 |
| citations verified | 13 |
| pass rate | 100.0% |

**No citation failed.** Every identifier exists, belongs to the account it
was cited on, and every quote appears verbatim in the record it names.

---

## Per-account detail

| account | verdict | citations | failures |
|---|---|---:|---:|
| `A00000` | insufficient_evidence | 1 | 0 |
| `A00008` | fraud | 1 | 0 |
| `A00013` | legitimate | 2 | 0 |
| `A00022` | legitimate | 3 | 0 |
| `A00025` | insufficient_evidence | 0 | 0 |
| `A00031` | legitimate | 4 | 0 |
| `A00032` | legitimate | 1 | 0 |
| `A00037` | insufficient_evidence | 1 | 0 |
