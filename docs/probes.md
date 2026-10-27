# The instruments

Moved here from `README.md` unchanged, so that page can stay an argument rather
than an archive. The numbers are the same numbers; the generated reports they quote are still
at the top of the repository.

## The ten probes

| probe | the promise it tests |
|---|---|
| `isolation` | a record written into one store is not visible from a different store |
| `ack_readback` | a write that returned success is returned by a fresh read |
| `verbatim` | the record comes back as the record that was written, character for character |
| `restart` | the write survives the server being stopped and started |
| `forget` | a record can be made to stop being kept, and the others are still there afterwards |
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

## The positive control: the probes can pass

A suite that only ever fails measures nothing. `control/memory_server.py` is the smallest MCP memory
server built so that all ten probes pass, and it is the opposite decision from the server that fails:
**append-only, never rewrite**, with an OS lock around the append and a read-back before the write is
acknowledged. Unknown fields, unknown record types and concurrent writers survive by construction
rather than by care.

```
$ python harness.py --adapter=control --cmd="python control/memory_server.py"
isolation        PASS   0.3s  store A's record was not visible from store B
ack_readback     PASS   0.2s  acknowledged alpha; a fresh read returned 1 entities: ['alpha']
verbatim         PASS   0.5s  all 9 strings came back byte for byte, over the wire: 2, 3 and 4-byte UTF-8, ...
restart          PASS   0.5s  three writes across three server lifetimes; read back ['restart-0', ...]
forget           PASS   0.3s  asked to forget plinth-obsidian; after a restart the other two came back and it did not
findable         PASS   0.4s  all 8 acknowledged records came back in the top 3 for a search on their own name
foreign_field    PASS   0.3s  the extra field survived the next write
foreign_record   PASS   0.3s  the unmodelled record survived
concurrent       PASS   1.5s  20 of 20 acknowledged writes survived two servers on one store
large_record     PASS   0.2s  wrote 100000 characters, read back 100000
0 probe(s) failed
```

**The control lost 4 of 20 concurrent writes on its first version.** It relied on `O_APPEND` alone,
and on Windows the write position is fixed when the file is opened, so two processes appending at once
write to the same offset and clobber each other. Adding an OS lock (`msvcrt.locking` on Windows,
`flock` on POSIX) took it to 0 losses in 5 consecutive runs of 50 concurrent writes. That is the same
failure the reference server is reported to have, reproduced on demand - and it is why the concurrency
probe is worth running.

## The negative control: the probes can fail

A control proves the probes **can** pass. It says nothing about whether they can fail, and until this
phase nothing in this repository asked. The `forget` probe had just been published with six PASSes,
five "this subject cannot be asked" and **no FAIL at all** - so nothing in the table distinguished
"no subject broke this promise" from "this probe would not have noticed if one had".

`mutants.py` takes the control, breaks exactly one promise in it, and checks the whole nine-probe run
against the verdicts written down **before** the run. The prediction is what is being tested; filling
it in from what the run happened to print would make the table a description of the code instead of a
check on it.

```
$ python mutants.py
mutant               aimed at        iso  ack  vbt  rst  fgt  fnd  ffd  frc  cnc  lrg
----------------------------------------------------------------------------------------
leak-everywhere      isolation       FAIL .    .    .    .    .    .    .    .    .
no-persist           ack_readback    .    FAIL FAIL FAIL unk  FAIL unk  .    FAIL FAIL
keep-last            restart         .    .    FAIL FAIL unk  FAIL FAIL FAIL FAIL .
no-forget            forget          .    .    .    .    FAIL .    .    .    .    .
forget-all           forget          .    .    .    .    unk  .    .    .    .    .
reshape-modelled     foreign_field   .    .    .    .    .    .    FAIL .    .    .
drop-unnamed         foreign_record  .    .    .    .    .    .    .    FAIL .    .
stale-cache          concurrent      .    .    .    .    .    .    .    .    FAIL .
truncate-large       large_record    .    .    .    .    .    .    .    .    .    FAIL
lossy-locale         verbatim        .    .    FAIL .    .    .    .    .    .    .
mute-search          findable        .    .    .    .    .    FAIL .    .    .    .
blind-search         findable        .    .    .    .    .    FAIL .    .    .    .
```

All 120 predicted verdicts matched, on all twelve mutants. The generated table is
[`MUTANTS.md`](../MUTANTS.md), CI runs the whole battery on every push, and `--only=no-forget` runs
one.

**Eight of the ten fail alone** - one mutation reaches that probe and stops: `isolation`, `verbatim`,
`forget`, `findable`, `foreign_field`, `foreign_record`, `concurrent`, `large_record`. The two that
cannot be isolated are `ack_readback` and `restart`, and the reason is structural rather than a
weakness in the probes: every probe begins by writing a record and reading it back, so a subject that
loses writes at the root fails all of them. `keep-last` still pulls the two apart - it replaces the
store with each new record, so one write survives it and three do not.

`forget` is attacked twice, and the second attack is the one worth reading. `no-forget` acknowledges
the deletion and keeps the record: a plain FAIL, caught. `forget-all` deletes **everything** instead,
and the answer the caller gets back is byte-for-byte the same. The probe returns no verdict at all
rather than a PASS, because the two records nobody asked about are gone too, and a store that lost
everything cannot be told apart from a store that forgot exactly what it was told to. Over-deleting
and breaking are different defects and the probe cannot say which it saw, so it says that. Deletion
fails in two opposite directions, which is why the probe writes three records with no word in common
and insists the other two survive.

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
