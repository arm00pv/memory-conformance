# memory-conformance

**Memory systems claim to remember. This measures whether they keep what they acknowledged.**

A memory server answers `ok` and you move on. That answer is a promise about bytes, and almost
nobody tests it: the write is accepted, the record is gone, and the failure is discovered weeks later
by someone who trusted it. These are conformance probes for that promise, run against a server's own
public tools over its own transport - no internals, no mocks, no source reading.

```
$ python harness.py --cmd="node node_modules/@modelcontextprotocol/server-memory/dist/index.js"
ack_readback     PASS      0.7s  acknowledged alpha; a fresh read returned 1 entities: ['alpha']
restart          PASS      1.9s  three writes across three server lifetimes; read back [restart-0, ...]
foreign_field    FAIL      1.2s  the extra field was silently dropped by the next write
foreign_record   PASS      1.1s  the unmodelled record survived
concurrent       PASS      1.6s  20 of 20 acknowledged writes survived two servers on one store
large_record     PASS      0.7s  wrote 100000 characters, read back 100000
1 probe(s) failed
```

## The six probes

| probe | the promise it tests |
|---|---|
| `ack_readback` | a write that returned success is returned by a fresh read |
| `restart` | the write survives the server being stopped and started |
| `foreign_field` | a field the server does not model survives the next write |
| `foreign_record` | a record type the server does not model survives the next write |
| `concurrent` | two servers on one store keep every acknowledged write (threads, one server each, released together) |
| `large_record` | a 100,000-character record comes back whole |

Every probe drives the server through MCP `tools/call` and then checks both the answers over the
wire and the bytes on disk. Each runs against a fresh store in a temporary directory, so probes
cannot contaminate each other.

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
`retained` missed - but it is still character overlap, not semantics, and the twelve questions here
are too few to tell you where it stops working. Its single k=1 miss is a ranking question, not a
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
ack_readback     PASS    30.2s  acknowledged alpha; a fresh read returned 1 entities: ['alpha']
restart          PASS    57.4s  three writes across three server lifetimes; read back ['restart-0', ...]
foreign_field    UNKNOWN 14.4s  probe could not run: basic-memory keeps one markdown file per note plus
                                a SQLite index, not a single JSON-lines store; this probe's
                                annotate-a-file check has no equivalent here
foreign_record   UNKNOWN 13.9s  (same)
concurrent       PASS    47.6s  20 of 20 acknowledged writes survived two servers on one store
large_record     PASS    31.5s  wrote 100000 characters, read back 100000
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

## The four subjects measured so far

| subject | adapter | result |
|---|---|---|
| `@modelcontextprotocol/server-memory@1.0.0` | `reference` | 5/6 - fails `foreign_field` |
| `control/memory_server.py` | `control` | 6/6 |
| [retained](https://github.com/arm00pv/retained) | `retained` | **6/6** - including 50/50 concurrent writes across two processes |
| [basic-memory](https://github.com/basicmachines-co/basic-memory) 0.23.2 | `basic-memory` | **4/6 + 2 unanswerable** - passes `ack_readback`, `restart`, `concurrent`, `large_record`; `foreign_field` and `foreign_record` have no equivalent against a directory of markdown notes |

`retained` is the answer to the probe that fails: append-only, hash-chained, read-back verified before
the write is acknowledged, so a field the server does not model cannot be lost by it.

## Adding a system

The harness talks MCP over stdio, so any MCP server can be probed by changing `--cmd`. A system with
a different tool vocabulary needs a small adapter: implement `server()`, `write()`, `read()` and pass
it to the probes - `ReferenceAdapter` in `harness.py` is 20 lines and is the template, and
`BasicMemoryAdapter` is the worked example for a subject whose records live in a directory of files
rather than in one store file.

## Why this exists

It comes out of [silentfail](https://github.com/arm00pv/silentfail): the same doctrine, that a system
reporting success while doing nothing is the defect class worth engineering against, pointed at the
one place where it is least examined. The failure this probe found is silent by construction - the
success reply is honest about the write and silent about the loss.

## Limits, stated

- **One version per server.** Numbers above are `@modelcontextprotocol/server-memory@1.0.0`,
  `retained` and `basic-memory` 0.23.2 on 2026-10-19, and a different version of any of them can pass
  or fail differently.
- **Six probes are not a spec.** They cover retention and concurrency, not retrieval quality, latency
  or token cost.
- **Probes are deterministic, not sampled.** There is no confidence interval to quote; a probe either
  reproduces or it does not, and each one prints what it saw.

MIT licensed.
