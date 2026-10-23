# Replication on a corpus written blind

11 subjects, the same conformance harness, two question sets of 72 records each. Corpus B was
written by an author that never saw corpus A, the matrix or any result. The two totals below
are NOT comparable as numbers - they count answers to different questions. The order is.

| subject                         | A hit@3 | B hit@3 | B easy | B hard | B adversarial | B no-answer spoken |
|---|---|---|---|---|---|---|
| control 1.0.0                   | 25/60 | **32/60** | 16/16 | 1/16 | 15/16 | 0/12 |
| server-memory 1.0.0             | 0/60 | **0/60** | 0/16 | 0/16 | 0/16 | 0/12 |
| server-memory 2.0.0             | 0/60 | **0/60** | 0/16 | 0/16 | 0/16 | 0/12 |
| memento 0.7.0                   | 11/60 | **19/60** | 9/16 | 6/16 | 4/16 | 12/12 |
| memdb 1.4.0                     | 6/60 | **1/60** | 0/16 | 1/16 | 0/16 | 11/12 |
| memory-lean 1.5.0               | 14/60 | **0/60** | 0/16 | 0/16 | 0/16 | 0/12 |
| mcp-knowledge-graph 1.3.2       | 0/60 | **0/60** | 0/16 | 0/16 | 0/16 | 0/12 |
| zenbrain 0.3.0                  | 37/60 | **33/60** | 16/16 | 2/16 | 15/16 | 12/12 |
| memory-mcp-1file 0.9.2          | 43/60 | **45/60** | 16/16 | 13/16 | 16/16 | 12/12 |
| statecore-mcp 1.0.0             | 0/60 | **0/60** | 0/16 | 0/16 | 0/16 | 0/12 |
| mcp-duckdb-memory-server 1.1.10 | 10/60 | **13/60** | 9/16 | 0/16 | 4/16 | 0/12 |

Rank correlation between the two orderings: **rho = 0.86** over 11 subjects.

| subject                         | rank A | rank B | move |
|---|---|---|---|
| control 1.0.0                   | 3 | 3 | same |
| server-memory 1.0.0             | 8 | 7 | +1 |
| server-memory 2.0.0             | 9 | 8 | +1 |
| memento 0.7.0                   | 5 | 4 | +1 |
| memdb 1.4.0                     | 7 | 6 | +1 |
| memory-lean 1.5.0               | 4 | 9 | -5 |
| mcp-knowledge-graph 1.3.2       | 10 | 10 | same |
| zenbrain 0.3.0                  | 2 | 2 | same |
| memory-mcp-1file 0.9.2          | 1 | 1 | same |
| statecore-mcp 1.0.0             | 11 | 11 | same |
| mcp-duckdb-memory-server 1.1.10 | 6 | 5 | +1 |

## Every neighbouring pair, tested on both corpora

Exact McNemar on the questions where the two subjects disagree; the split is questions the
first subject answered and the second did not. A question counts as answered correctly the
same way compare.py counts it: the right record in the top three, and on a question with no
answer, silence. sep is p < 0.05.

| pair | corpus A | corpus B | same conclusion |
|---|---|---|---|
| memory-mcp-1file 0.9.2 / zenbrain 0.3.0 | 0.180 (10-4) not | 0.000 (12-0) sep | **no** |
| zenbrain 0.3.0 / control 1.0.0 | 1.000 (13-13) not | 0.007 (2-13) sep | **no** |
| control 1.0.0 / memory-lean 1.5.0 | 0.001 (11-0) sep | 0.000 (32-0) sep | yes |
| memory-lean 1.5.0 / memento 0.7.0 | 0.011 (23-8) sep | 0.281 (12-19) not | **no** |
| memento 0.7.0 / mcp-duckdb-memory-server 1.1.10 | 0.071 (10-21) not | 0.362 (12-18) not | yes |
| mcp-duckdb-memory-server 1.1.10 / memdb 1.4.0 | 0.000 (18-2) sep | 0.000 (24-1) sep | yes |
| memdb 1.4.0 / server-memory 1.0.0 | 0.238 (6-12) not | 0.006 (1-11) sep | **no** |
| server-memory 1.0.0 / server-memory 2.0.0 | 1.000 (0-0) not | 1.000 (0-0) not | yes |
| server-memory 2.0.0 / mcp-knowledge-graph 1.3.2 | 1.000 (0-0) not | 1.000 (0-0) not | yes |
| mcp-knowledge-graph 1.3.2 / statecore-mcp 1.0.0 | 0.000 (12-0) sep | 1.000 (0-0) not | **no** |

5 of 10 neighbouring pairs reach the same conclusion on both corpora.

A pair that changes conclusion is the corpus talking, not the subjects. A separation
that holds on only one of two question sets is conditional on that question set, and
should be read that way until a third corpus agrees.
