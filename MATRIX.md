# Measured subjects

| subject | isolation | ack_readback | restart | findable | foreign_field | foreign_record | concurrent | large_record | ceiling |
|---|---|---|---|---|---|---|---|---|---|
| control 1.0.0 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 60s |
| server-memory 1.0.0 | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | PASS | 60s |
| server-memory 2.0.0 | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | PASS | 60s |
| memento 0.7.0 | PASS | PASS | PASS | FAIL | PASS | PASS | PASS | FAIL | 180s |
| memdb 1.4.0 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 60s |
| memory-lean 1.5.0 | PASS | PASS | PASS | PASS | FAIL | FAIL | PASS | PASS | 60s |
| mcp-knowledge-graph 1.3.2 | PASS | PASS | PASS | PASS | PASS | FAIL | FAIL | PASS | 90s |
| zenbrain 0.3.0 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 60s |
| memory-mcp-1file 0.9.2 | FAIL | (PASS) | (PASS) | (PASS) | (UNKNOWN) | (UNKNOWN) | (FAIL) | (UNKNOWN) | 60s |
| statecore-mcp 1.0.0 | PASS | PASS | PASS | FAIL | PASS | PASS | FAIL | UNKNOWN | 60s |
| mcp-duckdb-memory-server 1.1.10 | PASS | PASS | PASS | PASS | UNKNOWN | UNKNOWN | FAIL | UNKNOWN | 90s |

Cells in parentheses belong to a subject that failed `isolation`; its other verdicts describe leaked state.

## Retrieval: a score, not a verdict

72 records, 60 questions, cold start. hit@3 per band; "easy" shares wording with its answer, "hard" is a paraphrase, "adversarial" has a near duplicate competing. "noans" is questions with no answer in the store that were answered anyway.

| subject | easy h3 | hard h3 | adversarial h3 | all h1 | all h3 | no-answer answered | runs | h3 95% |
|---|---|---|---|---|---|---|---|---|
| control 1.0.0 | 16/16 | 0/16 | 9/16 | 25/60 | 25/60 | 0/12 | 25-25 | 18-33 |
| server-memory 1.0.0 | 0/16 | 0/16 | 0/16 | 0/60 | 0/60 | 0/12 | 0-0 | 0-4 |
| server-memory 2.0.0 | 0/16 | 0/16 | 0/16 | 0/60 | 0/60 | 0/12 | 0-0 | 0-4 |
| memento 0.7.0 | 3/16 | 3/16 | 5/16 | 3/60 | 11/60 | 12/12 | 11-11 | 6-18 |
| memdb 1.4.0 | 6/16 | 0/16 | 0/16 | 0/60 | 6/60 | 12/12 | 6-6 | 3-12 |
| memory-lean 1.5.0 | 14/16 | 0/16 | 0/16 | 14/60 | 14/60 | 0/12 | 14-14 | 9-21 |
| mcp-knowledge-graph 1.3.2 | 0/16 | 0/16 | 0/16 | 0/60 | 0/60 | 0/12 | 0-0 | 0-4 |
| zenbrain 0.3.0 | 16/16 | 7/16 | 14/16 | 31/60 | 37/60 | 12/12 | 37-37 | 29-44 |
| memory-mcp-1file 0.9.2 | 16/16 | 13/16 | 14/16 | 41/60 | 43/60 | 12/12 | 43-43 | 36-49 |
| statecore-mcp 1.0.0 | 0/16 | 0/16 | 0/16 | 0/60 | 0/60 | 12/12 | 0-0 | 0-4 |
| mcp-duckdb-memory-server 1.1.10 | 8/16 | 0/16 | 2/16 | 10/60 | 10/60 | 0/12 | 10-10 | 6-17 |

The last column is the 95% Wilson interval for all-band hit@3, in counts. Two subjects whose intervals overlap are not separated by this corpus.

## Cost

Measured once per subject with nothing else running. "resp" is the median bytes returned for one question and "amp" is that divided by the answer's own size. A subject that returns nothing is cheap for the wrong reason - read this table with the retrieval one.

| subject | startup | first write | write p50 | search p50 | resp bytes | amp | store B/rec | vary |
|---|---|---|---|---|---|---|---|---|
| control 1.0.0 | 0.23s | 0.01s | 0.009s | 0.001s | 4175 | x72 | 140 | 0% |
| server-memory 1.0.0 | 0.89s | 0.05s | 0.021s | 0.005s | 39 | x1 | 150 | 62% |
| server-memory 2.0.0 | 0.80s | 0.03s | 0.013s | 0.005s | 39 | x1 | 150 | 69% |
| memento 0.7.0 | 1.42s | 4.54s | 0.111s | 0.045s | 1497 | x26 | 0 | 293% |
| memdb 1.4.0 | 0.42s | 0.01s | 0.001s | 0.002s | 1027 | x18 | 42024 | 0% |
| memory-lean 1.5.0 | 0.12s | 0.01s | 0.004s | 0.002s | 164 | x3 | 150 | 0% |
| mcp-knowledge-graph 1.3.2 | 0.13s | 0.01s | 0.005s | 0.003s | 39 | x1 | 150 | 0% |
| zenbrain 0.3.0 | 0.43s | 0.01s | 0.001s | 0.002s | 663 | x11 | 21424 | 0% |
| memory-mcp-1file 0.9.2 | 0.51s | 1.56s | 0.036s | 0.055s | 1969 | x34 | - | 11% |
| statecore-mcp 1.0.0 | 0.36s | 0.02s | 0.005s | 0.002s | 5710 | x98 | 19226 | 5% |
| mcp-duckdb-memory-server 1.1.10 | 0.33s | 0.14s | 0.010s | 0.005s | 210 | x4 | - | 25% |

`vary` is how far the worst steady-state measurement moved across 3 passes, as a fraction of its own median: first write, write, search and response bytes, with timings under 20 ms excluded because a ratio of millisecond noise is not a measurement. Absolute ranges and the noisier startup and restart figures are in `results/*-cost.json`.
