# What this suite knows

Every claim below is a sentence this repository has published, re-checked against the committed
results on both corpora and both phrasings. The point is not that they all hold - several do not,
and that is the finding. A claim that survives one corpus and not the other is a fact about a
question set; one that survives one phrasing and not the other is a fact about who is typing.

Two measurements are kept apart, because confusing them is how a claim about retrieval becomes a
claim about silence. A subject's SCORE is what the paired test pairs on - the right record in the
top three, plus a credit for declining a question with no answer. Its HITS are only the questions
that have an answer and were answered correctly. "It answers nothing" is a claim about hits.

**7 of the 30 claims hold in every setting measured.** The rest are printed beside the setting
that breaks them, because that setting is the claim's real scope.

| claim | A written | A keywords | B written | B keywords | status |
|---|---|---|---|---|---|
| most-hits | yes | yes | yes | yes | **HOLDS** |
| leads-runner | no | yes | yes | no | **MIXED** |
| beats-control | no | no | no | no | **FAILS** |
| reference-silent | yes | no | yes | no | **ONE PHRASING** |
| small-servers-silent | yes | no | yes | no | **ONE PHRASING** |
| memento-speaks | yes | yes | yes | yes | **HOLDS** |
| can-forget | no | no | **FAILS** |
| verbatim-all | no | no | **FAILS** |
| scale-ceiling | yes | yes | yes | yes | **HOLDS** |
| floor-not-zero | yes | yes | yes | yes | **HOLDS** |
| silence-scores-better | yes | yes | yes | no | **MIXED** |
| absent-band-flat | yes | no | yes | yes | **MIXED** |
| metrics-agree | no | no | no | no | **FAILS** |
| search-is-flat | no | no | **FAILS** |
| leaks-state | yes | yes | **HOLDS** |
| leanest | yes | no | **MIXED** |
| best-hard | yes | yes | yes | yes | **HOLDS** |
| best-adversarial | yes | no | no | no | **MIXED** |
| phrasing-matters | yes | yes | **HOLDS** |
| leader-is-steady | no | no | **FAILS** |
| tie-means-same | no | no | **FAILS** |
| corpora-agree | no | no | **FAILS** |
| agent-agrees-with-score | no | no | **FAILS** |
| real-corpus-agrees | no | no | **FAILS** |
| ranking-survives-paraphrase | no | no | **FAILS** |
| near-end-separates | no | no | **FAILS** |
| plural-is-free | no | no | **FAILS** |
| silent-everywhere | no | no | **FAILS** |
| score-sees-ordering | no | no | **FAILS** |
| score-prefers-recalcitrance | no | no | **FAILS** |

## Each claim, with what it rests on

**most-hits** - memory-mcp-1file answers more answerable questions than any other subject here. *HOLDS*
  - A written: true (42/48, alone at the top of 11 subjects)
  - A keywords: true (42/48, alone at the top of 11 subjects)
  - B written: true (45/48, alone at the top of 11 subjects)
  - B keywords: true (37/48, alone at the top of 11 subjects)

**leads-runner** - memory-mcp-1file is better than zenbrain by the paired test. *MIXED*
  - A written: false (p = 0.5811 on 8-5 discordant questions)
  - A keywords: true (p = 0.0225 on 11-2 discordant questions)
  - B written: true (p = 0.0005 on 12-0 discordant questions)
  - B keywords: false (p = 0.4531 on 5-2 discordant questions)

**beats-control** - zenbrain is better than the positive control by the paired test. *FAILS*
  - A written: false (p = 0.7011 on 15-12 discordant questions)
  - A keywords: false (p = 0.0490 on 4-13 discordant questions)
  - B written: false (p = 0.0074 on 2-13 discordant questions)
  - B keywords: false (p = 0.0309 on 4-14 discordant questions)

**reference-silent** - @modelcontextprotocol/server-memory answers no answerable question at all. *ONE PHRASING*
  - A written: true (0 of 48 answerable questions answered)
  - A keywords: false (2 of 48 answerable questions answered)
  - B written: true (0 of 48 answerable questions answered)
  - B keywords: false (2 of 48 answerable questions answered)

**small-servers-silent** - the smallest servers here find nothing at all. *ONE PHRASING*
  - A written: true (mcp-knowledge-graph 1.3.2 0, server-memory 1.0.0 0, server-memory 2.0.0 0, statecore-mcp 1.0.0 0)
  - A keywords: false (mcp-knowledge-graph 1.3.2 2, server-memory 1.0.0 2, server-memory 2.0.0 2, statecore-mcp 1.0.0 0)
  - B written: true (mcp-knowledge-graph 1.3.2 0, server-memory 1.0.0 0, server-memory 2.0.0 0, statecore-mcp 1.0.0 0)
  - B keywords: false (mcp-knowledge-graph 1.3.2 2, server-memory 1.0.0 2, server-memory 2.0.0 2, statecore-mcp 1.0.0 0)

