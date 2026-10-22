# memory-conformance

**Memory systems claim to remember. This measures whether they keep what they acknowledged.**

A memory server answers `ok` and you move on. That answer is a promise about bytes, and almost
nobody tests it: the write is accepted, the record is gone, and the failure is discovered weeks later
by someone who trusted it. These are conformance probes for that promise, run against a server's own
public tools over its own transport - no internals, no mocks, no source reading.

```
$ python harness.py --cmd="node node_modules/@modelcontextprotocol/server-memory/dist/index.js"
isolation        PASS              3.6s  store A's record was not visible from store B
ack_readback     PASS              4.6s  acknowledged alpha; a fresh read returned 1 entities: ['alpha']
restart          PASS             15.7s  three writes across three server lifetimes; read back [restart-0, ...]
findable         PASS              2.3s  all 8 acknowledged records came back in the top 3 for a search on their own name
foreign_field    FAIL              7.8s  the extra field was silently dropped by the next write
foreign_record   PASS              5.0s  the unmodelled record survived
concurrent       PASS              3.6s  20 of 20 acknowledged writes survived two servers on one store
large_record     PASS              1.9s  wrote 100000 characters, read back 100000
1 probe(s) failed
```

## The eight probes

| probe | the promise it tests |
|---|---|
| `isolation` | a record written into one store is not visible from a different store |
| `ack_readback` | a write that returned success is returned by a fresh read |
| `restart` | the write survives the server being stopped and started |
| `findable` | a record can be found again by the name it was stored under |
| `foreign_field` | a field the server does not model survives the next write |
| `foreign_record` | a record type the server does not model survives the next write |
| `concurrent` | two servers on one store keep every acknowledged write (threads, one server each, released together) |
| `large_record` | a record as large as the subject accepts comes back whole |

Every probe drives the server through MCP `tools/call` and then checks both the answers over the
wire and the bytes on disk. Each runs against a fresh store in a temporary directory, so probes
cannot contaminate each other.

`isolation` runs first and is a **precondition, not a feature**. A verdict measured on a subject that
carries state between stores describes leaked state, so a subject that fails it is reported with a
warning and its other verdicts must not be published. A probe answers PASS, FAIL, or **UNKNOWN** -
and UNKNOWN is a real answer: the probe could not be expressed against this subject, which is not
the same thing as a defect.

## Result: `@modelcontextprotocol/server-memory@1.0.0`

**1 of 6 failed.** Node 24.19.0, Python 3.14.7, Windows, 2026-10-19.

`foreign_field`, reproduced:

1. the server acknowledges an entity,
2. a human (or another tool) adds a field to that entity in the JSONL store - `"reviewed_by": "a human"`,
3. the server is restarted and accepts one more write,
4. the annotated field is **gone**, and nothing in any reply said so.

The store is rewritten from the server's own parsed model on every mutation, so anything the model
does not represent is discarded at the next write. A tool that writes to the same store - a script,
another MCP client, a person with an editor - cannot tell that its data was dropped.

The record-level probe passes: a whole line whose `type` the server does not model did survive the
next write in this version. So the loss is **field-level**, not line-level, and the two should not be
confused when reading bug reports.

## Three errors this harness caught in itself

- **The concurrency probe was not a race.** The first version ran writer 0 to completion and then
  writer 1, which is a sequence: each write read the file the previous one had already rewritten, so
  "20 of 20 survived" proved nothing. Fixed with two threads released together.
- **It still passes at 100 writes** ("100 of 100 survived", 3.5 s). A widely reported lost-update
  pattern for this server does not reproduce here in this version, and saying so is part of the job:
  a conformance suite that only ever confirms the folklore is not measuring anything.
- **The client decoded JSON-RPC as cp1252.** `subprocess.Popen(text=True)` uses the console codepage,
  so the first subject that emitted a single non-ASCII character - an em dash in a tool description
  was enough - killed the stdout reader thread with `UnicodeDecodeError`, and every subsequent
  request timed out as if the server had hung. The transport is UTF-8 by specification and is now
  decoded as such. All three earlier subjects were re-run after the fix and their verdicts are
  unchanged; the reference server's `foreign_field` still fails, which is the point.

## Retrieval: keeping is not finding

Retention is not retrieval. `retrieval.py` writes twelve memories and asks twelve questions - six that
share vocabulary with the memory they want, six paraphrases - then reports hit@1 and hit@3 on a server
that has just restarted, so search cannot ride on anything the writing process still held in memory.

