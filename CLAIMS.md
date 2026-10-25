# What this suite knows

Every claim below is a sentence this repository has published, re-checked against the committed
results on both corpora and both phrasings. The point is not that they all hold - several do not,
and that is the finding. A claim that survives one corpus and not the other is a fact about a
question set; one that survives one phrasing and not the other is a fact about who is typing.

Two measurements are kept apart, because confusing them is how a claim about retrieval becomes a
claim about silence. A subject's SCORE is what the paired test pairs on - the right record in the
top three, plus a credit for declining a question with no answer. Its HITS are only the questions
that have an answer and were answered correctly. "It answers nothing" is a claim about hits.

**5 of the 13 claims hold in every setting measured.** The rest are printed beside the setting
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
| leaks-state | yes | yes | **HOLDS** |
| leanest | yes | no | **MIXED** |
| best-hard | yes | yes | yes | yes | **HOLDS** |
| best-adversarial | yes | no | no | no | **MIXED** |
| phrasing-matters | yes | yes | **HOLDS** |

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