**memento-speaks** - memento answers every unanswerable question. *HOLDS*
  - A written: true (12 of 12 unanswerable questions answered)
  - A keywords: true (12 of 12 unanswerable questions answered)
  - B written: true (12 of 12 unanswerable questions answered)
  - B keywords: true (12 of 12 unanswerable questions answered)

**can-forget** - every subject can be asked to forget a record, and forgets it. *FAILS*
  - A written: false (5 cannot be asked (memdb, zenbrain, memory-mcp-1file, statecore-mcp, mcp-duckdb-memory-server); 0 were asked and did not forget (none))
  - B written: false (5 cannot be asked (memdb, zenbrain, memory-mcp-1file, statecore-mcp, mcp-duckdb-memory-server); 0 were asked and did not forget (none))

**verbatim-all** - every subject returns a record exactly as it was written. *FAILS*
  - A written: false (0 altered it (none); 3 could not be compared (memory-mcp-1file, statecore-mcp, mcp-duckdb-memory-server))
  - B written: false (0 altered it (none); 3 could not be compared (memory-mcp-1file, statecore-mcp, mcp-duckdb-memory-server))

**scale-ceiling** - the retrieval score's maximum is reachable by something. *HOLDS*
  - A written: true (an oracle returning the corpus's own answers scored 60 of 60)
  - A keywords: true (an oracle returning the corpus's own answers scored 60 of 60)
  - B written: true (an oracle returning the corpus's own answers scored 60 of 60)
  - B keywords: true (an oracle returning the corpus's own answers scored 60 of 60)

**floor-not-zero** - a subject that answers nothing still scores the unanswerable questions. *HOLDS*
  - A written: true (a subject that never answers scored 12 of 60, the 12 questions with no answer)
  - A keywords: true (a subject that never answers scored 12 of 60, the 12 questions with no answer)
  - B written: true (a subject that never answers scored 12 of 60, the 12 questions with no answer)
  - B keywords: true (a subject that never answers scored 12 of 60, the 12 questions with no answer)

**silence-scores-better** - at least one subject scores worse than a memory that answers nothing. *MIXED*
  - A written: true (2 subject(s) below the 12 that answering nothing scores (memdb 6, statecore-mcp 0))
  - A keywords: true (1 subject(s) below the 12 that answering nothing scores (statecore-mcp 0))
  - B written: true (1 subject(s) below the 12 that answering nothing scores (memdb 2))
  - B keywords: false (0 subject(s) below the 12 that answering nothing scores)

**absent-band-flat** - the unanswerable questions give the stronger subjects no advantage. *MIXED*
  - A written: true (the unanswerable band's discrimination is +0.00, on 12 questions worth 12 of the score's 60 points)
  - A keywords: false (the unanswerable band's discrimination is +0.13, on 12 questions worth 12 of the score's 60 points)
  - B written: true (the unanswerable band's discrimination is -0.22, on 12 questions worth 12 of the score's 60 points)
  - B keywords: true (the unanswerable band's discrimination is -0.40, on 12 questions worth 12 of the score's 60 points)

**metrics-agree** - the score and the answerable-only count rank the top of the table the same way. *FAILS*
  - A written: false (2 of 2 top-of-table pairs get different verdicts from the two metrics: memory-mcp-1file vs control (score tied, hits separated); zenbrain vs control (score tied, hits separated))
  - A keywords: false (2 of 2 top-of-table pairs get different verdicts from the two metrics: memory-mcp-1file vs control (score tied, hits separated); zenbrain vs control (score separated, hits tied))
  - B written: false (2 of 2 top-of-table pairs get different verdicts from the two metrics: memory-mcp-1file vs control (score tied, hits separated); zenbrain vs control (score separated, hits tied))
  - B keywords: false (1 of 2 top-of-table pairs get different verdicts from the two metrics: zenbrain vs control (score separated, hits tied))

**search-is-flat** - a search costs the same on a small store and a large one. *FAILS*
  - A written: false (10 subject(s) cost more to search at 3000 records than at 5 (control x60, mcp-duckdb-memory-server x54, mcp-knowledge-graph x3, memdb x25, memento x87, memory-lean x4, server-memory x3, server-memory x3, statecore-mcp x6, zenbrain x5))
  - B written: false (10 subject(s) cost more to search at 3000 records than at 5 (control x60, mcp-duckdb-memory-server x54, mcp-knowledge-graph x3, memdb x25, memento x87, memory-lean x4, server-memory x3, server-memory x3, statecore-mcp x6, zenbrain x5))

**leaks-state** - memory-mcp-1file leaks state between stores and is out of scope. *HOLDS*
  - A written: true (isolation FAIL)
  - B written: true (isolation FAIL)

**leanest** - memory-lean returns fewer bytes per question than any subject that answers anything. *MIXED*
  - A written: true (164 bytes per question for memory-lean 1.5.0)
  - B written: false (210 bytes per question for mcp-duckdb-memory-server 1.1.10 - memory-lean is cheaper at 164 but answers nothing on this corpus, so it does not qualify)

**best-hard** - memory-mcp-1file leads the hard band. *HOLDS*
  - A written: true (12/16, alone at the top of 11 subjects)
  - A keywords: true (13/16, alone at the top of 11 subjects)
  - B written: true (13/16, alone at the top of 11 subjects)
  - B keywords: true (6/16, alone at the top of 11 subjects)

**best-adversarial** - zenbrain leads the adversarial band. *MIXED*
  - A written: true (16/16, alone at the top of 11 subjects)
  - A keywords: false (13/16, tied with control 1.0.0, memory-mcp-1file 0.9.2)
  - B written: false (15/16, best is 16)
  - B keywords: false (15/16, best is 16)

**phrasing-matters** - one subject's answer count moves by ten or more on phrasing alone. *HOLDS*
  - A written: true (memdb 1.4.0: 6 as written, 19 as keywords)
  - B written: true (memory-lean 1.5.0: 0 as written, 16 as keywords)

**leader-is-steady** - one subject leads the retrieval table, however the table is ordered. *FAILS*
  - A written: false (3 subjects lead at least one of the 24 rulers, and memory-mcp-1file 0.9.2 leads the most (15 of 24))
  - B written: false (3 subjects lead at least one of the 24 rulers, and memory-mcp-1file 0.9.2 leads the most (15 of 24))

**tie-means-same** - two subjects a ruler cannot separate answer the questions the same way. *FAILS*
  - A written: false (the widest pair any ruler cannot separate disagreed on 41 of 60 questions (mcp-duckdb-memory-server 1.1.10 vs memory-mcp-1file 0.9.2, corpus B written top))
  - B written: false (the widest pair any ruler cannot separate disagreed on 41 of 60 questions (mcp-duckdb-memory-server 1.1.10 vs memory-mcp-1file 0.9.2, corpus B written top))

**corpora-agree** - every pair of corpora here reaches the same verdict on every pair of subjects. *FAILS*
  - A written: false (verdicts that differ between corpora: A vs B 16 of 55, A vs C 16 of 55, B vs C 0 of 55)
  - B written: false (verdicts that differ between corpora: A vs B 16 of 55, A vs C 16 of 55, B vs C 0 of 55)

**agent-agrees-with-score** - the ranking a caller with a token budget sees is the one this repository publishes. *FAILS*
  - A written: false (1 of 3 corpora put a different subject on top when the metric is what a caller reads: B (score memory-mcp-1file, agent control))
  - B written: false (1 of 3 corpora put a different subject on top when the metric is what a caller reads: B (score memory-mcp-1file, agent control))

**real-corpus-agrees** - the leader on a corpus with no author is the leader on the corpora written by hand. *FAILS*
  - A written: false (the leader on real text is control, and 1 of the three authored corpora agree (not A, B))
  - B written: false (the leader on real text is control, and 1 of the three authored corpora agree (not A, B))

**ranking-survives-paraphrase** - the subject that answers the most verbatim questions also answers the most paraphrased ones. *FAILS*
  - A written: false (8 subject(s) tie at the ceiling on the verbatim questions (24 of 24) and zenbrain is first when two words survive (21 of 24))
  - B written: false (8 subject(s) tie at the ceiling on the verbatim questions (24 of 24) and zenbrain is first when two words survive (21 of 24))

**near-end-separates** - asking a record its own words back separates the subjects better than paraphrasing it. *FAILS*
  - A written: false (the verbatim band separates 26 of 55 pairs and the half-paraphrased band 38)
  - B written: false (the verbatim band separates 26 of 55 pairs and the half-paraphrased band 38)

**plural-is-free** - a memory that answers a record's own words answers the plural of them too. *FAILS*
  - A written: false (5 of 11 subjects lose more than half of their answers when the question pluralises the record's words (control 24 to 9, mcp-knowledge-graph 24 to 0, memory-lean 24 to 0, server-memory 24 to 0, server-memory 24 to 0))
  - B written: false (5 of 11 subjects lose more than half of their answers when the question pluralises the record's words (control 24 to 9, mcp-knowledge-graph 24 to 0, memory-lean 24 to 0, server-memory 24 to 0, server-memory 24 to 0))

**silent-everywhere** - the subjects that answer nothing on the authored corpora answer nothing on real text either. *FAILS*
  - A written: false (1 of 4 still answer nothing on real text (server-memory 33, server-memory 33, mcp-knowledge-graph 33 of 48 answered))
  - B written: false (1 of 4 still answer nothing on real text (server-memory 33, server-memory 33, mcp-knowledge-graph 33 of 48 answered))

**score-sees-ordering** - the retrieval score changes when a search returns its worst match first. *FAILS*
  - A written: false (reversing the result list moved the score by 0 and the hit count by 0 (score 37 against 37))
  - B written: false (reversing the result list moved the score by 0 and the hit count by 0 (score 37 against 37))

**score-prefers-recalcitrance** - a search that accepts one shared word scores no better than one that requires half. *FAILS*
  - A written: false (accepting one shared word scored 43 against 37, a gain of 6 for answering worse)
  - B written: false (accepting one shared word scored 43 against 37, a gain of 6 for answering worse)