> *This section records the original twelve-question run against `retained` and `basic-memory`. The
> corpus is now 36 records and 30 questions in four bands - including near-duplicate distractors and
> questions with no answer at all - and every subject in the matrix is measured on it. See the
> retrieval table above.*

| subject | easy (6) | hard (6) | all 12 |
|---|---|---|---|
| `@modelcontextprotocol/server-memory@1.0.0` | 0/6 h1, 0/6 h3 | 0/6 h1, 0/6 h3 | **0/12** |
| `retained` (lexical only) | 6/6 h1, 6/6 h3 | 4/6 h1, 5/6 h3 | **10/12 h1, 11/12 h3** |
| `retained` (hybrid, `all-minilm` vectors) | 6/6 h1, 6/6 h3 | 5/6 h1, 6/6 h3 | **11/12 h1, 12/12 h3** |
| `basic-memory` 0.23.2 (text index, no embeddings) | 6/6 h1, 6/6 h3 | 5/6 h1, 6/6 h3 | **11/12 h1, 12/12 h3** |

The reference server scores zero, and the reason is not ranking - it is matching. Characterised
directly:

```
deployment               -> [rec-key]     deployment key           -> [rec-key]
key rotates              -> [rec-key]     staging                  -> [rec-port]
postgres staging port    -> []            environment staging      -> []
```

It returns a record only when the **whole query string** appears in the record, so a question phrased
the way a person phrases it returns nothing at all. `retained` tokenises, ranks with `bm25` and takes
the top k, which is why it answers ten of twelve and misses only the question with no shared
vocabulary at all ("how many machines do we run" against "three hosts: throne, watchtower and pi").

That remaining miss is the honest ceiling of `retained`: no amount of ranking fixes a query whose
words are absent from the store. `basic-memory` answers that same question without any embedding, and
the reason matters when reading the row above - it is not understanding.

Its text search matches each query term as a **prefix** of a stored token, and returns a record if
any term matches. Characterised directly against a two-note store:

```
how many machines do we run -> [rec-hosts]   complet    -> [rec-speed]   linters -> []
run                         -> [rec-hosts]   completing -> []            thr     -> [rec-hosts]
lint                        -> [rec-speed]   throne     -> [rec-hosts]   machine -> []
```

So `run` reaches "the estate **runs** on three hosts", which is the whole of why that question is
answered at rank 1; `completing` does not reach "completes", and no query reaches a word that is not
in the store at all. Prefix matching is cheaper than a vector index and enough for the one question
`retained` missed - but it is still character overlap, not semantics. Twelve questions were too few to
find where it stops working; the thirty-question corpus does, and the answer is the `hard` band. Its
single k=1 miss in that original run was a ranking question, not a
matching one: "when is a write considered safe" returns `[rec-lock, rec-ack]`, and both are about
writes being safe.

## The positive control: the probes can pass

A suite that only ever fails measures nothing. `control/memory_server.py` is the smallest MCP memory
server built so that all six probes pass, and it is the opposite decision from the server that fails:
**append-only, never rewrite**, with an OS lock around the append and a read-back before the write is
acknowledged. Unknown fields, unknown record types and concurrent writers survive by construction
rather than by care.

```
$ python harness.py --adapter=control --cmd="python control/memory_server.py"
ack_readback     PASS   acknowledged alpha; a fresh read returned 1 entities
restart          PASS   three writes across three server lifetimes; all read back
foreign_field    PASS   the extra field survived the next write
foreign_record   PASS   the unmodelled record survived
concurrent       PASS   50 of 50 acknowledged writes survived two servers on one store
large_record     PASS   100,000 characters written, 100,000 read back
0 probe(s) failed
```

**The control lost 4 of 20 concurrent writes on its first version.** It relied on `O_APPEND` alone,
and on Windows the write position is fixed when the file is opened, so two processes appending at once
write to the same offset and clobber each other. Adding an OS lock (`msvcrt.locking` on Windows,
`flock` on POSIX) took it to 0 losses in 5 consecutive runs of 50 concurrent writes. That is the same
failure the reference server is reported to have, reproduced on demand - and it is why the concurrency
probe is worth running.

## A fourth subject: `basic-memory`

