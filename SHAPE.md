# The same question, asked two ways

Each question is put to every subject twice in one pass: as written, and as the same words with
the words that carry no meaning removed. The second form is derived mechanically, so it is the
same for everybody and has no author's vocabulary in it.

The totals are CORRECT ANSWERS, the metric the paired test in compare.py pairs on: the right
record in the top three, or silence on a question that has no answer. They are therefore not the
same as MATRIX.md's hit@3 column, which counts hits only - a subject that finds nothing but
declines all twelve unanswerable questions scores 12 here and 0 there. The easy, hard and
adversarial columns count hits only, so a +1 there and a +0 in the total is the absent band

## retrieval_corpus.json

| subject                         | as written | as keywords | change | easy | hard | adversarial |
|---|---|---|---|---|---|---|
| control 1.0.0                   | 37/60 | **41/60** | +4 | +0 | +2 | +2 |
| server-memory 1.0.0             | 12/60 | **14/60** | +2 | +0 | +0 | +2 |
| server-memory 2.0.0             | 12/60 | **14/60** | +2 | +0 | +0 | +2 |
| memento 0.7.0                   | 11/60 | **10/60** | -1 | +0 | +0 | -1 |
| memdb 1.4.0                     | 6/60 | **29/60** | +23 | +1 | +4 | +10 |
| memory-lean 1.5.0               | 26/60 | **30/60** | +4 | +0 | +0 | +4 |
| mcp-knowledge-graph 1.3.2       | 12/60 | **14/60** | +2 | +0 | +0 | +2 |
| zenbrain 0.3.0                  | 37/60 | **32/60** | -5 | +0 | -1 | -4 |
| memory-mcp-1file 0.9.2          | 43/60 | **43/60** | +0 | +0 | +1 | -1 |
| statecore-mcp 1.0.0             | 0/60 | **0/60** | +0 | +0 | +0 | +0 |
| mcp-duckdb-memory-server 1.1.10 | 22/60 | **22/60** | +0 | -2 | +1 | +1 |

Rank correlation between the two phrasings: **rho = 0.86** over 11 subjects. 8 of 11 subjects
score differently depending on how the question is put.

Questions that change outcome between the two phrasings, first twelve:

| subject | band | question | right as written | right as keywords |
|---|---|---|---|---|
| control 1.0.0 | hard | how long are backups kept after they are taken | no | yes |
| control 1.0.0 | hard | where is customer data physically held | no | yes |
| control 1.0.0 | adversarial | how long after the deployment key rotates may the old one still be used | no | yes |
| control 1.0.0 | adversarial | what happens after three failed payments | no | yes |
| server-memory 1.0.0 | adversarial | how long does the refresh token last | no | yes |
| server-memory 1.0.0 | adversarial | what is the tunnel mtu | no | yes |
| server-memory 2.0.0 | adversarial | how long does the refresh token last | no | yes |
| server-memory 2.0.0 | adversarial | what is the tunnel mtu | no | yes |
| memento 0.7.0 | easy | corpus 105 cases | no | yes |
| memento 0.7.0 | adversarial | how old may the oldest backup copy become | no | yes |
| memento 0.7.0 | adversarial | which git behaviour hides the carriage returns | yes | no |
| memento 0.7.0 | easy | shared runner build eleven minutes | yes | no |

59 question outcomes in total change with the phrasing alone - no subject changed,
no store changed, no ranking changed, only the words used to ask.

## retrieval_corpus_b.json

| subject                         | as written | as keywords | change | easy | hard | adversarial |
|---|---|---|---|---|---|---|
| control 1.0.0                   | 44/60 | **44/60** | +0 | +0 | -1 | +1 |
| server-memory 1.0.0             | 12/60 | **14/60** | +2 | +1 | +0 | +1 |
| server-memory 2.0.0             | 12/60 | **14/60** | +2 | +1 | +0 | +1 |
| memento 0.7.0                   | 19/60 | **17/60** | -2 | -2 | -2 | +2 |
| memdb 1.4.0                     | 2/60 | **16/60** | +14 | +2 | +0 | +1 |
| memory-lean 1.5.0               | 12/60 | **28/60** | +16 | +11 | +0 | +5 |
| mcp-knowledge-graph 1.3.2       | 12/60 | **14/60** | +2 | +1 | +0 | +1 |
| zenbrain 0.3.0                  | 33/60 | **34/60** | +1 | -1 | +2 | +0 |
| memory-mcp-1file 0.9.2          | 45/60 | **37/60** | -8 | +0 | -7 | -1 |
| statecore-mcp 1.0.0             | 12/60 | **12/60** | +0 | +0 | +0 | +0 |
| mcp-duckdb-memory-server 1.1.10 | 25/60 | **29/60** | +4 | +3 | +0 | +1 |

Rank correlation between the two phrasings: **rho = 0.81** over 11 subjects. 9 of 11 subjects
score differently depending on how the question is put.

Questions that change outcome between the two phrasings, first twelve:

| subject | band | question | right as written | right as keywords |
|---|---|---|---|---|
| control 1.0.0 | hard | What must a conductor know before working a road unsupervised? | yes | no |
| control 1.0.0 | adversarial | Which depot site holds the simulator used to train drivers? | no | yes |
| server-memory 1.0.0 | easy | Which sets are the oldest working units? | no | yes |
| server-memory 1.0.0 | adversarial | How long is the Kestrel Line? | no | yes |
| server-memory 2.0.0 | easy | Which sets are the oldest working units? | no | yes |
| server-memory 2.0.0 | adversarial | How long is the Kestrel Line? | no | yes |
| memento 0.7.0 | easy | When does Saltmarsh depot open each day? | yes | no |
| memento 0.7.0 | easy | How many conductors work a train formed of more than four vehicles? | yes | no |
| memento 0.7.0 | hard | How much time off must a crew have before going back on duty? | yes | no |
| memento 0.7.0 | hard | When are the underframes stripped and rebuilt? | yes | no |
| memento 0.7.0 | adversarial | Where does the Marlbrook Line take its power from? | no | yes |
| memento 0.7.0 | adversarial | How much is a day ticket for unlimited rides on the Ridgeway Line? | no | yes |

69 question outcomes in total change with the phrasing alone - no subject changed,
no store changed, no ranking changed, only the words used to ask.

