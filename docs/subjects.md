# Every subject, measured

Moved here from `README.md` unchanged, so that page can stay an argument rather
than an archive. The numbers are the same numbers; the generated reports they quote are still
at the top of the repository.

## The subjects measured so far

```
$ python matrix.py

subject                         isol     ack      verb     restart  forget   find     field    record   conc     large    ceil
------------------------------------------------------------------------------------------------------------------------------
control 1.0.0                   PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS      60s
server-memory 1.0.0             PASS     PASS     PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS      60s
server-memory 2.0.0             PASS     PASS     PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS      60s
memento 0.7.0                   PASS     PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS     FAIL     180s
memdb 1.4.0                     PASS     PASS     PASS     PASS     UNKNOWN  PASS     PASS     PASS     PASS     PASS      60s
memory-lean 1.5.0               PASS     PASS     PASS     PASS     PASS     PASS     FAIL     FAIL     PASS     PASS      60s
mcp-knowledge-graph 1.3.2       PASS     PASS     PASS     PASS     PASS     PASS     PASS     FAIL     FAIL     PASS      90s
zenbrain 0.3.0                  PASS     PASS     PASS     PASS     UNKNOWN  PASS     PASS     PASS     PASS     PASS      60s
memory-mcp-1file 0.9.2          FAIL     (PASS)   (UNKNOWN)  (PASS)   (UNKNOWN)  (PASS)   (UNKNOWN)  (UNKNOWN)  (FAIL)   (UNKNOWN)   60s
statecore-mcp 1.0.0             PASS     PASS     UNKNOWN  PASS     UNKNOWN  FAIL     PASS     PASS     FAIL     UNKNOWN   60s
mcp-duckdb-memory-server 1.1.10 PASS     PASS     UNKNOWN  PASS     UNKNOWN  PASS     UNKNOWN  UNKNOWN  FAIL     UNKNOWN   90s

(x) verdict qualified by a failed isolation precondition - not publishable on its own
ceil is the per-call ceiling each subject was given; a verdict measured at one ceiling
does not transfer to another, and memento is the proof: same machine, PASS at 180s and
FAIL at 60s on the same probe.
1 subject(s) out of scope, 10 measured

retrieval, cold start, 72 records and 60 questions - a score, not a verdict. hit@3 per
per band - easy shares wording with the answer, hard is a paraphrase, adversarial has a
near duplicate competing. 'noans' is questions with no answer that were answered anyway;
0 is right.
subject                         easy    hard    adver   all h1   all h3   kw h3    change   noans   runs      95%
-----------------------------------------------------------------------------------------------------------------
control 1.0.0                   16/16   0/16    9/16    25/60    25/60    30/60    +5       0/12    25-25     18-33
server-memory 1.0.0             0/16    0/16    0/16    0/60     0/60     2/60     +2       0/12    0-0       0-4
server-memory 2.0.0             0/16    0/16    0/16    0/60     0/60     2/60     +2       0/12    0-0       0-4
memento 0.7.0                   3/16    4/16    7/16    6/60     14/60    12/60    -2       12/12   14-14     9-21
memdb 1.4.0                     6/16    0/16    0/16    0/60     6/60     19/60    +13      12/12   6-6       3-12
memory-lean 1.5.0               14/16   0/16    0/16    14/60    14/60    18/60    +4       0/12    14-14     9-21
mcp-knowledge-graph 1.3.2       0/16    0/16    0/16    0/60     0/60     2/60     +2       0/12    0-0       0-4
zenbrain 0.3.0                  16/16   8/16    16/16   33/60    40/60    33/60    -7       12/12   40-40     32-46
memory-mcp-1file 0.9.2          16/16   12/16   14/16   39/60    42/60    42/60    +0       11/12   42-42     34-48
statecore-mcp 1.0.0             0/16    0/16    0/16    0/60     0/60     0/60     +0       12/12   0-0       0-4
mcp-duckdb-memory-server 1.1.10 8/16    1/16    3/16    12/60    12/60    13/60    +1       0/12    12-12     7-19

'runs' is the min-max of the same experiment repeated 3 times; '95%' is the Wilson
interval for the majority result, in counts. The first covers repeating the experiment,
the second covers asking a different set of 60 questions. They are not the same error.
'kw h3' is the same 60 questions asked again with the words that carry no meaning removed:
memdb 1.4.0 is 6/60 one way and 19/60 the other on the same corpus, so a score quoted without
its phrasing is half a measurement. Per-band detail is in SHAPE.md.

cost, measured once per subject with nothing else running. 'resp' is the median bytes the
server sends back for one question and 'amp' is that divided by the answer's own size - a
system that answers by returning the whole store shows up here. A subject that returns
nothing is cheap for the wrong reason, so read this table with the one above it.
subject                         startup  lst write write p50 search p50 resp B   amp     vary   
------------------------------------------------------------------------------------------------
control 1.0.0                      0.23s    0.01s    0.009s    0.001s     4175     x72      0%
server-memory 1.0.0                0.89s    0.05s    0.021s    0.005s       39      x1     62%
server-memory 2.0.0                0.80s    0.03s    0.013s    0.005s       39      x1     69%
memento 0.7.0                      1.42s    4.54s    0.111s    0.045s     1497     x26    293%
memdb 1.4.0                        0.42s    0.01s    0.001s    0.002s     1027     x18      0%
memory-lean 1.5.0                  0.12s    0.01s    0.004s    0.002s      164      x3      0%
mcp-knowledge-graph 1.3.2          0.13s    0.01s    0.005s    0.003s       39      x1      0%
zenbrain 0.3.0                     0.43s    0.01s    0.001s    0.002s      663     x11      0%
memory-mcp-1file 0.9.2             0.51s    1.56s    0.036s    0.055s     1969     x34     11%
statecore-mcp 1.0.0                0.36s    0.02s    0.005s    0.002s     5710     x98      5%
mcp-duckdb-memory-server 1.1.10    0.33s    0.14s    0.010s    0.005s      210      x4     25%

'vary' is how far the worst steady-state measurement moved across 3 passes, as a fraction
of its own median: first write, write, search and response bytes, with timings under 20 ms
left out because a ratio of millisecond noise is not a measurement. Absolute ranges and
the noisier startup/restart figures are in results/*-cost.json.
```