[basic-memory](https://github.com/basicmachines-co/basic-memory) is markdown-first: one note per file
with YAML frontmatter, a SQLite index beside it, and MCP tools `write_note`, `read_note`,
`search_notes` and `list_directory`. Probed at 0.23.2 on Python 3.14.7, Windows, 2026-10-19, with
semantic search switched off so the run needs no embedding model and stays lexical (see below).

```
$ python harness.py --adapter=basic-memory --cmd=".venv-bm\Scripts\basic-memory.exe mcp --transport stdio"
ack_readback     PASS            30.2s  acknowledged alpha; a fresh read returned 1 entities: ['alpha']
restart          PASS            57.4s  three writes across three server lifetimes; read back ['restart-0', ...]
foreign_field    UNKNOWN                        14.4s  basic-memory keeps one markdown file per note plus
                                a SQLite index, not a single JSON-lines store; this probe's
                                annotate-a-file check has no equivalent here
foreign_record   UNKNOWN                        13.9s  (same)
concurrent       PASS            47.6s  20 of 20 acknowledged writes survived two servers on one store
large_record     PASS            31.5s  wrote 100000 characters, read back 100000
0 probe(s) failed
```

**Four passes, no failures, two questions the suite cannot ask this subject.** `foreign_field` and
`foreign_record` work by annotating a single JSON-lines store between two writes and looking for the
bytes afterwards. basic-memory has no such file, so the adapter raises from `store_path()` and both
probes report UNKNOWN rather than a verdict. Pointing `store_path()` at a note file would be worse
than useless: the unmodelled-record probe appends a line to whatever file it is handed, and
basic-memory never rewrites a note it did not touch, so the probe would find the record intact and
report a PASS that measures nothing. A probe that cannot be expressed is reported as unanswerable -
it is not converted into a pass, and it is not quietly dropped.

What the four that did run say: a 100,000-character note comes back whole (after the adapter strips
the frontmatter envelope, which adds a newline the record never had), notes survive restarts, and
twenty concurrent writes from two server processes sharing one project and one SQLite index all
survived. The retention promise basic-memory makes to a caller, it keeps.

Two things had to be configured to probe it at all, and neither touches what is measured:

- **A project per store.** Every server is started with `BASIC_MEMORY_CONFIG_DIR` pointing into the
  probe's temp directory and `BASIC_MEMORY_MCP_PROJECT` selecting the single project registered
  there, so nothing is written to the user's `~/.basic-memory` and no probe can see another's notes.
- **Semantic search off.** Out of the box basic-memory enables fastembed embeddings, which want a
  model download; `semantic_search_enabled: false` makes its default search `text`, which is what
  the probes and the retrieval cases use anyway.

## The subjects measured so far

```
$ python matrix.py

subject                         isol     ack      restart  find     field    record   conc     large    ceil
------------------------------------------------------------------------------------------------------------
control 1.0.0                   PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS      60s
server-memory 1.0.0             PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS      60s
server-memory 2.0.0             PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS      60s
memento 0.7.0                   PASS     PASS     PASS     FAIL     PASS     PASS     PASS     FAIL     180s
memdb 1.4.0                     PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS      60s
memory-lean 1.5.0               PASS     PASS     PASS     PASS     FAIL     FAIL     PASS     PASS      60s
mcp-knowledge-graph 1.3.2       PASS     PASS     PASS     PASS     PASS     FAIL     FAIL     PASS      90s
zenbrain 0.3.0                  PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS      60s
memory-mcp-1file 0.9.2          FAIL     (PASS)   (PASS)   (PASS)   (UNKNOWN)  (UNKNOWN)  (FAIL)   (UNKNOWN)   60s
statecore-mcp 1.0.0             PASS     PASS     PASS     FAIL     PASS     PASS     FAIL     UNKNOWN   60s
mcp-duckdb-memory-server 1.1.10 PASS     PASS     PASS     PASS     UNKNOWN  UNKNOWN  FAIL     UNKNOWN   90s

(x) verdict qualified by a failed isolation precondition - not publishable on its own
ceil is the per-call ceiling each subject was given; a verdict measured at one ceiling
does not transfer to another, and memento is the proof: same machine, PASS at 180s and
FAIL at 60s on the same probe.
1 subject(s) out of scope, 10 measured

retrieval, cold start, 36 records - a score, not a verdict. hit@3 per band: easy shares
wording with the answer, hard is a paraphrase, adversarial has a near duplicate competing.
'noans' is questions with no answer in the store that were answered anyway: 0 is right.
subject                         easy    hard    adver   all h1   all h3   noans   runs      95%
-----------------------------------------------------------------------------------------------
control 1.0.0                   8/8     0/8     5/8     13/30    13/30    0/6     13-13     8-18
server-memory 1.0.0             0/8     0/8     0/8     0/30     0/30     0/6     0-0       0-3
server-memory 2.0.0             0/8     0/8     0/8     0/30     0/30     0/6     0-0       0-3
memento 0.7.0                   2/8     2/8     4/8     2/30     8/30     6/6     8-8       4-13
memdb 1.4.0                     7/8     0/8     0/8     1/30     7/30     6/6     7-7       4-12
memory-lean 1.5.0               6/8     0/8     0/8     6/30     6/30     0/6     6-6       3-11
mcp-knowledge-graph 1.3.2       0/8     0/8     0/8     0/30     0/30     0/6     0-0       0-3
zenbrain 0.3.0                  8/8     8/8     7/8     20/30    23/30    6/6     23-23     18-26
memory-mcp-1file 0.9.2          8/8     7/8     7/8     20/30    22/30    6/6     22-22     17-26
statecore-mcp 1.0.0             0/8     0/8     0/8     0/30     0/30     6/6     0-0       0-3
mcp-duckdb-memory-server 1.1.10 5/8     0/8     0/8     5/30     5/30     0/6     5-5       2-10

'runs' is the min-max of the same experiment repeated 3 times; '95%' is the Wilson
interval for the majority result, in counts. The first covers repeating the experiment,
the second covers asking a different thirty questions. They are not the same error.

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
  only memento correct      8
  only server-memory        6
  exact McNemar p = 0.7905  -> not separated by this corpus
```

They are opposites — one answers everything including six questions that have no answer, the other
answers nothing at all — and on this corpus they are statistically identical.

- **`@modelcontextprotocol/server-memory`, both versions** — 7 of 8 probes pass, and it answers
  **none** of the 30 questions. `search_nodes` matches the query as a literal substring:
  `"postgres staging port"` returns nothing, `"postgres"` returns the record.
- **memento** — returns the same three entities for a matching name, a nonsense string and the empty
  query. Its search is a listing, and it speaks on every unanswerable question.
- **memory-mcp-1file** — the joint-best retriever here (22/30), and the one subject excluded from the
  conformance table for leaking state between stores.

`runs` and `95%` are two different error bars and both matter. `runs` is the min–max of the whole
experiment repeated three times: the **measurement** error, and it is zero on every subject here.
`95%` is the Wilson interval: the **sampling** error, how far a different thirty questions might move
the score, about four counts either way. A repeatable number whose precision is limited only by the
size of the corpus is a good place to be.

Two rows whose intervals overlap are not separated by this corpus — and because every subject answers
the *same* questions, the sharper test is the paired one:

```
$ python compare.py zenbrain memdb
  only zenbrain correct    15
  only memdb correct        0
  exact McNemar p = 0.0001  -> separated
```

The control passing all eight is the claim that every probe *can* pass, which is the difference
between a conformance suite and a set of accusations.

## Cost: the third axis

```
$ python matrix.py --cost-only        # timings taken in a quiet pass of their own

subject                  startup  lst write write p50 search p50 resp B   amp     vary
control 1.0.0               0.23s    0.01s    0.009s    0.001s     4175     x72      0%
server-memory 1.0.0         0.89s    0.05s    0.021s    0.005s       39      x1     62%
server-memory 2.0.0         0.80s    0.03s    0.013s    0.005s       39      x1     69%
memento 0.7.0               1.42s    4.54s    0.111s    0.045s     1497     x26    293%
memdb 1.4.0                 0.42s    0.01s    0.001s    0.002s     1027     x18      0%
memory-lean 1.5.0           0.12s    0.01s    0.004s    0.002s      164      x3      0%
mcp-knowledge-graph 1.3.2   0.13s    0.01s    0.005s    0.003s       39      x1      0%
zenbrain 0.3.0              0.43s    0.01s    0.001s    0.002s      663     x11      0%
memory-mcp-1file 0.9.2      0.51s    1.56s    0.036s    0.055s     1969     x34     11%
```

`resp` is the median bytes a server sends back for one question, and `amp` is that divided by the size
of the correct record — so answering by returning the whole store shows up as a multiplier.

`vary` is how far the worst steady-state measurement moved across three passes, as a fraction of its
own median, and it is not a rounding detail. **memento's first write ranged from 2.3 s to 14.4 s**
across three passes on the same machine — the 4.54 s is a median of a six-fold spread, so an agent
runtime capping a tool call at 10 s faces a coin flip rather than a budget. `memory-mcp-1file`'s
response size moved 11% between passes: the byte count is exact for one response, and the response is
the subject's choice, which is why byte counts are repeated too.

**Read this table with the retrieval one, or the cheapest memory looks like the best.** The two
subjects that cost 39 bytes per question return *nothing*; efficiency achieved by silence is not
efficiency. The best retriever (`memory-mcp-1file`, 22/30) is also among the most expensive per
question at 34× the size of the answer. And one marketing claim survives measurement intact:
`memory-lean` is genuinely lean — 164 bytes, 3×, and the fastest startup in the set.

**`store B/rec` is marginal, not average**, measured between two batches so the preallocation floor
cancels. Dividing total size by record count reported memento at 350,549 bytes per record; its true
marginal cost is **zero**, because its 4.3 MB store is allocated once and then holds anything.

The `ceil` column is the per-call ceiling each subject was given, and it changes verdicts. memento
passes `concurrent` at 180 s and fails it at 60 s on the same machine on the same day. A verdict is
only meaningful together with the ceiling it was measured under.

Two further subjects were measured before the current probe set and are not in the matrix:
[retained](https://github.com/arm00pv/retained) passed 6/6 including 50/50 concurrent writes across
two processes, and [basic-memory](https://github.com/basicmachines-co/basic-memory) 0.23.2 passed 4/6
with 2 unanswerable — `foreign_field` and `foreign_record` have no equivalent against a directory of
markdown notes. `retained` is the answer to the probe that fails: append-only, hash-chained,
read-back verified before the write is acknowledged.

## Run it on your own server

One command, no configuration, and it tells you what it could not measure:

```
$ python check.py "node my-server.js"

subject : node my-server.js
binding : discovered, proven by round-trip
attempt : 1, ceiling 60s

conformance
  isolation       PASS       store A's record was not visible from store B
  ack_readback    PASS       acknowledged alpha; a fresh read returned 1 entities: ['alpha']
  restart         PASS       three writes across three server lifetimes; read back [...]
  findable        PASS       all 8 acknowledged records came back in the top 3 for a search on their own name
  foreign_field   UNKNOWN(not-applicable)  no store is declared for this subject [...]
  foreign_record  UNKNOWN(not-applicable)  no store is declared for this subject [...]
  concurrent      FAIL       10 write(s) failed outright: ["create_entities refused: ..."]
  large_record    UNKNOWN(not-applicable)  adapter cannot measure record content
  4 kept, 3 unknown, 1 failed

retrieval (36 records, 30 questions, cold start)
  hit@3  easy 5/8  hard 0/8  adversarial 0/8  ->  all 5/30
  questions with no answer that were answered anyway: 0/6

cost
  startup 0.59s   first write 0.13s   write 0.010s   search 0.007s
  210 bytes per question (4x the size of the answer)   - bytes per record

what to do next
  - foreign_field and foreign_record are UNKNOWN because no store is declared. A manifest of about
    fourteen lines makes them answerable - see manifests/memdb.json.
  - Each probe ran once. Add --repeat=3 to find out whether the verdicts are stable.
```

**UNKNOWN is not a pass.** A badge reports all three counts, so a subject cannot make itself look
good by being unmeasurable:

```
$ python check.py "node my-server.js" --badge
badge written to conformance-badge.svg
```

Exit codes: `0` every probe that could run was kept, `1` something failed, `2` the subject could not
be graded at all — which happens when it leaks state between stores, and then no other verdict in the
report describes it either.

## Adding a system

The harness talks MCP over stdio, so any MCP server can be probed by changing `--cmd`. Three ways in,
in order of how much you have to write:

**1. Nothing.** `--adapter=auto` lists the server's own tools, proposes a write tool from each
tool's JSON schema, then tries every plausible reader until one returns a token that was just
written. A binding that has not been proven is never used. This reaches five of the eight probes.

**2. A manifest - twelve lines of JSON.** Say where the store is and how a record is identified;
everything else stays discovered:

```json
{"subject": "@j0hanz/memdb 1.4.0",
 "command_must_contain": ["memdb"],
 "store": {"kind": "sqlite", "path": ".memdb/memory.db", "table": "memories",
           "match": {"column": "content", "op": "contains"},
           "content_column": "content"}}
```

```
$ python manifest.py manifests/memdb.json "node node_modules/@j0hanz/memdb/dist/index.js"
predicate: {"column": "content", "op": "contains"}  ->  matched the record that was just written
OK        this manifest describes this subject
```

A declaration is a claim, so it is checked before any verdict depends on it: the command must match,
the declared path must exist inside the run's store directory, and the declared predicate must find
a record that was just written through the server. All eight probes then become answerable.

**3. An adapter**, when the tool vocabulary itself differs. Implement `server()`, `write()`,
`read()` and pass it to the probes - `ReferenceAdapter` in `harness.py` is 20 lines and is the
template, and `BasicMemoryAdapter` is the worked example for a subject whose records live in a
directory of files rather than in one store file.

## Why this exists

It comes out of [silentfail](https://github.com/arm00pv/silentfail): the same doctrine, that a system
reporting success while doing nothing is the defect class worth engineering against, pointed at the
one place where it is least examined. The failure this probe found is silent by construction - the
success reply is honest about the write and silent about the loss.

## Limits, stated

- **One version per server.** Numbers above are `@modelcontextprotocol/server-memory` 1.0.0 and
  2.0.0, `retained` and `basic-memory` 0.23.2 on 2026-10-19, and a different version of any of them
  can pass or fail differently. `--expect=` re-runs a pinned report and exits non-zero on drift.
- **Eight probes are not a spec.** They cover retention, concurrency, findability and one
  precondition - not retrieval quality, latency or token cost. Retrieval is measured separately
  (`retrieval.py`, and the second table in `MATRIX.md`) and reported as a score, because
  "relevant" is a judgement while "returned" is a fact.
- **Cost is measured once, not repeatedly.** A single quiet pass beats a timing taken while nine
  other subjects run, and it is still not a distribution: there is no p90 on any cost column and no
  repeat. Bytes are used rather than tokens because bytes are what the transport carries and what can
  be counted exactly; a token estimate would be a guess wearing a number's clothes.
- **Retrieval is repeated three times and is deterministic.** Every subject's `runs` column is a
  single number: three complete repetitions of the experiment moved nothing. An earlier draft of this
  README blamed a 22/30 → 24/30 difference on instability; that difference was observed across two
  runs during which the harness itself was changing, which is not the same thing. Verified properly,
  zenbrain is 23/30 on four separate invocations and on all three in-run passes.
- **Cost is repeated three times, and the ranges matter more than the medians.** memento's first
  write spans 2.3–14.4 s across passes; quoting the 4.5 s median alone would be a claim about a fixed
  cost that does not exist. Full per-metric ranges, including the noisier startup and restart
  figures, are in `results/*-cost.json`. Timings under 20 ms are left out of `vary` because a ratio
  needs something to divide by.
- **There is no end-to-end session cost.** The bill an agent pays is many writes, many reads and many
  misses; this measures one of each.
- **`findable` is a floor, not a benchmark.** It asks only whether a record comes back for its own
  name. Passing it means a memory can be read back at all; it says nothing about answering questions.
- **Every probe is run three times.** `--repeat=N` repeats all eight, reports the modal outcome,
  prints the tally, and marks any disagreement `unstable`. A tie breaks toward the worse outcome, so
  an unstable subject is never rounded up to PASS. Repeating only the probes that have been *seen* to
  flake is the assumption that has been retracted twice in this project already.
  `--repeat-probes=` narrows the list when you deliberately want to save time.

  The result of repeating all of them: **72 verdicts, 216 executions, one unstable row** — and it
  belongs to the subject already excluded for leaking state. Its `restart` probe passed twice and
  failed once, and the evidence it printed contained a record written by a *different probe* in a
  *different store*. The flakiness is a downstream symptom of the isolation failure, which is the
  strongest argument for `isolation` running first.
- **Retrieval numbers come with an interval, and the interval is the honest part.** 30 questions
  separates the ends of the table and not the middle. Every row carries a 95% Wilson interval, and
  because every subject answers the *same* 30 questions, `compare.py` runs the paired test
  (exact McNemar) that the marginal counts cannot replace:

  ```
  $ python compare.py zenbrain memory-mcp-1file
    correct for both         20
    only zenbrain correct     2
    only memory-mcp-1file     2
    exact McNemar p = 1.0000  -> not separated by this corpus
  ```

- **The retrieval corpus is authored by this project.** The questions may share its author's
  vocabulary. The `adversarial` band is the most robust part, because a near-duplicate distractor is
  hard to match by accident, and `absent` is the most objective, because "nothing" needs no
  judgement about relevance.
- **`python matrix.py --report-only`** re-renders both tables from the reports already under
  `results/` without re-running a subject. A verdict is worth little if the table around it can only
  be produced by a twenty-minute run.

MIT licensed.