**Retrieval is measured with questions that have no answer, because otherwise "return everything"
scores like a search.** The `noans` column is how many unanswerable questions a subject answered
anyway — a memory that always answers is a memory that cannot say "I don't have that".

**The two axes are close to inverted, and two opposite failures score identically.** Ranked by
retention the order is control, memdb, zenbrain. Ranked by retrieval it is zenbrain and
memory-mcp-1file, then the control, then everybody else — and the two servers most people actually use
come last, at zero.

The sharpest example is a pair a single score would have got wrong:

```
$ python compare.py memento server-memory-1.0.0
  only memento correct     11
  only server-memory       12
  exact McNemar p = 1.0000  -> not separated by this corpus
```

They are opposites — one answers everything including all twelve questions that have no answer, the
other answers nothing at all — and on this corpus they are statistically identical.

- **`@modelcontextprotocol/server-memory`, both versions** — 7 of 8 probes pass, and it answers
  **almost none** of the 60 questions: 0 as written, 2 as keywords. `search_nodes` matches the query
  as a literal substring, so `"postgres staging port"` returns nothing and `"postgres"` returns the
  record - which is why stripping the meaningless words is worth two questions to it and nothing to
  most of the rest.
- **memento** — returns the same three entities for a matching name, a nonsense string and the empty
  query. Its search is a listing, and it speaks on every unanswerable question.
- **memory-mcp-1file** — the highest retrieval count here (42 of 60 as written, 42 as keywords)
  against zenbrain's 40 and 33, and the one subject excluded from the conformance table for leaking
  state between stores. Whether the two are separated depends on the phrasing: 8 discordant questions
  against 5, p = 0.58, as written; 11 against 2, p = 0.0225, as keywords. Sixty questions establishes
  that both are far better than memdb and does not establish, on the questions alone, which of them is
  better than the other.

`runs` and `95%` are two different error bars and both matter. `runs` is the min–max of the whole
experiment repeated three times: the **measurement** error, and it is zero on every subject here.
`95%` is the Wilson interval: the **sampling** error, how far a different sixty questions might move
the score, about seven counts either way. A repeatable number whose precision is limited only by the
size of the corpus is a good place to be.

Two rows whose intervals overlap are not separated by this corpus — and because every subject answers
the *same* questions, the sharper test is the paired one:

```
$ python compare.py zenbrain memdb
  only zenbrain correct    15
  only memdb correct        0
  exact McNemar p = 0.0001  -> separated
```

The control passing all nine is the claim that every probe *can* pass, which is the difference
between a conformance suite and a set of accusations.
