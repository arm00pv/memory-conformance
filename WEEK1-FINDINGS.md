# Week 1 — two subjects, two different failure axes

> **Addenda follow, in order, and two claims made below did not survive re-testing in Addendum 3.**
> Coverage widened from 2 subjects to 4 by discovering the write/read binding at runtime instead of
> hand-writing an adapter; the suite then learned to grade its own preconditions; then a subject's
> store could be declared instead of coded, and F1 and part of F4 were withdrawn. Read Addendum 3
> before quoting anything above it.


Run on Windows, Node v24.19.0, Python 3.14.7, 2026-10-20.

## The result in one sentence

The two servers fail on **different axes**: the reference server silently drops a field another
tool added, while memento keeps it but cannot survive two writers or a five-kilobyte record. Neither
is "the good one", and that is precisely what a conformance suite is for.

## Subjects

| # | subject | version | backend | isolatable? |
|---|---|---|---|---|
| 1 | `@modelcontextprotocol/server-memory` | 1.0.0 | JSONL file | yes (`MEMORY_FILE_PATH`) |
| 2 | `@iachilles/memento` | 0.7.0 | SQLite + sqlite-vec | yes (`MEMORY_DB_PATH`) |
| — | `@j0hanz/memdb` | 1.4.0 | SQLite | **no** — no store-path variable |
| — | `memory-mcp-1file` | 0.9.2 | file | **no** — no store-path variable |

## Results

```
probe            server-memory          memento
ack_readback     PASS     1.1s          PASS    29.9s
restart          PASS     1.9s          PASS    44.7s
foreign_field    FAIL     0.7s          PASS    22.2s
foreign_record   PASS     0.7s          PASS    22.7s
concurrent       PASS     1.2s          FAIL   125.4s
large_record     PASS     0.7s          UNKNOWN 126.4s
```

The reference server's result reproduces exactly and is unchanged by the refactor (1 of 6).

## F1 — memento deadlocks under concurrent writers *(withdrawn in Addendum 3)*

Five runs, four failures, one pass. The signature is identical every time: the first
`create_entities` from each writer never returns, then later calls fail with `[Errno 22] Invalid
argument` or `I/O operation on closed file` — writes to a dead process's stdin.

```
RUN 1: FAIL 66.4s   ['w0-0: did not answer within 60s', 'w0-1: [Errno 22] Invalid argument', ...]
RUN 2: FAIL 73.7s   ['w1-0: did not answer within 60s', 'w0-0: did not answer within 60s', ...]
RUN 3: FAIL 64.8s   ['w1-0: did not answer within 60s', 'w1-1: [Errno 22] Invalid argument', ...]
```

The single PASS is worse than the failures: a retry can look like a fix.

## F2 — memento's write cost explodes between 1 kB and 5 kB

Measured with `size_sweep.py`, fresh store per point, 150 s ceiling:

```
      chars    seconds
        100      19.05   ok
       1000      29.23   ok
       5000     >150     never completed
      10000     >150     never completed
      25000     >150     never completed
```

The reference server writes 100,000 characters in **0.7 s**. memento cannot complete 5,000 in
**150 s** — a ~10^5 gap at the top of the tested range. An agent storing a source file or a document
does not reliably get an error; it gets a hang. (Re-swept in Addendum 3: the boundary is between
4,000 and 5,000 characters, and above it the subject sometimes refuses explicitly and sometimes
hangs.)

## F3 — memento passes what the reference fails

`foreign_field` and `foreign_record` now produce real verdicts on a SQL store (see Changes), and
memento passes both: an added column survives the next write, and a table owned by another tool in
the same database is not destroyed.

This matters for how the results get reported. A one-line summary ("memento is buggy") would be
false. memento is **better** than the reference on data preservation and **worse** on concurrency
and size. A leaderboard that collapses this to a single rank would be lying by omission.

## F4 — memento's cost is paid up front

```
initialize 3.07s | create_entities 13.21s | add_observations 0.55s | read_graph 0.05s | search_nodes 1.33s
```

A fresh store is 4.3 MB because of the sqlite-vec index. Agent runtimes commonly cap a tool call at
10-30 s, so the first write into a new store is already past several ceilings. *(Corrected in
Addendum 3: 4.3 MB is per store, not per entity - byte-identical at 1, 5, 20 and 50 records.)*

## Findings about this suite

**S1 — the store probes were JSONL-only; now they are not.** They used to open the store file and
write JSON Lines, which made every SQL subject UNKNOWN on the two strongest probes. They now ask the
adapter (`annotate_field`, `field_survived`, `inject_foreign_record`,
`foreign_record_survived`), so a backend supplies its own meaning:

- JSONL: add a key to the record / append a line of an unmodelled type.
- SQLite: `ALTER TABLE entities ADD COLUMN` and set it on the row / create and populate a table the
  server does not read.

Both probes went from UNKNOWN to verdicts, and the SQL verdicts were the opposite of the reference's.

**S2 — a subject that cannot be pointed at a fresh store cannot be tested.** `@j0hanz/memdb` and
`memory-mcp-1file` expose no path variable, so probes would share one default store and contaminate
each other. memdb wrote a `.memdb/` directory into the repository during discovery, which is the
evidence. Both were dropped rather than tested badly. Conformance should state the requirement
explicitly: **a subject must be isolatable, or it is out of scope.**

**S3 — a fixed timeout manufactures UNKNOWNs.** At the original 30 s ceiling memento produced five
UNKNOWNs and one PASS. The server was slow, not broken. `--timeout=` is now a run parameter and must
be recorded with any verdict it produced.

## Changes made

- `MEMORY_DB_PATH` added to the per-store environment, so SQLite subjects can be isolated.
- Backend-agnostic store helpers on the adapter; `MementoAdapter` implements the SQLite versions.
- `MementoAdapter` — same tool surface as the reference, different store.
- `--timeout=` and `PROBE_TIMEOUT` replace the hardcoded 30 s default.
- `discover.py` — list any server's tools over its own transport.
- `timing.py` — attribute a timeout to one operation.
- `size_sweep.py` — find the size where a subject stops completing, instead of waiting out a timeout.

## What this proves

The suite finds real, reproducible defects in published, installable servers, on more than one
axis, and it can now do so for SQL-backed subjects rather than only JSONL files.

## What it does not prove

Breadth. Two of four candidate subjects were untestable for want of a store-path variable, so the
sample is two. The next bottleneck is coverage, not the number of probes.

## Next

1. Auto-detect write/read/search from `tools/list` so adding a subject stops costing a hand-written
   adapter. That is the only way 20 subjects is realistic.
2. Repeat each probe three times and record the modal verdict, because F1 is non-deterministic.
3. Decide and document what "isolatable" means, then list subjects that fail the requirement as
   **out of scope** rather than absent.

---

# Addendum: auto-detection brings coverage to four subjects

A hand-written adapter per subject does not scale, so the binding is now discovered at runtime
(`autodetect.py`, `AutoAdapter`): list the published tools, propose a write tool from each tool's
own JSON schema, then **try each plausible reader until one returns a token that was just written**.
A binding that has not been proven is never used.

## Coverage

```
subject                    adapter     ack    restart  f_field  f_record  concurrent  large
server-memory 1.0.0        reference   PASS   PASS     FAIL     PASS      PASS        PASS
memento 0.7.0              memento     PASS   PASS     PASS     PASS      FAIL        UNKNOWN
memdb 1.4.0                auto        PASS   PASS     UNKNOWN  UNKNOWN   PASS        UNKNOWN
memory-mcp-1file 0.9.2     auto        PASS   PASS     UNKNOWN  UNKNOWN   UNKNOWN     UNKNOWN
```

Two subjects that previously could not be tested at all are now measured, with no adapter written
for either.

## Four bugs the auto-detection had in itself

Each one turned a working server into a false negative, which is the failure mode a conformance
suite must never have.

1. **`entityType` swallowed the token.** The field is a category, not an identifier; matching on the
   substring "entity" sent the probe token into it. Fields containing "type" are now excluded from
   identifier matching.
2. **A single reader guess is not enough.** `recall` matches the substring "all" and then rejects an
   empty query. The first candidate can be wrong while a perfectly good reader sits next to it, so
   readers are now tried in order and the first that returns the token wins.
3. **A tag is a label, not content.** `memdb` silently rejects a tag containing spaces, and my
   binder was putting the whole record body into the `tags` array. The write failed while the caller
   was told nothing.
4. **The separator was a colon.** `token + ": " + content` is tokenised on the colon, so an
   exact-token search missed and a server that stored the record perfectly scored as having lost it.
   The separator is a space.

## S4 — auto-detection reaches 4 of 6 probes, and the reason is structural

It cannot run the two out-of-band probes, because it has no declared store semantics, and it cannot
run `large_record`, because it proves that a **name** came back, not that the **body** did. Token
embedding also makes the stored string longer than the probe writes, so an exact length comparison
could never pass.

`large_record` therefore reports **UNKNOWN**, not FAIL. Reporting FAIL would claim a defect that was
never observed, which is the one thing a conformance suite cannot do.

## S5 — memory-mcp-1file persists outside any controllable location

Its `restart` probe read back `['alpha', 'restart-0', 'restart-1', 'restart-2']` — `alpha` was written
by the *previous* probe, in a different temporary directory. Running the subject with `cwd` set to
its own store was not enough, so it keeps state somewhere the harness cannot redirect. Its
`concurrent` probe then failed to initialise at all.

Verdicts for a subject that leaks state across probes are not trustworthy even when they read PASS,
and the suite should be able to detect and flag that condition itself. It now does - see below.

---

# Addendum 2: the suite now grades its own preconditions

`isolation` is a new probe that runs **first**. It writes a marker into store A, then starts the
subject against store B and asks what B can see. A subject that shows B the marker cannot be
measured by any of the other probes, because their PASSes describe leaked state rather than stored
state.

```
subject                  isolation
server-memory 1.0.0      PASS    store A's record was not visible from store B
memento 0.7.0            PASS    store A's record was not visible from store B
memdb 1.4.0              PASS    store A's record was not visible from store B
memory-mcp-1file 0.9.2   FAIL    a record written into store A was visible from store B
```

## The evidence is inside the PASS rows

`memory-mcp-1file`, full run:

```
isolation        FAIL      3.7s  a record written into store A was visible from store B
ack_readback     PASS      3.6s  acknowledged alpha; a fresh read returned 2 entities:
                                  ['alpha', 'isolation-marker-alpha']
restart          PASS      7.9s  ... read back ['alpha', 'isolation-marker-alpha', 'restart-0', ...]
```

`ack_readback` wrote one record and got **two** back. The extra one is the isolation marker from a
different store. Both verdicts read PASS because the probe only asks whether its own record came
back - and that is the whole reason the precondition has to be a probe of its own rather than
something a human notices in the messages.

## S2 is partly resolved by working-directory isolation

`memdb` creates `.memdb/` relative to wherever it is started. Running each subject with `cwd` set to
its own store directory was enough to isolate it, and its `isolation` verdict is now PASS. The
isolation is opt-in, because a relative command (`node node_modules/...`) stops resolving in a
different directory - which is a bug this change introduced once and then fixed.

`memory-mcp-1file` writes somewhere neither a store-path variable nor the working directory reaches.
That subject is now **explicitly out of scope** rather than silently graded.

---

# Addendum 3: a store declared instead of coded, and two claims withdrawn

Three things happened. A subject's store can now be **declared** instead of hand-coded, which closed
the last three UNKNOWNs for a subject nobody wrote an adapter for. The probes learned to **repeat**
the ones that measure a race. And re-testing F1 and F4 under today's conditions showed that both
were stated too strongly.

## Three UNKNOWNs become verdicts

`@j0hanz/memdb` is discovery-bound: nothing about its tools is hand-coded, and before this change
five of the probes could answer and three could not, because the two out-of-band probes had no
declared store to inspect. With a twelve-line manifest:

```
subject  : @j0hanz/memdb 1.4.0
store    : .memdb/memory.db (sqlite)
measures : record bodies, out of band

isolation        PASS      0.8s  store A's record was not visible from store B
ack_readback     PASS      0.7s  acknowledged alpha; a fresh read returned 1 entities: ['alpha']
restart          PASS      1.4s  three writes across three server lifetimes; read back [...]
foreign_field    PASS      0.8s  the extra field survived the next write
foreign_record   PASS      0.8s  the unmodelled record survived
concurrent       PASS      1.1s  20 of 20 acknowledged writes survived two servers on one store
large_record     PASS      0.8s  wrote 50000 characters; 50000 are still in the store;
                                 refused at 100000 by its own limit, so 50000 was measured
0 probe(s) failed
```

Seven verdicts, no UNKNOWN, no failure. It cost thirteen lines of JSON:

```json
{"subject": "@j0hanz/memdb 1.4.0",
 "command_must_contain": ["memdb"],
 "store": {"kind": "sqlite", "path": ".memdb/memory.db", "table": "memories",
           "match": {"column": "content", "op": "contains"},
           "content_column": "content"}}
```

Only two of those keys carry knowledge a generic tool could not work out:

- **`match`** - memdb has no name column. The name the caller passes is folded into the text of the
  row, so a record is identified by containment. Guessing "there is a name column" would have found
  no row and reported UNKNOWN for a reason that says nothing about memdb.
- **`content_column`** - lets the size probe measure the body **on disk** instead of asking the
  server to render 100,000 characters back, which is the difference between a verdict and an
  UNKNOWN for any subject whose reader tools do not return bodies.

Everything else - which tool writes, which tool reads, how a name maps onto a schema - stays
discovered at runtime and proven by round-trip, exactly as before.

## A declaration is a claim, so the claim is checked

```
$ python manifest.py manifests/memdb.json "node node_modules/@j0hanz/memdb/dist/index.js"
subject  : @j0hanz/memdb 1.4.0
store    : C:\...\manifest_check__1lpp_fh\.memdb/memory.db
predicate: {"column": "content", "op": "contains"}  ->  matched the record that was just written
OK        this manifest describes this subject
```

It writes a record through the server, resolves the declared path inside the run's own directory,
and asks the declared predicate for that record. Four guards, each tested:

1. **The command must match.** A memdb manifest pointed at memento:
   `FAIL  the manifest does not describe this command; it would grade the wrong subject`
2. **The path must exist.** A manifest naming `wrong/memory.db`:
   `FAIL  wrote a record but '<tmp>' holds no wrong/memory.db`.
   Note what does *not* happen: SQLite's `connect()` creates a missing file, so the naive version of
   this check would have manufactured an empty database, altered nothing, and reported UNKNOWN for a
   reason unrelated to the subject. The backends refuse to connect until the path exists.
3. **The predicate must find something**, and the match clause is echoed back when it does not.
4. **A glob must match exactly one file.** Two matches means the manifest does not know which store
   it means, and picking the first would make the run depend on directory order.

## The declarative path agrees with the hand-written one

memento is the only subject with both a hand-written adapter and a manifest, which makes it a
control: if the manifest mechanism resolves the store or the predicate wrongly, the verdicts split.

```
probe             hand-written   declared
ack_readback      PASS           PASS
foreign_field     PASS           PASS
foreign_record    PASS           PASS
```

Same verdicts, so the mechanism is not adding a second source of error. `manifest_control.py` is
kept as the test.

## A defect the manifest found in this harness: a refusal is not an acknowledgement

memdb answers a 100,000-character write with

```
MCP error -32602: Input validation error: Invalid arguments for tool store_memory:
Too big: expected string to have <=100000 characters at content
```

delivered as an **ordinary tool result** carrying `isError: true`, not as a JSON-RPC error. The client
concatenated the content text and returned it, so a rejected write was indistinguishable from an
accepted one, and the harness recorded it as an ack. `McpServer.call()` now raises `ToolRefused`.

This is the sixth bug this suite has caught in itself and the first that could have published a
**false PASS** rather than a false FAIL. Every verdict previously recorded for a subject that
refuses writes was measuring acknowledgements that never happened. The four subjects above were
re-run after the fix and none of their verdicts moved - their writes were small enough to be
accepted - but that is luck, not design.

## A declared limit is not data loss

The first run with the manifest printed `large_record FAIL  read back None`. That FAIL came from a
code path that measured nothing: the disk measurement returned nothing, the probe fell through to
the wire measurement, and the wire measurement does not exist for this adapter. Two fixes:

- when no measurement is available, the probe reports **UNKNOWN**, never FAIL;
- when a write is refused by a message that names a size, the probe **halves the body** until the
  subject accepts it and reports the size it actually measured.

So the evidence line reads `wrote 50000 characters; 50000 are still in the store; refused at 100000
by its own limit, so 50000 was measured`. A bare `PASS` at "100,000" would have hidden that memdb
has a limit at all; a bare `FAIL` would have called a documented limit a data-loss defect. A
refusal that names anything other than a size is still UNKNOWN, because that is a defect the probe
did not manage to characterise.

The same change fixed an inconsistency one layer down: `initialize` was still on the original fixed
30 s while every other call honoured `--timeout=`. A slow subject was reported as
"initialize did not answer" even when the operator had explicitly raised the ceiling - S3, repeated.

## A race has a distribution, not a verdict

`--repeat=N` (default 1) runs the repeat-prone probes N times; `--repeat-probes=` chooses which
(default `concurrent`, the only probe observed to be unstable). The verdict is the mode, the tally
is printed, disagreement is recorded as `unstable`, and a tie breaks toward the worse outcome so an
unstable subject is never rounded up:

```
PASS,PASS,PASS             -> PASS     {'PASS': 3}
FAIL,FAIL,FAIL,FAIL,PASS   -> FAIL     {'FAIL': 4, 'PASS': 1}   unstable
PASS,FAIL                  -> FAIL     {'PASS': 1, 'FAIL': 1}   unstable  (tie breaks to worse)
PASS,PASS,FAIL             -> PASS     {'PASS': 2, 'FAIL': 1}   unstable
UNKNOWN,UNKNOWN,PASS       -> UNKNOWN  {'UNKNOWN': 2, 'PASS': 1} unstable
```

## F1 is withdrawn: memento does not lose concurrent writes here

F1 said memento deadlocks under concurrent writers - five runs, four failures. It does not
reproduce:

```
20 writes x 2 writers, 5 attempts    -> PASS 5/5    61.1s
50 writes x 2 writers, 3 attempts    -> PASS 3/3   150 acknowledged writes, all survived   37.7s
```

What differs is not the server. Same version, and the store file is **byte-identical** to the one
measured for F4 (4,308,992 bytes). What differs is the machine:

```
                        then      now
initialize              3.07s     0.60s
create_entities        13.21s     3.67s
add_observations        0.55s     0.06s
read_graph              0.05s     0.00s
search_nodes            1.33s     0.07s
re-initialize           3.1s      1.23s
a fresh store           4.3 MB    4,308,992 bytes
```

F1's failure signature began with **"did not answer within 60s"** - the ceiling was 60 s in those
runs. memento does not lose an acknowledged write; under contention it stops answering **inside the
caller's patience**, and the harness then wrote into a process it had already killed, which is what
produced `[Errno 22] Invalid argument` and `I/O operation on closed file`.

The corrected finding is narrower and more useful: memento's concurrency failure is a **latency
cliff, not a data-loss race**. It belongs next to F4, not next to F3. It is still a defect worth
reporting - a fresh write costs 3.7 s here and 13.2 s on a loaded machine, and agent runtimes
commonly cap a tool call at 10-30 s - but "memento loses writes" was wrong and is withdrawn.

This is the first claim in this document that did not survive re-testing. It is also the reason the
suite records `--timeout` and the machine's behaviour alongside a verdict: a number measured on a
loaded machine is a number about the machine.

## F4's store size was wrong by a factor of the record count

"A fresh store is 4.3 MB after one entity, because of the sqlite-vec index" is true and misleading.
Measured at four sizes:

```
  1 entities     4308992 bytes
  5 entities     4308992 bytes
 20 entities     4308992 bytes
 50 entities     4308992 bytes
```

Byte-identical every time. The space is preallocated **once per store**, not once per record. So it
is a fixed 4.3 MB floor rather than unbounded growth, which is a materially different claim: a store
that grows 4 MB per record would be disqualifying for any long-lived agent, and this is not that.
Corrected.

## The matrix, re-measured

```
subject                  adapter   isol  ack   restart f_field f_record concurrent large
server-memory 1.0.0      reference PASS  PASS  PASS    FAIL    PASS     PASS       PASS
memento 0.7.0            memento   PASS  PASS  PASS    PASS    PASS     PASS(3x)   UNKNOWN
memdb 1.4.0              manifest  PASS  PASS  PASS    PASS    PASS     PASS       PASS
memory-mcp-1file 0.9.2   auto      FAIL  PASS* PASS*   UNKNOWN UNKNOWN  UNKNOWN    UNKNOWN
```

`*` qualified by the failed isolation precondition - those PASSes describe leaked state.

memento's `large_record` is UNKNOWN rather than FAIL for the honest reason: the write never returns,
so nothing was observed to be lost. `foreign_field` and `foreign_record` remain UNKNOWN for
`memory-mcp-1file` because no store is declared for it - and it should not be declared, because that
subject is out of scope until it can be isolated at all.

## What six self-bugs have in common

Five of the six were a probe reporting a **false FAIL** on a working server, and the sixth was a
false PASS. The false FAILs came from the same mistake each time: the harness assuming something
about the subject that was not true - that a reader's name says what it does, that a tag is content,
that a colon is a separator, that a store is JSON Lines, that a file exists because a path was
declared. The false PASS came from the mirror image: assuming that a returned result means the work
was done.

Both directions are the same error, and it is not about memory servers at all. It is that a claim
about behaviour has to be **checked against something the claimed system does not control**, and
every one of these bugs was a place where the harness checked against its own assumption instead.

## F2 holds, and is now characterised instead of just failed

F2 said memento cannot complete a 5,000-character write in 150 s. Re-swept at every size, fresh store
per point:

```
     chars    seconds  result
       100      17.24   ok
      1000      18.68   ok
      2000      18.63   ok
      3000      30.39   ok
      4000      24.71   ok
      5000      31.31   ok        <- once
      5000     155.38   hung
      5000     155.71   hung
      5000     156.28   hung
      6000     155.67   hung
     10000     153.21   hung
     25000     153.65   hung
     50000     154.52   hung
    100000     153.71   hung
```

The boundary is between 4,000 and 5,000 characters, and above it memento has **three** behaviours
rather than one:

```
create_entities refused: Failed to allocate memory    2.72s  explicit, correct, fast
tools/call did not answer within 150s                155.38s  hangs
initialize did not answer within 30s                  30.05s  never starts
```

The first line is only visible because of the `ToolRefused` fix earlier in this addendum. Before it,
a fast explicit "Failed to allocate memory" was read as a *successful write whose result happened to
be a sentence* - the exact false PASS that fix was written for, met in the wild within the hour.

The non-determinism is the subject's, not the harness's: the same size on the same machine, back to
back, completed once and hung three times. It is an allocation failing at a boundary, and the three
symptoms are the three places that failure can surface. This is precisely the case `--repeat`
exists for.

The reference server writes 100,000 characters in 0.7 s. The gap at the top of the tested range is
about five orders of magnitude and it is unchanged.

## What is still missing

1. **A leaderboard is still not honest to publish.** Four subjects, one of them out of scope, is not
   a sample. The manifest lowers the cost of adding one to thirteen lines, which is the point, but
   the number is not yet worth printing.
2. **A write that never returns is not an UNKNOWN.** When a subject hangs, the probe cannot tell "I
   could not measure this" from "it did not acknowledge", and reports UNKNOWN. memento's
   `large_record` is the live example: the subject is unambiguously failing to store a large record,
   and the suite says we do not know. The three-state verdict is right in principle and still too
   coarse here.
3. **`concurrent` conflates two failures for the same reason.** "The write was lost" and "the write
   never returned" both print FAIL. The evidence line distinguishes them; the verdict does not.

---

# Addendum 4: eight subjects, and a verdict that depends on the clock

Breadth was the stated bottleneck. It is now eight subjects, seven of them measurable, and the
result is a matrix rather than a winner.

## The matrix

```
subject                  isol     ack      restart  field    record   conc     large    ceil
--------------------------------------------------------------------------------------------
server-memory 1.0.0      PASS     PASS     PASS     FAIL     PASS     PASS     PASS      60s
server-memory 2.0.0      PASS     PASS     PASS     FAIL     PASS     PASS     PASS      60s
memento 0.7.0            PASS     PASS     PASS     PASS     PASS     PASS     FAIL     180s
memdb 1.4.0              PASS     PASS     PASS     PASS     PASS     PASS     PASS      60s
memory-lean 1.5.0        PASS     PASS     PASS     FAIL     FAIL     PASS     PASS      60s
mcp-knowledge-graph 1.3.2 PASS    PASS     PASS     PASS     FAIL     FAIL     PASS      90s
zenbrain 0.3.0           PASS     PASS     PASS     PASS     PASS     PASS     PASS      60s
memory-mcp-1file 0.9.2   FAIL     (PASS)   (PASS)   (UNKNOWN)  (UNKNOWN)  (FAIL)   (UNKNOWN)   60s
```

Parenthesised cells belong to the subject that failed `isolation`; they describe leaked state and
are not publishable on their own. `python matrix.py` regenerates this from `subjects.json`, and
every cell traces back to a file under `results/`.

## What the matrix says that a ranking could not

Three of the seven measured subjects keep everything asked of them. Four do not, and no two of the
four fail the same way:

- **server-memory** (both versions) drops a field another tool added, and keeps everything else.
- **memory-lean** drops the field *and* the whole foreign record.
- **mcp-knowledge-graph** drops the foreign record by **refusing to serve**: a second tool's line in
  the store makes the server fail to parse its own file, so the next call returns
  `MCP error -32603: Unexpected non-whitespace character after JSON`.
- **memento** keeps everything and then declines to answer in time.

A single rank would have put memdb and zenbrain first and memento last, which is the same as saying
nothing about *what* is wrong with memento.

## server-memory 2.0.0 shipped the same defect

The flagship server published a new major version during this work, so it is installed under an
alias and run against the **pinned 1.0.0 verdicts**:

```
$ python harness.py --adapter=reference --cmd="node node_modules/memory-server-next/dist/index.js" \
      --expect=expected.json
...
verdicts match expected.json
```

No drift. The 2.0.0 release migrated the store from `memory.json` to `memory.jsonl` and still silently
drops a field it does not model on the next write. That is the difference between recording a number
and watching one, and it is the first thing in this project that a third party could have predicted
from the harness alone.

## memory-lean is worse than the server it imitates

Its tool vocabulary is byte-for-byte the reference server's (`create_entities`, `search_nodes`,
`read_graph`), and it is marketed as the token-lean alternative. It fails one probe the reference
passes:

```
foreign_field    FAIL   the extra field was silently dropped by the next write
foreign_record   FAIL   the unmodelled record was silently removed by the next write
```

The reference server at least appends unknown lines and leaves them alone. memory-lean rewrites the
file from its own model and takes everything else with it. It also caps a single observation at 300
characters, which the size probe now measures rather than complains about:

```
large_record     PASS   wrote 195 characters; 195 are still in the store;
                        refused at 100000 by its own limit, so 195 was measured
```

## mcp-knowledge-graph loses most of its writes

The concurrency probe runs two servers against one store and counts how many acknowledged writes
survive. Across five attempts: **4, 5, 10, 12 and 13 of 20**. Never all of them, never close.

```
concurrent       FAIL  [unstable] 10 of 20 acknowledged writes survived two servers on one store;
                                  12 of 20 ...; 13 of 20 ...
```

Both servers answer `ok` to every write. A read-modify-write store with no locking will do exactly
this, and the caller is told nothing. This is the defect the project exists to find, found in a
published package whose own description sells it as "persistent memory for AI models".

## The ceiling is part of the verdict

memento was measured twice on the same machine on the same day. At a 60 s ceiling:

```
concurrent       FAIL  10 write(s) failed outright: ['w1-0: tools/call did not answer within 60s',
                       'w1-1: [Errno 22] Invalid argument', ...]   {FAIL: 2, PASS: 1}
large_record     FAIL(no-ack)  tools/call did not answer within 60s
```

At 180 s, on the same probe and the same subject:

```
concurrent       PASS  20 of 20 acknowledged writes survived two servers on one store
```

Nothing about memento changed. The clock changed. So the matrix carries a `ceil` column, because a
verdict is a claim about a subject **under a stated ceiling**, and Addendum 3 already withdrew one
claim that was really a claim about a loaded machine.

The two runs are kept side by side under `results/` precisely so this cannot quietly disappear.

## Three verdicts became more honest

The three-state verdict was too coarse in one direction and too generous in another, and both are
now fixed:

| what happened | before | now |
|---|---|---|
| the subject never answered | UNKNOWN | `FAIL(no-ack)`, with the ceiling in the evidence |
| the subject rejected the call | counted as an acknowledgement | `FAIL(refused)` |
| the subject returned a protocol error | UNKNOWN (harness error) | `FAIL(subject-error)` |
| the probe cannot be expressed here | UNKNOWN | UNKNOWN, and it still means exactly that |

The distinction that matters is between *we could not measure this* and *the subject did not do the
thing*. Only the first is UNKNOWN. memento's large record is the live example: the subject
unambiguously fails to store 100,000 characters, and reporting that as "we do not know" was the
suite understating its own finding.

The size ladder also had to reach further. memory-lean's cap is 300 characters; stopping the search
at an eighth of the requested size reported it as unable to store anything at all. Ten halvings
reaches ~1/1000 and covers the ranges seen so far.

## What each manifest had to state

Six of the eight subjects are described by a manifest, and the total is under eighty lines.

| subject | the one thing a generic tool could not work out |
|---|---|
| memdb | there is no name column; the name is folded into the row text, so records are found by containment |
| memory-lean | nothing beyond the store variable and a name key |
| mcp-knowledge-graph | it finds its store by walking up for a project marker and otherwise falls back to its own package directory, so `--memory-path` has to be part of the command |
| zenbrain | one store method fans out across six tables by content type; four differently shaped writes all landed in `learned_facts`, which is why that table is declared |
| memento | the control: also run through the hand-written adapter, and both agree |

That last row is the one that makes the rest trustworthy. When the declaration and the hand-written
code disagree, one of them is wrong, and `manifest_control.py` says so.

## Still not a leaderboard, and now the reason is specific

Eight subjects is a sample, not a survey. But the sharper problem is that **the matrix does not rank
anything**: five of the seven measured subjects pass five or more of seven probes, and the useful
information is entirely in *which* probe fails. Sorting that into a single number would destroy the
finding — the same mistake the project is built to catch in other people's benchmarks.

What is still missing is a second axis. Retention and concurrency are covered; retrieval quality,
latency and cost are not, and a memory system that keeps everything and finds nothing would score
7/7 on this matrix. `retrieval.py` and `retrieval_cases.json` exist for that but are not wired into
the matrix.

---

# Addendum 5: the other axis — kept is not found

The last addendum ended by naming the hole: *a memory system that keeps everything and finds nothing
would score seven of seven.* That is now closed, and the closing found the biggest result in the
project so far.

## The hole was real, and so was the answer

A new probe, `findable`, asks the weakest possible retrieval question: **does a record come back for
the name it was stored under?** Eight records, eight queries, each query the record's own handle, run
on a server that never saw the writes. Failing it is not a ranking disagreement; it is a memory that
cannot be read back at all.

It is a floor, not a benchmark. Passing it says a memory can be reached; it says nothing about
answering questions — which is what the second axis below is for.

## Two bugs in the probe before it could find anything

Both were mine, and both were false FAILs on working servers.

1. **The names shared a token.** The first version used `findable-0` … `findable-7`. Any tokeniser
   splits that into "findable" plus a digit, so every record matched every query, three filled the
   top three, and memdb was reported as unable to find *any* of its own records. Eight disjoint word
   pairs fixed it: `zephyr-quartz`, `ember-lattice`, and so on.
2. **A query was answered by a reader.** `AutoAdapter` binds its reader first, because five probes
   only need "give me everything", and `read_graph` wins that race on every subject that has one.
   `search()` then fell back to that reader and **silently discarded the query**, returning the whole
   graph in file order. memory-lean was reported as finding 3 of 8 when its own `search_nodes`
   answers "1 match" perfectly. A query now requires a search tool or the probe reports UNKNOWN.

That is seven self-bugs. Both of these were caught by disbelieving the first result and going to the
raw response — which remains the only method that has ever worked.

## The finding: memento's search does not search

memento fails `findable` — 5 of 8 — and the evidence says something sharper than a miss count:

```
query 'zephyr-quartz'             -> ['cobalt-thistle', 'ember-lattice', 'halcyon-basalt']
query 'xylophone-nonexistent-zzz' -> ['cobalt-thistle', 'ember-lattice', 'halcyon-basalt']
query ''                          -> ['cobalt-thistle', 'ember-lattice', 'halcyon-basalt']
```

The same three entities, alphabetically, for a matching name, for a string that appears in no record,
and for the empty query. The reference server answers the same three questions with `['zephyr-quartz']`,
`[]` and `['zephyr-quartz', 'ember-lattice', 'cobalt-thistle']` respectively.

The probe now says so in its own words: *"every query returned the same 3 records regardless of what
was asked - the search does not discriminate."* A search that returns the whole store is a listing
wearing a search's clothes, and a caller has no way to tell from the outside except by asking
something it knows is absent.

## The second axis

`retrieval.py` runs 12 records and 12 questions against a cold server and reports hit@1 and hit@3 on
two bands: questions that share vocabulary with their answer, and questions that do not.

```
subject                  easy h1/h3   hard h1/h3   all h1/h3
control 1.0.0            6/6 6/6      5/6 6/6      11/12 12/12
server-memory 1.0.0      0/6 0/6      0/6 0/6       0/12  0/12
server-memory 2.0.0      0/6 0/6      0/6 0/6       0/12  0/12
memento 0.7.0            0/6 1/6      1/6 3/6       1/12  4/12
memdb 1.4.0              6/6 6/6      1/6 1/6       7/12  7/12
memory-lean 1.5.0        3/6 3/6      0/6 0/6       3/12  3/12
mcp-knowledge-graph 1.3.2 0/6 0/6     0/6 0/6       0/12  0/12
zenbrain 0.3.0           6/6 6/6      4/6 5/6      10/12 11/12
memory-mcp-1file 0.9.2   6/6 6/6      5/6 6/6      11/12 12/12
```

This is a score, not a verdict: "relevant" is a judgement and "returned" is a fact, so it is reported
as a number and never as PASS/FAIL.

## The two axes are close to inverted

This is the result. Ranked by retention, the order is control, memdb, zenbrain, then everybody else.
Ranked by retrieval, the order is memory-mcp-1file, control, zenbrain, memdb, and the two servers most
people actually use come last, at **zero**.

- **`@modelcontextprotocol/server-memory`, both versions** — 7 of 8 conformance probes pass; it
  cannot answer a single one of the twelve questions.
- **`memory-mcp-1file`** — 12 of 12 on retrieval, the best in the set, and it is the one subject
  excluded from the conformance table for leaking state between stores.
- **memento** — keeps everything asked of it except large records, and its search is a listing.

A single number would have to choose between these, and there is no defensible way to choose.

## The reference server cannot answer a question

Its 0/12 is not a harness artefact. `search_nodes` matches the query as a **literal substring**:

```
query 'postgres staging port'          -> []
query 'postgres'                       -> ['rec-port']
query 'deployment key rotates monthly' -> []
query 'deployment key'                 -> ['rec-key']
```

That is a defensible implementation of a tool called `search_nodes`, and it is why the question must
be asked: an agent that asks "how many machines do we run" gets nothing, and has no way to know
whether the memory is empty, broken, or merely literal.

## Two more problems the phase exposed

**The precondition was flaky.** memdb failed `isolation` once in the middle of a matrix run and
passed on fifteen attempts either side of it. A one-off FAIL there parenthesises every other verdict
for that subject; a one-off PASS would publish the verdicts of a leaking one. `isolation` is now
repeated whenever repeats are on, so a flake surfaces as `[unstable: ...]` instead of silently
choosing a story.

**The positive control was not a control.** `ControlAdapter` had no store surface, so the two
foreign-data probes came back as harness errors — a server with a good reputation answering
"unknown". It inherits the JSON Lines store backend now and scores **8/8**, which is what a control
has to do to mean anything.

## The matrix, with the control in it

```
subject                  isol   ack    restart find   field  record conc   large   ceil
control 1.0.0            PASS   PASS   PASS    PASS   PASS   PASS   PASS   PASS     60s
server-memory 1.0.0      PASS   PASS   PASS    PASS   FAIL   PASS   PASS   PASS     60s
server-memory 2.0.0      PASS   PASS   PASS    PASS   FAIL   PASS   PASS   PASS     60s
memento 0.7.0            PASS   PASS   PASS    FAIL   PASS   PASS   PASS   FAIL    180s
memdb 1.4.0              PASS   PASS   PASS    PASS   PASS   PASS   PASS   PASS     60s
memory-lean 1.5.0        PASS   PASS   PASS    PASS   FAIL   FAIL   PASS   PASS     60s
mcp-knowledge-graph 1.3.2 PASS  PASS   PASS    PASS   PASS   FAIL   FAIL   PASS     90s
zenbrain 0.3.0           PASS   PASS   PASS    PASS   PASS   PASS   PASS   PASS     60s
memory-mcp-1file 0.9.2   FAIL   (PASS) (PASS)  (PASS) (UNKNOWN) (FAIL) (FAIL) (UNKNOWN) 60s
```

The control passing all eight is the claim that every probe *can* pass, which is the difference
between a conformance suite and a set of accusations.

## What this is still not

- **Twelve questions is a small corpus.** It is enough to separate 12/12 from 0/12 and not enough to
  rank 11/12 against 10/12. The bands are coarse on purpose; the spread inside a band is noise.
- **Retrieval has no ground truth beyond the 12 cases.** It measures whether one specific relevant
  record came back, not whether the answer was any good.
- **The axes are unweighted.** Nothing here says how much retention is worth relative to retrieval,
  and that is a judgement for whoever is choosing a memory server, not for the harness.

What the suite can now say is specific and checkable: *this server keeps what it acknowledges and
cannot find it again; that one finds everything and does not keep it.* Two sentences, both
falsifiable, neither of which was available from any published comparison.

---

# Addendum 6: asking questions that have no answer

Twelve questions could separate 12/12 from 0/12 and nothing finer, and every subject was measured
only on **recall** — how often the right record came back. That left a hole big enough to drive a
listing through: a system that answers every question with its whole store has perfect recall and is
not a search. The corpus is now thirty-six records and thirty questions in four bands, and the two
new bands are what make the numbers mean something.

## The four bands

- **easy** — the question contains words that appear in the answer.
- **hard** — a paraphrase that shares almost nothing with the wording of the answer.
- **adversarial** — the answer is present and a **near duplicate competes for the same words**. There
  is a staging port and a production port; two keys, one of which lives in hardware; three hosts, one
  of which is the always-on collector. Getting *a* plausible record is not getting the right one.
- **absent** — nothing in the store answers the question, so the correct behaviour is to return
  nothing at all.

The absent band exists because of the project's own vocabulary. A memory that always answers is a
memory that **cannot say "I don't have that"** — the same defect as a conformance probe that reports
FAIL when it means "I could not check". Returning three unrelated records to "what is the office wifi
password" is a confident wrong answer, and only a question with no answer can detect it.

## The result

```
subject                  easy    hard    adver   all h1   all h3   noans   95%
------------------------------------------------------------------------------
control 1.0.0            8/8     0/8     5/8     13/30    13/30    0/6     8-18
server-memory 1.0.0      0/8     0/8     0/8      0/30     0/30    0/6     0-3
server-memory 2.0.0      0/8     0/8     0/8      0/30     0/30    0/6     0-3
memento 0.7.0            2/8     2/8     4/8      2/30     8/30    6/6     4-13
memdb 1.4.0              7/8     0/8     0/8      1/30     7/30    6/6     4-12
memory-lean 1.5.0        6/8     0/8     0/8      6/30     6/30    0/6     3-11
mcp-knowledge-graph 1.3.2 0/8    0/8     0/8      0/30     0/30    0/6     0-3
zenbrain 0.3.0           8/8     7/8     7/8     20/30    22/30    6/6     17-26
memory-mcp-1file 0.9.2   8/8     7/8     7/8     20/30    22/30    6/6     17-26
```

`noans` is the number of questions with no answer that were **answered anyway**. Zero is right.

## Two failure modes that score exactly the same

This is the most interesting thing the band structure produced. Put the reference server and memento
side by side and a paired test cannot separate them:

```
$ python compare.py memento server-memory-1.0.0
  correct for both          0
  correct for neither      16
  only memento correct      8
  only server-memory        6
  exact McNemar p = 0.7905  -> not separated by this corpus
```

They are **opposites**. `server-memory` answers nothing — 0 of 30 answerable questions, and correctly
silent on all 6 unanswerable ones. memento answers everything — 8 of 30 right, and it speaks on all 6
questions that have no answer. One is a memory that cannot find; the other is a listing that cannot
stop. On this corpus they come out identical, and any single "retrieval score" would have declared
one of them the winner on a difference inside the noise.

## Intervals, and why the paired test is the better instrument

Independent 95% Wilson intervals are printed with each row because thirty questions is not many:

```
zenbrain         22/30   17-26
memdb             7/30    4-12
```

Those do not overlap, so that pair is separated on the marginals. But `zenbrain` 22/30 and `control`
13/30 give `17-26` and `8-18` — **overlapping by one**, and the marginal test would have to say
"inconclusive".

The marginals are the weaker test because they throw away the pairing. **Every subject answers the
same thirty questions**, so the right question is not "are these proportions different" but "on the
questions where they disagree, does one win more often than the other". That is McNemar, and it is
exact here:

```
$ python compare.py zenbrain memdb
  correct for both          7
  correct for neither       8
  only zenbrain correct    15
  only memdb correct        0
  exact McNemar p = 0.0001  -> separated
```

Fifteen discordant questions, fifteen to nothing. And the same instrument says the opposite about the
two best subjects:

```
$ python compare.py zenbrain memory-mcp-1file
  correct for both         20
  only zenbrain correct     2
  only memory-mcp-1file     2
  exact McNemar p = 1.0000  -> not separated by this corpus
```

So the corpus supports "zenbrain and memory-mcp-1file are the best retrievers here and indistinguishable
from each other; both are clearly better than memdb; the control at 13/30 is also clearly better than
memdb (12–0, p = 0.0005)". It does **not** support "zenbrain is better than the control", and the
matrix no longer invites that reading.

## What this does not fix

- **The corpus is authored by me.** The questions may share my vocabulary in ways I cannot see, and a
  system tuned on different data is not necessarily worse. The adversarial band is the strongest part
  because a distractor is hard to accidentally match, and the absent band is the most objective
  because "nothing" needs no judgement.
- **Thirty questions still separates ends, not middles.** The paired test recovers a lot of that, and
  the intervals say plainly when a gap is a coin toss.
- **No cost axis.** Latency and token cost are still unmeasured, and memento's 30-second answers are
  not free. A memory that is right and unusably slow is not a memory either.

## Files

```
retrieval_corpus.json  36 records in eight clusters, 30 questions in four bands
retrieval.py           four bands, per-band hit@1/hit@3, abstention count
matrix.py              second table, Wilson intervals, --report-only to re-render from saved reports
compare.py             paired comparison between two subjects, exact McNemar
```

`python matrix.py --report-only` re-renders both tables from the reports already under `results/`,
because a verdict is worth nothing if the table around it can only be produced by a twenty-minute run.

---

# Addendum 7: the bill

The last two addenda measured whether a memory keeps what it is given and whether it can find it
again. Neither measured what either of those costs, and a memory that is right and unusably slow is
not a memory — nor is one that answers a twenty-byte question with five kilobytes, whatever it calls
itself.

`cost.py` measures seven things per subject, once, in a quiet pass of its own:

```
subject                  startup  lst write write p50 search p50 resp B   amp   store B/rec
control 1.0.0               0.07s    0.01s    0.010s    0.000s     4175      x72          140
server-memory 1.0.0         0.56s    0.02s    0.007s    0.002s       39       x1          150
server-memory 2.0.0         0.64s    0.03s    0.008s    0.002s       39       x1          150
memento 0.7.0               0.58s    4.43s    0.120s    0.055s     1497      x26            0
memdb 1.4.0                 0.57s    0.04s    0.001s    0.002s     1028      x18        42848
memory-lean 1.5.0           0.10s    0.02s    0.003s    0.001s      164       x3          150
mcp-knowledge-graph 1.3.2   0.10s    0.02s    0.004s    0.002s       39       x1          150
zenbrain 0.3.0              0.34s    0.03s    0.001s    0.001s      663      x11        21424
memory-mcp-1file 0.9.2      0.66s    1.58s    0.028s    0.036s     4838      x83            -
```

`resp` is the median bytes the server actually sends back for one question; `amp` is that divided by
the size of the correct record, so answering by returning the whole store appears as a multiplier
rather than a shrug.

## The metric was wrong first, in the same way F4 was

The first version divided the store size by the record count and reported memento at **350,549 bytes
per record**. That number is real arithmetic and a false claim: memento's store is a fixed 4.3 MB
whatever it holds, so the division was measuring the preallocation floor as if it were growth — the
same mistake F4 was corrected for, made again in new code.

The fix is what makes the column mean anything: write fifteen records, measure, write fifteen more,
measure, and report the **marginal** between the two batches. The floor cancels. Memento's true
marginal cost is **zero bytes per record** — a store that pays its entire cost once and then stores
nothing for free — and memdb's is 42,848.

## A third inversion, and one marketing claim that passes

Read with the retrieval table, the cost numbers invert it again:

- **The cheapest subjects are silent.** `server-memory` and `mcp-knowledge-graph` cost 39 bytes per
  question — less than the size of the answer — because they return nothing. Efficiency is not a
  virtue when it is achieved by saying nothing, and the two tables have to be read together or the
  cheapest memory in the table looks like the best one.
- **The best retriever is the most expensive.** `memory-mcp-1file` answers 22 of 30 and sends thousands
  of bytes to do it, many times the size of the record it is looking for.
- **`memory-lean` is genuinely lean.** It calls itself token-lean and it is: 164 bytes per answer, an
  amplification of 3, the lowest of anything that answers at all, with one of the fastest startups in
  the set. That is the first marketing claim in this project that survived measurement intact.
- **`memento` pays seconds for the first write** and a tenth of a second for every one after it. An
  agent runtime that caps a tool call at 10–30 s does not notice this at three seconds; it noticed it
  at thirteen, which is what the withdrawn F1 was really about. Addendum 9 shows the cost is not even
  a fixed number.

The control costs thousands of bytes per question because it has no server-side search: it transfers
the whole store and filters locally. That is a fact about the control, reported rather than excused,
and it is a reminder that a small toy server is not automatically a cheap one.

## What this still is not

- **Cost is measured once here.** A single quiet pass is better than a timing taken while nine other
  subjects run, and it is not a distribution. Addendum 9 fixes this.
- **Bytes are not tokens.** They are what the transport carries and what can be counted exactly,
  which is why they are used; a token estimate would be a guess wearing a number's clothes.
- **No end-to-end cost.** The bill an agent actually pays is per session — many writes, many reads,
  many misses — and this measures one of each.

## Files

```
cost.py                seven measurements, four rules, two-batch marginal store growth
matrix.py              third table; --cost-only takes timings in a pass of their own
results/*-cost.json    every number above, per subject
```

    python matrix.py --cost-only     # take the timings in a quiet pass
    python matrix.py --report-only   # re-render all three tables from what is saved

---

# Addendum 8: repeating the measurement, and a correction to Addendum 7

Addendum 7 ended with a warning: the retrieval table had moved between two runs of the matrix on the
same machine on the same day — zenbrain 22/30 and then 24/30 — and `retrieval.py` had no way to say
which of those was the measurement and which was the weather. It now does. The answer is that there
was no weather.

## What repeating showed

Each subject's retrieval is now the whole experiment run three times: a fresh store, thirty-six
records, a cold start, and all thirty questions, then the per-question majority.

```
subject                  easy    hard    adver   all h1   all h3   noans   runs      95%
control 1.0.0            8/8     0/8     5/8     13/30    13/30    0/6     13-13     8-18
server-memory 1.0.0      0/8     0/8     0/8      0/30     0/30    0/6     0-0       0-3
server-memory 2.0.0      0/8     0/8     0/8      0/30     0/30    0/6     0-0       0-3
memento 0.7.0            2/8     2/8     4/8      2/30     8/30    6/6     8-8       4-13
memdb 1.4.0              7/8     0/8     0/8      1/30     7/30    6/6     7-7       4-12
memory-lean 1.5.0        6/8     0/8     0/8      6/30     6/30    0/6     6-6       3-11
mcp-knowledge-graph 1.3.2 0/8    0/8     0/8      0/30     0/30    0/6     0-0       0-3
zenbrain 0.3.0           8/8     8/8     7/8     20/30    23/30    6/6     23-23     18-26
memory-mcp-1file 0.9.2   8/8     7/8     7/8     19/30    22/30    6/6     22-22     17-26
```

**Every run column is a single number.** Not one subject moved by so much as one question across
three complete repetitions of the experiment, on nine subjects. The measurement is deterministic.

## The correction

Addendum 7 said the retrieval number was not reproducible to the question, and cited 22/30 then
24/30. That inference was wrong, and the way it was wrong is worth more than the fix.

The two runs it compared were taken while the harness itself was changing: the `search_text` surface
was added between them, which is a change to the code path that produces the number. A difference
observed across two runs in which other things also changed is not evidence of nondeterminism — it is
evidence that other things changed. I attributed it to the subject's stability without having held
the instrument still, which is the same mistake as measuring a write on a loaded machine and calling
it the server's latency.

Verified properly:

```
invocation 1: hit@1 20/30  hit@3 23/30
invocation 2: hit@1 20/30  hit@3 23/30
invocation 3: hit@1 20/30  hit@3 23/30
invocation 4: hit@1 20/30  hit@3 23/30
```

Four separate process invocations, and three in-run passes, all identical. The current value is 23,
and it is 23 every time.

The three recorded values — 22, 23, 24 — all sit inside the published Wilson interval of 18–26, so
nothing in Addenda 5 or 6 changes. What changes is the reason given for the interval.

## The two error bars are different, and both are kept

- **runs** — min and max of the same experiment repeated three times. This is *measurement* error: how
  much the number moves when nothing about the question changes. It is zero here.
- **95%** — the Wilson interval for the majority result. This is *sampling* error: how much a
  different thirty questions might move the score. It is plus or minus about four.

Zero measurement error and four counts of sampling error is a good place for an instrument to be. It
means the number is repeatable and its precision is limited only by the size of the corpus, which is a
problem you can fix by writing more questions rather than by buying quieter hardware.

## What the repeated result does not change

The three comparisons that carry the argument are identical to Addendum 6:

```
zenbrain vs memory-mcp-1file    2-1 discordant, exact McNemar p = 1.0000  -> not separated
zenbrain vs memdb              16-0 discordant, exact McNemar p < 0.0001  -> separated
memento    vs server-memory     8-6 discordant, exact McNemar p = 0.7905  -> not separated
```

The middle one is now 16–0 rather than 15–0, because the majority over three runs resolved one
previously unstable question in zenbrain's favour. The conclusion is unmoved: two subjects are the
best retrievers here and indistinguishable from each other, and one of the two worst is statistically
identical to the other.

## What is still not repeated

The **cost** table. Every timing in Addendum 7 is a single pass, and the same discipline applies: a
number taken once cannot distinguish the subject from the moment. `store B/rec` and the byte counts
are exact and do not need repeating; the four timing columns do. Addendum 9 takes that up.

---

# Addendum 9: repeating the bill

Addendum 8 ended by noting that the cost timings were still a single pass each. They are now three,
and the cost table is the only one of the three axes where repeating changed the answer.

```
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

## memento's first write is not 4.5 seconds. It is 2.3 to 14.4 seconds

Three passes, same machine, same build:

```
first_write   2.286  -  14.383     (median 4.54)
startup_p50   0.697  -   1.712
write_p50     0.086  -   0.293
search_p50    0.038  -   0.170
```

A six-fold spread on the number that decides whether an agent can use the subject at all. Addendum 7
reported 4.43 s, which was the median of that spread presented as if it were a point. The correct
statement is narrower and worse for the vendor: **memento's first write into a new store usually
takes a few seconds and sometimes takes fourteen.** An agent runtime that caps a tool call at 10 s
does not face a fixed cost it can budget for; it faces a coin flip. That is the same fact as the
withdrawn F1 and the ceiling lesson, arriving from the other direction — and it took repeating the
measurement to see it.

## The bytes were not exact, and I said they were

Addendum 8 closed with *"Bytes and store sizes are exact and are not repeated."* The count is exact;
the response is not. Repeating shows `memory-mcp-1file` sending **1,766 to 1,974 bytes** across three
passes for the same thirty questions — and 4,838 on an earlier run. The measurement of what a memory
costs per question is itself a distribution, and every byte figure in the previous addendum was run
zero.

## A ratio needs something to divide by

The first version of the variability column reported memdb at **200%**. Memdb's write takes one
millisecond and moved to one millisecond; as a percentage of its own median, that is 200% and it
means nothing. A floor was added: timings whose median is under 20 ms are excluded from the figure and
their absolute ranges are left in the JSON where they belong. Six of the nine subjects are now 0%,
which is the honest answer for a millisecond-scale operation on a machine that is otherwise idle.

## The repeat was not repeating the thing that varies

Discovery-bound adapters cache which of a server's tools they bound. Three passes shared one adapter
instance, so the binding was chosen once and held fixed — the instrument was repeating the experiment
while holding the conclusion still. `AutoAdapter.reset()` now clears the binding before each pass.

Verified: it changed nothing measurable. The binding is stable across rediscoveries for every subject
tested, so the run-to-run drift in `memory-mcp-1file`'s numbers is not the adapter choosing
differently — it is the subject's own state, which it keeps somewhere the harness cannot clear. That
is the same fact S5 recorded about it, showing up again in the cost column, and it is why that subject
is marked out of scope rather than graded.

The fix was still worth making. "The adapter is stable" is a claim, and it had been assumed rather
than tested for three addenda.

## What is now measured, and what is still not

Every number in `MATRIX.md` carries an error bar of the kind it needs:

| axis | error bar | measures |
|---|---|---|
| conformance | `--repeat=`, modal verdict, `unstable` flag | whether the subject gives the same answer twice |
| retrieval | `runs` (measurement) and `95%` (sampling) | whether the experiment repeats, and how much thirty questions can move |
| cost | `vary` per subject, ranges in the JSON | whether the machine was the same shape twice |

Still missing: the conformance probes are repeated only where instability was *observed*, not
everywhere; there is no end-to-end session cost; and no axis measures what a memory is worth, only
what it does.

---

# Addendum 10: repeating every probe

Addendum 9 closed by noting the last place where stability was *assumed* rather than measured: the
conformance probes were repeated only where instability had been **observed** — `concurrent` and
`isolation` — and the other six were reported from a single attempt each. That is the same
assumption that had already been retracted twice on the other two axes, so it was the next thing to
test.

`--repeat-probes=` now defaults to **all**. Asking for repeats and then not repeating most of the
probes is a way of believing a number rather than checking it; narrowing the list is still possible,
and is now an explicit decision to save time rather than the default.

## The result

Nine subjects, eight probes, three attempts each: **72 verdicts and 216 executions.**

```
subject                  isol     ack      restart  find     field    record   conc     large
control 1.0.0            PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS
server-memory 1.0.0      PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS
server-memory 2.0.0      PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS
memento 0.7.0            PASS     PASS     PASS     FAIL     PASS     PASS     PASS     FAIL
memdb 1.4.0              PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS
memory-lean 1.5.0        PASS     PASS     PASS     PASS     FAIL     FAIL     PASS     PASS
mcp-knowledge-graph 1.3.2 PASS    PASS     PASS     PASS     PASS     FAIL     FAIL     PASS
zenbrain 0.3.0           PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS
memory-mcp-1file 0.9.2   FAIL     (PASS)   (PASS)   (PASS)   (UNKNOWN)  (UNKNOWN)  (FAIL)   (UNKNOWN)
```

**Not one verdict on a measurable subject moved.** Seven subjects, eight promises each, three
attempts apiece: every one is deterministic. The entire conformance table is reproducible, and it is
the only one of the three axes where that turned out to be true without a caveat.

## The one row that did move

Exactly one of the 72 verdicts was flagged `unstable`, and it belongs to the subject that was already
out of scope:

```
memory-mcp-1file  restart  PASS  {"PASS": 2, "FAIL": 1}  over 3 runs
  three writes across three server lifetimes; read back
  ['alpha', 'isolation-marker-alpha', 'restart-0', 'restart-1', 'restart-2']
  [unstable: FAIL 1, PASS 2 of 3 runs]
```

The evidence names `alpha`, written by a *different probe* in a *different store*. So the flakiness
is not incidental: it is a downstream symptom of the isolation failure. A subject that never knows
which store it is talking to cannot be counted on to restart into the same one, and the probe that
notices this is not the one that is looking for it.

That makes the exclusion of `memory-mcp-1file` doubly justified — it fails the precondition, and
under that failed precondition it is also unstable — and it is the strongest argument in the project
for `isolation` running first. A suite that graded this subject's other seven probes would have
published seven green cells describing leaked, flaky state.

## What this cost

The matrix now takes roughly twice as long. That is the entire price of replacing an assumption with
a measurement, and it is the right trade: a verdict that cannot be reproduced is not a verdict.

## The pattern, three times over

Three separate measurements in this project were believed stable on the strength of one observation,
and all three were tested in the end:

| axis | what was assumed | what was true |
|---|---|---|
| cost timings | a single quiet pass is a number | memento's first write spans 2.3–14.4 s across passes |
| retrieval | one run is the score | deterministic — but only provable after four invocations and three in-run passes |
| conformance | six probes looked stable, so they are | true for seven subjects, false for the eighth, and only the eighth mattered |

The lesson is not "always repeat". It is that **stability is a property of an individual measurement,
not of a benchmark**, and it has to be established per axis because the mechanisms are unrelated: a
timing varies with the machine, a search varies with the tool binding and the subject's own state,
and a probe varies with a precondition another probe happens to be breaking.

## What is still not measured

Nothing on these three axes is now reported from a single observation without saying so. What
remains is not more repetition but more axes: there is no end-to-end session cost, no measurement of
what a memory is worth rather than what it does, and the corpus is still thirty questions written by
the person who wrote the harness.

---

# Addendum 11: breadth, and what it actually costs

The plan was eight measured subjects to fifteen. It reached eleven: ten measured and one out of
scope. That yield is the finding, and it says more about the state of this ecosystem than another
green column would.

## What was tried

Seven packages installed and triaged with a new `triage.py`, which starts each one, proposes a write,
and reports every file it leaves behind along with the tables of any SQLite store:

| package | outcome |
|---|---|
| `statecore-mcp` 1.0.0 | **added** - SQLite, local once `--data` points at the run's directory |
| `@izumisy/mcp-duckdb-memory-server` 1.1.10 | **added** - DuckDB, local by default |
| `crbro-memory` 2.10.0 | rejected - works, but writes to `~/.crbro` and offers no way to say otherwise |
| `rag-memory-epf-mcp` 6.4.1 | rejected - its `sources` field is an array of objects and the binder fills arrays with strings |
| `@hasna/mementos` 0.17.10 | never starts over stdio from a clean install |
| `aimem-mcp` 0.3.0 | never starts (declares a Node <21 engine) |
| `toon-memory` 4.3.5 | ships an installer rather than a server; needs an interactive `init` first |

Two of seven added. The manifest makes *declaring* a subject fourteen lines; it does not make
*understanding* one cheap, and that is where the hours went.

## Two properties the triage surfaced

**Two subjects wrote to the user's home directory by default.** `statecore-mcp` created
`~/.statecore/statecore.db` and `crbro-memory` created `~/.crbro` the first time each was started.
Both were removed. This is worth stating plainly: a memory server that defaults to the home directory
is one an agent shares with every other agent on the machine, silently. It is the same defect as
`memory-mcp-1file`, and it is the single most common way a subject fails the isolation precondition.

**DuckDB cannot be shared by two processes at all.** The concurrency probe does not report lost
writes for it; both servers answer `ok` and the second one cannot open the file:

```
concurrent  FAIL  10 write(s) failed outright:
                  "create_entities refused: Cannot read properties of null (reading 'connect')"
```

That is a third distinct concurrency failure mode, after memento's latency cliff and
mcp-knowledge-graph's silent loss.

## The new subjects, and the one number that matters

```
subject                  isol   ack    restart find   field   record  conc   large   resp B  amp
statecore-mcp 1.0.0      PASS   PASS   PASS    FAIL   PASS    PASS    FAIL   UNKNOWN   5710   x98
mcp-duckdb-memory 1.1.10 PASS   PASS   PASS    PASS   UNKNOWN UNKNOWN FAIL   UNKNOWN    210    x4
```

**statecore-mcp is the most expensive memory in the table and answers none of the thirty questions.**
5,710 bytes per question - 98 times the size of the answer it did not find - against a median of 663
for the best retriever. It also loses 3 of 20 acknowledged writes across two processes and cannot find
a record by the name it was given. Cheap is not the same as efficient, and expensive is not the same
as thorough; this is a subject that is neither.

## Four bugs the breadth found in the binder

Each one turned a working server into "this package does not work", which is the failure mode the
binder exists to avoid. All four are fixed in `autodetect.py`.

1. **It started the CLI instead of the server.** `@hasna/mementos` publishes `mementos` and
   `mementos-mcp`; taking the first entry point ran a command-line tool that does not speak MCP, and
   the result read as "initialize did not answer".
2. **"learn" was not a write verb.** `crbro-memory` calls its write `crbro_learn`, so the package
   looked like a memory server with no way to store anything.
3. **A constrained field got an invented value.** `rag-memory-epf-mcp` declares `status` as an enum
   of `["active", "provisional"]`; the binder sent `"probe"` and the write was rejected. It now reads
   the enum and sends a value the schema accepts.
4. **An optional field was never filled, even when it was the only place the handle could go.**
   `crbro_learn` will not store anything without a `topic` and does not list one as required, so the
   binder never sent it. Optional name-shaped fields are now consulted, but only when no required
   field could carry the name, so an existing binding cannot be disturbed.

That is eleven self-bugs across this project. The pattern has not changed: every one of them was the
harness assuming something about the subject instead of reading what the subject said.

## What breadth actually taught

Adding subjects is not a way to accumulate green rows. Six of seven new packages could not be
measured, three of them for reasons that are themselves defects - a global store, an exclusive file
lock, a server that will not start - and the two that could be measured both failed something. The
matrix got more useful and less flattering at the same time.

---

# Addendum 12: doubling the corpus, and what it did not buy

The retrieval corpus is now 72 records in fourteen clusters and 60 questions in the same four bands.
Every retrieval number in this document is superseded, and all eleven subjects were re-measured
against it with three repetitions each.

## What changed

```
                       30 questions                60 questions
memory-mcp-1file       22/30                      43/60
zenbrain               23/30                      37/60
control                13/30                      25/60
memory-lean             6/30                      14/60
memento                 8/30                      11/60
memdb                   7/30                       6/60
mcp-duckdb              -                          10/60
server-memory 1.0/2.0   0/30                       0/60
mcp-knowledge-graph     0/30                       0/60
statecore               0/30                       0/60
```

The separations from the floor got much stronger, because there is twice as much evidence for them:

```
zenbrain     vs memdb   31-0 discordant,  p < 0.0001   separated
control      vs memdb   31-0 discordant,  p < 0.0001   separated
memory-lean  vs memdb   20-0 discordant,  p < 0.0001   separated
```

## What it did not buy

**The two best retrievers are still not separated.** That was the whole reason for doubling the
corpus:

```
memory-mcp-1file vs zenbrain   10-4 discordant,  p = 0.18   not separated
```

Sixty questions establishes that both are far better than memdb and does not establish which of them
is better than the other. Their independent intervals overlap too (36-49 against 29-44), so this is
not an artefact of the marginal test.

The reason is visible in the bands. Both answer every easy question and most adversarial ones; they
diverge on the twelve `hard` paraphrases and disagree on only ten questions overall. A corpus
separates two systems in proportion to how differently they fail, and these two fail alike.

## The lesson, stated plainly

A corpus written by one person separates **"answers at all" from "answers nothing"** very easily -
that gap is 43 against 0 and it will survive any amount of shuffling. It does not separate two
systems that both answer, because it takes a large number of questions that happen to sit on their
particular disagreements, and I cannot see where those are without already knowing the answer.

That is the argument for the questions being written by somebody else, and it is not a thing more
work by me can fix. The corpus is in `retrieval_corpus.json`; a second author's questions can be added
to it and re-measured with one command.

## Two numbers that were wrong in three places each

The corpus size was written out in prose in `matrix.py`, `check.py` and `README.md`. Doubling the
corpus falsified all three at once, and none of them was noticed until the tables were regenerated.
They now read the size from `retrieval_corpus.json`, because a number that describes the instrument
should come from the instrument.

`sync_readme.py` is now a permanent tool rather than something rewritten each time: it puts the live
output of `matrix.py --report-only` into the README's table block. That block had already drifted a
subject behind when this was written, and hand-syncing documentation is a thing that fails silently
and then reports itself as true.

---

## Addendum 13: a second corpus, written blind, and what it took away

Every retrieval number in this document rests on a question set that I wrote, about a world I invented,
while looking at the results I was producing. That is a defect in the instrument and it was the largest
one left: nothing in the pipeline could have caught a corpus that quietly suited the answer the table
already gave, because the corpus and the table came from the same place. This addendum is the attempt to
attack that, and it cost more claims than it confirmed.

### The second corpus was written by someone who could not see the first

A separate author - a fresh instance of the same model, given nothing but a specification - wrote
`retrieval_corpus_b.json`: 72 records, 60 questions, 16 easy, 16 hard, 16 adversarial, 12 absent,
72 records in 14 clusters. It was told the domain (a fictional regional railway operator, deliberately
not the ops estate of corpus A), the shape of the record and the meaning of the four bands, and it was
told explicitly not to read corpus A, the matrix, the findings or any result. It reported authoring
without reading them.

THAT IS INDEPENDENCE OF INFORMATION, NOT INDEPENDENCE OF MIND, and the difference matters. A different
author with no knowledge of the answers is the thing that removes the specific bias being attacked - the
temptation to write questions that suit a hypothesis already held. A different model would remove more.
It was not available here and this is the honest description of what was tested.

### The corpus is now checked instead of asserted

`validate_corpus.py` reads a corpus and checks the assumptions its own bands rest on, as facts
rather than as intentions: ids unique, every expected answer an actual record, no record answering two
questions, no absent question covered by a record, every adversarial question with a record that
competes, every easy question sharing its answer's wording. It runs against BOTH corpora, including the
one every published number was computed from.

It found four defects in corpus A on the first run:

- six records each answered two questions, so those facts carried double weight and 48 questions measured
  42 facts;
- three questions labelled adversarial competed with nothing at all - "how far ahead are certificates
  renewed" shares no word with any record except its own answer - so the band that is supposed to ask
  "does it pick the right near duplicate" was partly asking nothing of the kind.

Both are pinned in `corpus-known.json`, which is the same idiom as `--expect` on the
probes: a known defect is written down, a new one fails the build, and a pinned one that stops
reproducing is reported as drift, because that means the corpus changed. Corpus B passes both checks
with no defects and none pinned.

WHAT THE FOUR DEFECTS COST, computed from the rows already on disk rather than from opinion:

| subject | published hit@3 | one credit per fact | adversarial, as labelled | adversarial, relabelled |
|---|---|---|---|---|
| memory-mcp-1file 0.9.2 | 43 | 37 | 14/16 | 11/16 |
| zenbrain 0.3.0 | 37 | 35 | 14/16 | 11/16 |
| control 1.0.0 | 25 | 24 | 9/16 | 6/16 |
| memory-lean 1.5.0 | 14 | 14 | 0/16 | 0/16 |
| memento 0.7.0 | 11 | 10 | 5/16 | 5/16 |
| mcp-duckdb-memory-server 1.1.10 | 10 | 10 | 2/16 | 2/16 |
| memdb 1.4.0 | 6 | 6 | 0/16 | 0/16 |
| statecore-mcp 1.0.0, server-memory 1.0.0, 2.0.0, mcp-knowledge-graph 1.3.2 | 0 | 0 | 0/16 | 0/16 |

The defects flattered the leader most: the 43 that made 1file look six questions clear of zenbrain is 37
against 35 once each fact counts once, and the adversarial band that looked like 14/16 for the two top
subjects is 11/16. No conclusion in the matrix changes - the top two were already unseparated, and the
only rank movement is a swap of two subjects tied at 10/60 - but the published magnitudes were too kind
to whoever came first, which is the direction such defects always lean.

### The replication

`REPLICATION.md` is generated by `replicate.py`. Eleven subjects, both corpora, same
harness, three passes per question as always. The totals are NOT comparable between corpora - they count
answers to different questions - so the comparison is of order and of separation.

| subject | corpus A hit@3 | corpus B hit@3 |
|---|---|---|
| memory-mcp-1file 0.9.2 | 43 | **44** |
| zenbrain 0.3.0 | 37 | **33** |
| control 1.0.0 | 25 | **32** |
| memento 0.7.0 | 11 | **19** |
| memory-lean 1.5.0 | 14 | **0** |
| mcp-duckdb-memory-server 1.1.10 | 10 | **13** |
| memdb 1.4.0 | 6 | **1** |
| server-memory 1.0.0, 2.0.0, mcp-knowledge-graph 1.3.2, statecore-mcp 1.0.0 | 0 | **0** |

Rank correlation between the two orderings: rho = 0.86 over eleven subjects. The top two are the same
two in the same order, the control is third on both, and the four subjects that cannot find anything
cannot find anything on either corpus. That much is not an artefact of the questions.

The claims are not the ranks, though. They are the adjacent pairs, because a table asserts "A is above
B" at every neighbouring position, and each of those is either a separation or a statement that the two
cannot be told apart. Tested one at a time on both corpora:

| pair | corpus A | corpus B | same conclusion |
|---|---|---|---|
| 1file / zenbrain | 0.180 (10-4) not separated | 0.003 (12-1) separated | **no** |
| zenbrain / control | 1.000 (13-13) not separated | 0.007 (2-13) separated | **no** |
| control / memory-lean | 0.001 (11-0) separated | 0.000 (32-0) separated | yes |
| memory-lean / memento | 0.011 (23-8) separated | 0.281 (12-19) not separated | **no** |
| memento / duckdb | 0.071 (10-21) not separated | 0.362 (12-18) not separated | yes |
| duckdb / memdb | 0.000 (18-2) separated | 0.000 (24-1) separated | yes |
| memdb / server-memory 1.0.0 | 0.238 (6-12) not separated | 0.006 (1-11) separated | **no** |
| server-memory 1.0.0 / 2.0.0, and 2.0.0 / knowledge-graph | all tied | all tied | yes |
| knowledge-graph / statecore | 0.000 (12-0) separated | 1.000 (0-0) not separated | **no** |

Five of ten neighbouring pairs reach the same conclusion. That is the finding, and it is not a
compliment to the instrument: half of what this document says about which subject beats which does not
survive a second question set.

### Two specific reversals worth naming

THE TOP TWO ARE SEPARATED ON ONE CORPUS AND NOT ON THE OTHER. Corpus A said 1file and zenbrain could not
be told apart (10-4, p = 0.18). Corpus B separates them (12-1, p = 0.003). Both statements are true of
their corpora. What is portable between them is the direction and the band: 1file finds 13 of 16 hard
paraphrases on BOTH corpora, while zenbrain finds 7 on A and 2 on B. A recall advantage concentrated in
one band, stable across two question sets, is a claim worth making; "43 beats 37" is not.

THE SECOND PLACE WAS NEVER AHEAD OF THE POSITIVE CONTROL, AND ON THE SECOND CORPUS IT IS BEHIND IT.
Corpus A: zenbrain 37/60 against the control's 25/60, and **thirteen questions to thirteen** - p = 1.0.
The twelve questions with no answer cancel the twelve-question recall gap exactly, because zenbrain
answers all twelve of them and the control declines all twelve. The marginal counts made that look like
a twelve-question win; the paired test says the two are interchangeable, and it said so before corpus B
existed. Corpus B agrees and goes further: the control is better, thirteen to two, p = 0.007.

The control is a server written to pass the eight probes with a plain keyword search bolted on. It is
not trying to be good at retrieval. A subject that cannot beat it has not demonstrated retrieval beyond
keyword matching on either corpus, and the corpus A table hid that behind a recall number.

### The shape of the question decided part of the score

memory-lean scored 14/60 on corpus A and 0/60 on corpus B, twelve of those fourteen in the easy band, and
returned an empty result for all sixteen corpus-B easy questions. That looked like a regression and it is
not one. A controlled test - one store, two records, the same fact asked six ways - shows what it
actually does:

| query | returned |
|---|---|
| maximum permitted speed Estuary Line | the right record |
| What is the maximum permitted speed on the Estuary Line? | nothing |
| access token fifteen minutes | the right record |
| How long does an access token last? | nothing |
| the record's own text, verbatim | the right record |
| the record's id | the right record |

Four hits, two misses. Its matching is word-based and the question-shaped queries carry function words
its index does not hold. Corpus A's easy band was written as keyword strings ("access token fifteen
minutes"); corpus B's was written as questions ("How long does an access token last?"). So the 14 and the
0 measure the corpus's phrasing, not the subject's retrieval. That is a bias I introduced into corpus A
without noticing, and a second author found it by writing questions the way a person speaks.

Every band is now asked in one shape only. A corpus that asked each fact both ways would separate
matching from ranking; this one does not, and until it does, a subject whose search is word-based will
score differently depending on who wrote the questions.

### The absent band is doing more work than it was credited with

On corpus B every subject that scores above zero also answers at least eleven of the twelve questions
that have no answer in the store: 1file 12/12, zenbrain 12/12, memento 12/12, memdb 11/12. The 44/60 and
33/60 come from systems that never say "nothing found", so the score column is a ranking of recall by
systems that have not learned to be wrong out loud.

THE SCORE COLUMN IS NOT WHERE THAT SHOWS UP. hit@3 rewards speaking - it is never true on a question
with no answer, so declining earns nothing and returning junk costs nothing - but the paired test counts
silence as correct, and there the same behaviour is worth a whole rank. duckdb against memdb separates
on both corpora, eighteen-two and twenty-four-one, and the larger split on corpus B is almost entirely
memdb answering eleven of twelve unanswerable questions while duckdb answers none. Read against the
score column alone, 10/60 and 6/60 look like two subjects that cannot find much. They are not the same
kind of failure.

### What this phase cost in my own mistakes

Five, in the same shape as the others: assumptions about the instrument.

1. The first absent-band check demanded that no word of an absent question appear in any record, and
   charged four honest questions - "what is the office wifi password" against a record about password
   policy - as answerable. A shared word is not a shared answer. The check now measures whether one
   record covers most of the question.
2. The first adversarial check demanded a competing record sharing two words with the QUESTION, and
   failed eleven of sixteen honest items. The trap is between two records: a question about refresh
   token lifetimes competes with a record about access token lifetimes through the single word
   "token", and that one word is the whole mechanism.
3. The brief given to the second author said 52 questions have an answer, which is wrong: 16+16+16+12
   is 60, so 48 do. The corrected arithmetic was sent before the corpus was finished and the author had
   already reconciled it.
4. `npm install` could not install one subject (`@zensation/mcp`) inside a OneDrive
   folder: npm's cleanup step hit EPERM removing a nested native build, rolled back the whole scope, and
   then reported the tree complete on the next run because a missing optional dependency is not an
   error. The subject was installed outside OneDrive and linked in, and the matrix now says so when a
   binary it expects is absent.

5. `replicate.py` decided whether a subject had answered a question using hit@3, which is never true on
   a question with no answer - so the entire absent band scored as a tie, and a subject that answers
   every unanswerable question looked identical to one that declines. The first version of this very
   addendum therefore claimed zenbrain was separated from the positive control at p = 0.002, on the same
   corpus where `compare.py` says p = 1.0. Two definitions of "correct" in one repository is how a table
   ends up contradicting itself; there is now one, and it lives in `compare.correct`.

The last two are the same failure as every other in this document: the tool believed its own report
rather than checking the thing it claimed to have produced.

### What a third corpus should test

Not another rewrite of the same design. The two experiments that would move this from "one author
replicated by another" to a measured instrument:

- each fact asked in both shapes, keyword and question, so matching and ranking separate;
- a corpus written by a different model, and the disagreements between corpora published as the error
  bar rather than the corpus A result;
- the absent band as a score, not a column: "of the questions that have no answer, how many did it
  decline", with the same weight as hit@3, so that a system that answers everything cannot sit at the
  top of a recall table without paying for it.

---

## Addendum 14: the same question, asked two ways

Addendum 13 ended by saying the next corpus should ask each fact in both shapes. This is that, done
mechanically instead of by authoring a third question set - because a corpus always carries its author's
phrasing, and asking the same words twice does not.

### The mechanism

`words.py` now holds the only tokenizer this repository has, used by the corpus validator and by
the retrieval harness, because two tools disagreeing about which words carry meaning is how a repository
contradicts itself. `keyword_form()` takes a question and drops the words that cannot distinguish
one record from another: "What is the maximum permitted speed on the Estuary Line?" becomes "maximum
permitted speed estuary line".

With `--shapes` on - now the default for every retrieval run - each question is put twice inside the
SAME pass: same store, same restart, same tool binding, same three repetitions. Anything that differs
between the two answers is the phrasing, and nothing else.

### The result

Correct answers, the metric the paired test uses: the right record in the top three, or silence on a
question that has no answer. That is not MATRIX.md's hit@3 column, which counts hits only, so a subject
that finds nothing but declines all twelve unanswerable questions is 12 here and 0 there.

| subject | A as written | A as keywords | B as written | B as keywords |
|---|---|---|---|---|
| memory-mcp-1file 0.9.2 | 43 | **43** | 45 | **37** |
| control 1.0.0 | 37 | **41** | 44 | **44** |
| zenbrain 0.3.0 | 37 | **32** | 33 | **34** |
| memory-lean 1.5.0 | 26 | **30** | 12 | **28** |
| mcp-duckdb-memory-server 1.1.10 | 22 | **22** | 25 | **29** |
| memento 0.7.0 | 11 | **10** | 19 | **17** |
| server-memory 1.0.0, 2.0.0, mcp-knowledge-graph 1.3.2 | 12 | **14** | 12 | **14** |
| memdb 1.4.0 | 6 | **29** | 2 | **16** |
| statecore-mcp 1.0.0 | 0 | **0** | 12 | **12** |

Eight of eleven subjects score differently on corpus A and nine of eleven on corpus B. Fifty-nine and
sixty-one question outcomes respectively change with nothing changing but the words used to ask. The
rank correlation between the two phrasings is 0.86 and 0.81.

### Two of these are lookup tables wearing a search interface

memdb goes from 6 to 29 on corpus A and 2 to 16 on corpus B when the questions are put as words.
memory-lean goes from 12 to 28 on corpus B - the same subject whose 14/60 against 0/60 across the two
corpora looked like a bug in Addendum 13. Neither is inconsistent; both need the user to type the words
rather than ask the question.

That is a product property and not a defect, and one hit@3 number cannot say it. "memdb finds 6 of 60"
and "memdb finds 29 of 60" are the same system measured twice, and the difference is who is typing.

### The one that goes the other way

memory-mcp-1file is unchanged on corpus A (43 to 43) and loses eight on corpus B (45 to 37) when the
words are stripped, seven of them in the hard band: 13 of 16 paraphrases as questions, 6 as keywords.
So its advantage over zenbrain is real, is concentrated in the band where a paraphrase has to be
understood rather than matched, AND NEEDS TO BE ASKED AS A QUESTION TO APPEAR. Put the same corpus B
questions as keywords and the gap goes with it: 5-2, p = 0.45.

Which decides the top-two claim in both directions, and the direction never reverses while the verdict
does:

| | as written | as keywords |
|---|---|---|
| corpus A | 10-4, p = 0.18, not separated | 13-2, p = 0.0074, separated |
| corpus B | 12-0, p = 0.0005, separated | 5-2, p = 0.45, not separated |

### One comparison that is meaningless without a phrasing

memdb against memento, the same two subjects, the same two corpora:

| | as written | as keywords |
|---|---|---|
| corpus A | 6-11, not separated | 25-6, separated for memdb |
| corpus B | 2-19, separated for memento | 13-14, tied |

Every possible answer appears. Nothing about either subject changed; the phrasing moved 50 questions.
A table of one phrasing cannot express this, and every earlier table in this project was read as though
it could.

### It reproduced, with one exception that is itself a finding

Every result was re-measured from scratch after the change, and MATRIX.md regenerated from the new
results is byte-identical to the committed one: 72 probe verdicts, nine subjects, three passes each, and
every retrieval score, all reproduced on a later day with a harness that asks twice as many questions.

The exception is memory-mcp-1file's corpus-B total, which came back 44 on one invocation and 45 on two
later ones. That is the discovery-bound binding already recorded in Addendum 11: inside one invocation
the three passes agree exactly, and between invocations AutoAdapter may bind a different one of the
subject's several search tools. A number that depends on which tool discovery happened to pick is quoted
with that in mind.

### Three more of my own mistakes

6. The stopword list never contained **and**, **or**, **but**, **if**, **because** or **while**. A
   conjunction was being counted as a word that distinguishes one record from another, which is enough
   for two unrelated records to look like they compete for the same words - the exact test the
   adversarial band rests on - and it put "and" into every derived keyword string. The list is fixed and
   is now the only copy in the repository.
7. **The hard band was never checked.** Every other band had a mechanical check; this one had a sentence,
   "a paraphrase that shares almost nothing with the wording of the answer". Counting it found two corpus
   A questions that share two words with their own answer - "where is customer data physically held"
   against a record that says "customer data" - which are keyword questions wearing a paraphrase's
   label. Both flattered the leader: memory-mcp-1file is 13/16 on the labelled band and 11/14 with them
   set aside. The threshold (at most one shared word) is written into the check, and it was chosen after
   measuring both corpora, which is worth knowing when reading it.
8. **A killed job kept running.** I stopped the first measurement, but the python process it started did
   not stop with it, and the next run's log redirect failed on the file the orphan still held. The job
   status said "completed"; the process table said otherwise, and the orphan was still overwriting
   results with keyword strings built from the pre-fix stopword list. The same lesson this document keeps
   recording, now about my own tooling: a report of completion is not evidence of it.

### What the table means now

A retrieval score is now a pair, and the pair is the measurement. "memdb 6/60" is not a fact about memdb;
"6/60 asked as written, 29/60 asked as keywords" is. The next thing to fix is not the corpus and not the
phrasing: it is that the two numbers travel together into every table and every claim, and that neither
of them is ever the silently chosen one.

---

## Addendum 15: the pair travels, and five numbers it caught on the way

Addendum 14 ended with a promise: stop letting one phrasing be the number. A number that lives only in
`SHAPE.md` is a number nobody reads - the places a number is actually read are the table, the
paired comparison and the one command a server author runs. So the pair now travels into all three.

- `retrieval.py` carries the keyword totals in the same summary it prints the written ones in, on
  the line below them.
- `matrix.py` gained two columns, `kw h3` and `change`, in both the console table and
  `MATRIX.md`, so the published table cannot show a retrieval score alone.
- `compare.py` reports both verdicts by default and says **THE PHRASING DECIDES THIS ONE** when they
  disagree. That sentence is the product: the same pair is "not separated" as written and "separated"
  as keywords, and the tool now refuses to print one of those without the other.
- `check.py`, the command someone runs on their own package, prints both - including whether the
  subject speaks on unanswerable questions under each phrasing, which is not the same number either.
- CI asserts all of it: a grep for the two columns in the matrix output and for the verdict sentence in
  `compare.py` output. A table that goes back to one phrasing now fails the build.

### What the pair caught, in this repository's own README

Five claims. Every one of them was true in the phrasing it was measured in, and every one misleads
without it:

1. **"answers none of the 60 questions"** about `@modelcontextprotocol/server-memory` - 0 as
   written, 2 as keywords. "None" was the wrong word for a subject that can be made to answer two.
2. **"the highest raw retrieval count, 43 of 60 against zenbrain's 37 ... not separated (p = 0.18)"** -
   the count is right and the verdict is phrasing-dependent: 13-2 and p = 0.0074 as keywords.
3. **"the highest raw retriever (memory-mcp-1file, 43/60) is also among the most expensive"** in the
   cost section - right, and now printed as 43 and 43 rather than 43 alone.
4. **memory-lean's "0/60 on corpus B"** - 0 as written and 28 on the same questions as keywords. "It
   cannot find anything" was wrong; "it cannot answer a question" is right, and the two sentences are
   about different systems from the same corpus.
5. **The `check.py` example output** quoted eight questions per band, from the thirty-question
   corpus, four phases after the corpus became sixty. It is regenerated now, from a real run rather
   than typed out - the first time that block has been produced by the tool it claims to be a
   transcript of.

None of the five was a lie when it was written. All five are the same defect this suite exists to catch
- a number separated from the condition it was measured under - found in the suite's own README, which
is the place it is easiest to miss because the author reads their own prose as intent rather than as
data.

### And the number I made up

I edited the README example block to read "easy 11/16 ... all 11/60 ... all 29/60 (+18)" before I ran it.
Those numbers were invented to fit the shape of the output, and I caught it two edits later, ran the
subject for real, and replaced the block with what actually came back - 0/60 and 2/60.

The invented numbers were plausible, and that is exactly the problem. A fabricated example does not
fail; it sits there reading like data, in the section of the README whose purpose is to show what real
data looks like. **Self-bug 9**, and the first one in this series that nobody else could have caught,
because the subject it describes was never run.

### The table as it now stands

hit@3, as published. The keyword column is the same sixty questions with the words that carry no
meaning removed.

| subject | hit@3 as written | hit@3 as keywords | change |
|---|---|---|---|
| memory-mcp-1file 0.9.2 | 43/60 | **43/60** | +0 |
| zenbrain 0.3.0 | 37/60 | **32/60** | -5 |
| control 1.0.0 | 25/60 | **29/60** | +4 |
| memory-lean 1.5.0 | 14/60 | **18/60** | +4 |
| memento 0.7.0 | 11/60 | **10/60** | -1 |
| mcp-duckdb-memory-server 1.1.10 | 10/60 | **10/60** | +0 |
| memdb 1.4.0 | 6/60 | **21/60** | +15 |
| server-memory 1.0.0, 2.0.0, mcp-knowledge-graph 1.3.2 | 0/60 | **2/60** | +2 |
| statecore-mcp 1.0.0 | 0/60 | **0/60** | +0 |

The two columns agree for four subjects and disagree for seven.

### What is still open

- **Corpus A's six defects are pinned, not fixed.** The two hard-band questions that share their
  answer's wording are still in the corpus, still labelled a paraphrase, and still flattering whoever
  finds them. Pinning records a defect; it does not remove it.
- **One author, one model.** Independence of information was tested. Independence of mind was not, and
  the two corpora were written by the same model family.
- **One subject's number moves between invocations.** memory-mcp-1file's corpus-B total is 44 or 45
  depending on which search tool discovery binds, and the report carries that as a range rather than a
  value.

---

## Addendum 16: paying the pinned debt, and what it did to the ranking

Addendum 15 ended with the thing still open: corpus A's six defects were pinned, not fixed. A pin says
"this is wrong and I know it is wrong"; it does not make it right, and every number computed from the
corpus was still computed from it.

### The repair

Ten questions rewritten, no record touched. Ten, against a count of eleven defects, because two of them
were the same question - the hard question on `key-signing` was both a duplicated answer and a
keyword match, and retargeting it fixed both.

The rules the repair was held to:

- **one fact, one question.** Every record that answers something now answers exactly one question, so
  no fact carries double weight.
- **a band's label must be true.** An "adversarial" question needs a near duplicate to compete with; a
  "hard" question must share at most one word with its answer.
- **no record may be edited.** Records are the store every subject is measured against; changing them
  changes the experiment for all 45 questions that still work, and that is a different repair.

| what was wrong | repaired to | band | new answer |
|---|---|---|---|
| `where is customer data physically held` - shared 2 words with its answer | In which city is the personal information of users kept? | hard | region |
| `which key is kept inside specialised hardware` - shared 2 words, and key-signing answered twice | How long must a passphrase be, and how is it stored? | hard | auth-password |
| auth-token-ttl answered twice | Does shutting the window log me out? | hard | auth-session |
| net-dns-ttl answered twice | How long is a machine left to settle before it stops taking work? | hard | maint-drain |
| backup-retention answered twice | Where is the key that protects the backups kept? | adversarial | data-backup-key |
| bill-terms answered twice | Is every read of personal information recorded? | adversarial | data-audit |
| auth-lockout answered twice | How soon does someone hear about a failed replication? | adversarial | alert-replication |
| `which host is used only for the always on collector` - competed with nothing | In which currency are invoices issued to a customer in another country? | adversarial | bill-currency |
| `can two stores see each other's records` - competed with nothing | How often is a release cut? | adversarial | rel-cadence |
| `how far ahead are certificates renewed` - competed with nothing | How fast must ninety five percent of requests be answered? | adversarial | latency-slo |

The three questions that competed with nothing could not be repaired by rewording: competition is a
property of the STORE, and those three records carry words no other record carries. Rather than add
near-duplicate records - which would have changed the store every subject is measured against - those
three questions were re-aimed at records that already had a competitor sitting beside them and no
question of their own.

### The validator after the repair

retrieval_corpus.json: 72 records, 60 questions (easy 16, hard 16, adversarial 16, absent 12), 48
distinct answers, 24 distractors, adversarial rival shares 1 and 2 words (no zeros, where before there
were three), and no hard question sharing more than one word with its answer.

`corpus-known.json` is now empty. The mechanism stays, with nothing pinned in it, so the next
defect that appears is a build failure rather than a line in a table. Three records lost their questions
(hosts-pi, mem-store-path, maint-cert) and became distractors; nine previously unused records gained one.

### The cost, and the guard that made it visible

Changing the instrument invalidates every number measured with it. That is exactly the failure this
project keeps recording, so the guard written for it fired first: `matrix.load_rows` compares a
saved report's questions against the corpus it claims to be about, and it refused all eleven corpus-A
result files on the first read. Nothing was reported from a corpus that no longer exists.

### What the change did to the numbers

Corpus A, hit@3, before and after the repair. Corpus B is untouched and its column is there to show what
a corpus that was never defective looks like.

| subject | A before | A after | B |
|---|---|---|---|
| zenbrain 0.3.0 | 37/60 | **40/60** | 33/60 |
| memory-mcp-1file 0.9.2 | 43/60 | **42/60** | 45/60 |
| control 1.0.0 | 25/60 | **25/60** | 44/60 |
| memento 0.7.0 | 11/60 | **14/60** | 19/60 |
| mcp-duckdb-memory-server 1.1.10 | 10/60 | **12/60** | 13/60 |
| memory-lean 1.5.0 | 14/60 | **14/60** | 0/60 |
| memdb 1.4.0 | 6/60 | **6/60** | 1/60 |

THE DEFECTS WERE DOING REAL WORK IN THE RANKING, and in the direction these things always do - for
whoever was leading. The runner-up gained three questions, the leader lost one, and the adversarial band
changed hands: zenbrain is now 16 of 16 on corpus A's adversarial questions where it was 14, while
memory-mcp-1file is 14 where it was 14. The paired comparison between them, 10-4 (p = 0.18) as written
before the repair, is 8-5 (p = 0.58) after it. The lead that the defects were propping up was two
questions of real difference and four questions of a corpus that was wrong in the leader's favour.

Two other subjects moved in the opposite direction from last phase's conclusion, and it is worth saying
so plainly: memento went from 11 to 14, because several of its misses were on questions that were
duplicated or unanswerable-by-design, and duckdb went from 10 to 12. Neither becomes a different
product; both were being measured by a defective instrument.

rho between the two corpora moved from 0.86 to 0.89, and the neighbouring pairs still disagree five
times out of ten. Fixing corpus A made the two corpora agree slightly better. It did not make them
agree.

### What is still open

- **Corpus B still carries four warnings**: an absent question sharing one word with a record, one
  near-paraphrase pair, and three adversarial questions with a one-word trap. Warnings, not defects, and
  printed on every run rather than suppressed.
- **One author, one model.** Unchanged.
- **The adversarial band now has no winner that survives both corpora.** zenbrain leads it 16-14 on
  corpus A and trails 15-16 on corpus B. That is two question sets disagreeing, with no defects on
  either side to blame it on.

---

## Addendum 17: the ledger, and five of eleven

Seventeen addenda is not a document, it is a diff. A reader arriving at this repository now has to
reconstruct what is true from a chain of corrections, and the corrections are the interesting part only
if you already know where they landed. So the claims are evaluated instead of remembered.

`claims.py` takes every sentence this repository has published about its subjects - eleven of them -
and checks each one against the committed results on both corpora and in both phrasings. It writes
`CLAIMS.md` and prints one line: **five of the eleven hold in every setting measured.**

| claim | verdict |
|---|---|
| memory-mcp-1file answers more answerable questions than any other subject | **HOLDS** - alone at the top on both corpora, in both phrasings |
| memory-mcp-1file leads the hard band | **HOLDS** |
| memento answers every unanswerable question | **HOLDS** - 12 of 12, four settings |
| memory-mcp-1file leaks state between stores | **HOLDS** - isolation FAIL |
| one subject's answer count moves by ten or more on phrasing alone | **HOLDS** |
| memory-mcp-1file is better than zenbrain by the paired test | MIXED - 8-5 (p = 0.58) on A as written, 11-2 (p = 0.02) as keywords, 12-0 on B as written, 5-2 (p = 0.45) on B as keywords |
| zenbrain leads the adversarial band | MIXED - 16/16 on A as written, tied at 13 as keywords, and behind on both of B's |
| memory-lean returns fewer bytes than any subject that answers anything | MIXED - 164 bytes and the cheapest on A; void on B, where it answers nothing and does not qualify |
| server-memory answers no answerable question | ONE PHRASING - 0 of 48 as written, 2 of 48 as keywords |
| the smallest servers here find nothing | ONE PHRASING - the same two questions, the same way |
| zenbrain is better than the positive control | **FAILS** - in all four readings, and the control is ahead in three of them |

### The sharpest line in it

**ZENBRAIN IS NOT BETTER THAN THE POSITIVE CONTROL, AND THE CONTROL IS AHEAD ON THREE OF FOUR READINGS.**
The control is a server written to pass the eight probes with a plain keyword search bolted on; it is not
trying to be good at retrieval. A subject that cannot beat it has not demonstrated retrieval beyond
keyword matching, and the marginal counts that made it look like a twelve-question win - 40/60 against
25/60 on corpus A - are cancelled by the twelve questions it answers that have no answer.

This is the result the suite was built to produce and could not produce for sixteen addenda, because
nobody had put the claims in one place where a single mechanical check could contradict them.

### Two measurements, kept apart

The first draft of this ledger asked whether "server-memory answers no question at all" and got back
**12 of 60 answered**. That is not a bug in the result, it is a bug in the question: the metric the paired
test uses counts *declining an unanswerable question* as correct, so a subject that finds nothing at all
scores 12 for being silent twelve times. Silence is part of being better than another server - it is not
"answering". The ledger now carries both: a score for the pairwise claims and a hit count for the ones
that are about finding things. **Self-bug 10.**

And a smaller one in the same file: the first draft reported a subject as "alone at the top" whenever it
came first in a sorted list, which is what happens to the alphabetically earlier of two tied subjects.
memory-mcp-1file ties the positive control at 42 hits on corpus A as keywords, and the ledger called that
a lead. A tie is not a lead; the detail line now says "tied with" and the claim fails. **Self-bug 11.**

### What this changes

The README now opens with the ledger rather than with a table, and every number in it can be traced to a
claim with a verdict and a setting. A new claim belongs in `CLAIMS.md`, not in prose: if it cannot be
evaluated against these results then it is not yet a finding, and if it can be, the tool will say which
corpora and which phrasings it survives.

### What is still open

- **One author, one model.** Both corpora were written by the same model family, one of them blind to
  the results. Independence of information was tested; independence of mind was not.
- **Corpus B still carries three warnings** - adversarial questions whose near duplicate is only one
  shared word away. They are printed on every run and are not defects, which is exactly why they will
  keep sitting there.
- **The adversarial band has no winner that survives both corpora**, and the ledger now records that as
  a MIXED claim rather than a sentence in prose. Resolving it needs a third corpus from a genuinely
  different author, and this harness can only offer another instance of the same one.

---

## Addendum 18: the ninth probe, and the promise nobody tests

Every probe so far asked what the subject KEPT. None asked whether it can be made to STOP keeping
something - deletion, the operation anyone with a wrong fact, a private record or a mistake in their
memory actually needs, and the one that fails in the same direction as the write: the caller is told "ok"
either way.

### The probe

Three records with no word in common are written, the middle one is forgotten, the server is restarted,
and the store is read on a process that saw neither the write nor the deletion. PASS requires **both**
halves: the forgotten record gone, and the two others still there. The second half is what makes the first
meaningful - a store that drops everything is indistinguishable from one that forgot exactly what it was
told to.

UNKNOWN is the verdict when the subject publishes no way to be asked, and it is now UNKNOWN rather than
FAIL. The distinction is the whole point: a subject that cannot be asked is not a subject that lied. The
promise is broken when the caller is told the record is gone and it is not.

The nine probes, measured on eleven subjects, three attempts each:

| | forget |
|---|---|
| control, server-memory 1.0.0 and 2.0.0, memento, memory-lean, mcp-knowledge-graph | **PASS** |
| memdb, zenbrain, memory-mcp-1file, statecore-mcp, mcp-duckdb-memory-server | **UNKNOWN** - no tool that can be shown to delete one record |

**Nobody was asked to forget and kept the record.** Five of eleven cannot be asked at all, and they
include the two subjects at the top of the retrieval table: memory-mcp-1file and zenbrain. The best
retrievers in this suite publish no documented way to remove anything, which is a fact worth having
before someone stores something they may need to take back.

That is the ledger's twelfth claim and it fails: `can-forget` - "every subject can be asked to forget a
record, and forgets it" - is false on both corpora, five subjects named.

### Two more of my own mistakes, both caught by the new probe printing the answer

**12. The sentinel went in the wrong function.** `_deleter` was set in `reset()` instead of
`__init__()`" and every discovery-bound subject - seven of eleven - reported a harness error on the first
run of the new probe while the hand-written adapters answered it. The log said
`'ManifestAdapter' object has no attribute '_deleter'`, which is at least an honest failure
message; the danger was the other direction, where a probe that cannot run reports UNKNOWN and looks like
a subject that cannot answer.

**13. The control's own verification had been lying since it was written.** `control/memory_server.py`
appends bytes and then reads the file back to confirm they landed; it has answered
`{"ok": false, ..., "readback_verified": false}` on EVERY write it has ever made. The cause is
Windows: `os.open()` there translates `\n` into `\r\n` unless `O_BINARY` is passed, so
the bytes on disk never equalled the bytes it wrote and its own check said so. Eighteen phases of the
suite passed over it, because the suite checks the read-back itself and never asked the control whether
its verification had succeeded.

The probe that found it is the one that prints the subject's own answer in its evidence. Nothing else in
this repository reads what the subject said it did.

### What this costs

The probe axis is re-measured for every subject, and nothing else: retrieval and cost do not depend on a
new probe, and re-rolling them would move numbers that did not change. MATRIX.md's verdict table gained a
column; the control, the reference server and the pinned expectations were updated to include it; and
every previous addendum's "eight probes" is now history rather than description.
---

## Addendum 19: does the suite have teeth

Addendum 18 ended with the forget probe published as **six PASSes, five "this subject cannot be
asked", and no FAIL at all.** Nothing in that table distinguished "no subject broke this promise"
from "this probe would not have noticed if one had". The same is true of every probe here: each one
has been *run*, and none had been *tested*. `restart` has never returned FAIL on any subject, and
`ack_readback` has never returned anything but PASS.

A verifier is only worth what its demonstrated failures are worth. So the next phase does not add a
tenth probe; it takes the positive control and breaks one promise in it at a time.

### The prediction is the test

`mutants.py` holds eleven mutants. Each is the control with one lever thrown, and each carries the
verdict all nine probes **must** return - written into the registry before anything ran. That
ordering is the whole design. Taking the expected vector from what the run happened to print would
have made the table a description of the code instead of a check on it, and it would have passed
just as green.

```
mutant               aimed at        iso  ack  rst  fgt  fnd  ffd  frc  cnc  lrg
------------------------------------------------------------------------------
leak-everywhere      isolation       FAIL .    .    .    .    .    .    .    .
no-persist           ack_readback    .    FAIL FAIL unk  FAIL unk  .    FAIL FAIL
keep-last            restart         .    .    FAIL unk  FAIL FAIL FAIL FAIL .
no-forget            forget          .    .    .    FAIL .    .    .    .    .
forget-all           forget          .    .    .    unk  .    .    .    .    .
reshape-modelled     foreign_field   .    .    .    .    .    FAIL .    .    .
drop-unnamed         foreign_record  .    .    .    .    .    .    FAIL .    .
stale-cache          concurrent      .    .    .    .    .    .    .    FAIL .
truncate-large       large_record    .    .    .    .    .    .    .    .    FAIL
mute-search          findable        .    .    .    .    FAIL .    .    .    .
blind-search         findable        .    .    .    .    FAIL .    .    .    .
```

All 99 predicted verdicts matched on the first run. That is evidence only because the matrix is not
flat: eleven mutants produce five different patterns, and a harness that could not fail would have
printed eleven rows of PASS. It was also, in part, luck of the scheduler - see mistake 17.

### Seven probes fail alone, and two cannot

`isolation`, `forget`, `findable`, `foreign_field`, `foreign_record`, `concurrent` and
`large_record` each have a mutant that reaches them and nothing else. `ack_readback` and `restart`
do not, and the reason is structural rather than a weakness in the probes: every probe begins by
writing a record and reading it back, so a subject that loses writes at the root fails all nine.
A mutation cannot break the first without breaking the others, and the table says which cascade
rather than hiding it.

`keep-last` pulls the two apart anyway: each write replaces the store with itself, so one write
survives and three do not. `ack_readback` passes it and `restart` fails it, which is the difference
between the two probes stated in the only way that means anything - a subject that satisfies one and
not the other.

### The forget probe gets attacked from both sides

`no-forget` acknowledges the deletion and keeps the record. Plain FAIL, caught.

`forget-all` deletes **everything** instead, and the answer the caller gets back is byte-for-byte
the same. The probe returns no verdict - not PASS - because the two records nobody asked about are
gone too, and a store that lost everything cannot be told apart from a store that forgot exactly
what it was told to. Over-deleting and breaking are different defects, the probe cannot say which it
witnessed, so it says that.

That is why the probe writes three records sharing no word and insists the other two survive. When
it was written, the second half looked like a tidiness check. It is the half that catches the
interesting failure, and the mutation battery is the first thing that demonstrated it does.

### Four more of my own mistakes

**14. The README stated a claim count that was already wrong.** It said "5 of the 11 claims hold in
every setting measured" for a whole phase after a twelfth claim had been added, and the sentence
after it - "the other six are printed beside the setting that breaks them" - named a count as well,
now seven. Both were hand-maintained prose about a number that `claims.py` computes.

This is the same defect the repository exists to find, sitting in its own front page. The fix is not
the edited number: `claims.py` now rewrites that sentence from the ledger it just built, and the run
fails if the README no longer contains it. The second sentence no longer names a count at all.

**15. The battery summarised itself wrongly, in the direction that flattered it.** The first
generated `MUTANTS.md` reported "8 fail alone" and then listed seven probes with `findable` twice.
The predicate asked whether some *other probe* had any killer, which is false for every probe once
the cascades are counted, so the list came out empty and the fallback text claimed the opposite. A
correct predicate is one mutant that kills this probe and nothing else; it now yields seven, and the
duplicated name came from the same bug.

**16. The leak was not gated on its mutant.** `MEMORY_LEAK_PATH` was read whenever it was set, so
every mutant would have leaked state between stores and produced verdict vectors nobody had
predicted - eleven surprising matrices instead of eleven predictions. Caught by re-reading the code
before the first run rather than by a run, which is the cheaper way to find it, and it is only
recorded because the tempting reading of "all 99 matched first time" is that the mutants are too
gentle. They are not; this one was simply not live yet.

**17. The battery was platform-dependent, and the first run could not tell.** `reshape-modelled` and
`drop-unnamed` rewrite the whole store, and the first version read the store *outside* the lock and
wrote it back *inside*. Two concurrent writers could therefore each overwrite the other's append with
what they had read a moment earlier - a concurrency defect bolted onto mutations that were supposed to
be about what the server keeps.

On Windows the race never bit and both mutants passed `concurrent`, exactly as the registry predicted.
On Linux the store ended the run empty - "0 of 20 acknowledged writes survived" - and CI failed the
battery on its very first push. So the headline "99 of 99 matched first time" was partly an accident
of one operating system, and I had no way to know that from the run that produced it.

The read now happens inside the same lock as the write, both mutants break one promise again, and the
predictions survived unchanged. That is the better evidence: a prediction that has to be adjusted to
fit the code is not a prediction any more. It is the second thing here that only a second platform
found, after the CRLF bug in 13, and the lesson repeats - a result measured on the machine that
produced it has not been measured against the machine that will believe it.

### What this proves, and what it does not

It proves that each of the nine probes can return FAIL, that seven of them can do it without
collateral, and that the suite distinguishes eleven different defects from each other and from the
control. It does not prove the probes would catch every defect a real memory server can have - only
the ones somebody here thought to build. A failure mode nobody has imagined yet is still unproven,
and every mutant is the control with a lever in it, so they all inherit the control's shape.

The honest count is nine probes and eleven demonstrations of failure, not nine probes and
completeness. The battery runs in CI in about a minute, needs no npm and no network, and is the only
job that would notice a probe quietly losing the ability to fail.

### What this costs

One new file (`mutants.py`), one generated table (`MUTANTS.md`), about forty lines of levers in the
control server, and one CI job. No subject verdict, retrieval score or cost figure moves: nothing
here touches what was measured before, only whether the thing doing the measuring works.
---

## Addendum 20: the tenth probe, and the narrowest promise of all

Every probe before this one asked whether the record was THERE. None asked whether it was the SAME.
That is the whole promise of a memory in one line, and it is the last place in this suite where the
answer is a byte comparison rather than a judgement.

### The probe

Nine strings go into one record, each aimed at a different layer of the encoding stack: 2, 3 and
4-byte UTF-8; a combining pair beside its precomposed twin, so a normalising store is visible;
right-to-left text; a JSON escape; a zero-width space; and a newline embedded in the body of a
newline-delimited transport. The record’s name is non-ASCII too, because the handle can be lost while
the body survives. Everything is compared after a restart, on a process that never saw the write.

PASS needs all nine, byte for byte. Anything else names the string that broke and how far the nearest
things in the store agreed with it before they diverged.

### What it found

| | verbatim |
|---|---|
| control, server-memory 1.0.0 and 2.0.0, memento, memdb, memory-lean, mcp-knowledge-graph, zenbrain | **PASS** (8) |
| memory-mcp-1file, statecore-mcp, mcp-duckdb-memory-server | **UNKNOWN** - the body is not returned over the wire and no store is readable (3) |

**Nobody altered a single character.** That is the second probe in a row to come back with no FAIL at
all, which is exactly the situation that made the mutation battery necessary: eight PASSes and three
"could not be asked" is also what a probe that cannot fail would print. `lossy-locale` - text
round-tripped through cp1252, which has an e-acute and has never had an emoji - fails it, alone, and
that is the difference between a result and a rumour.

The three UNKNOWNs are the interesting half. Those subjects answer a read with the record’s name and
keep the body where only their own store can see it, and no manifest declares that store. This is the
same shape as `can-forget`: a capability the harness cannot reach is a fact about the harness, and it
is reported as one.

### memento returns the body sorted

memento came back with all nine strings intact and in alphabetical order. Every character survived
and the sequence did not. That is reported in the evidence and deliberately not scored: calling it a
verbatim failure would tell a reader the text was mangled, which is false, and passing in silence
would hide that a sequence stored as a sequence comes back sorted. The verdict is about the
characters - the one thing the probe does not have to interpret - and the evidence says which order
the subject chose.

### Four more of my own mistakes, and one that took three attempts

**18. The comparison judged order.** The first version required a field called `observations` holding
a list, and compared it element by element. memento failed on the very first subject that reached it,
with an evidence line that said "line 2: wrote the latin string, got the astral one" - a permutation
reported as a mangling. A diagnostic script confirmed nine strings, byte for byte, sorted.

**19. The first fix still measured four of eleven subjects.** Seven return the record’s name and no
body. Requiring the reference server’s record shape meant the probe was UNKNOWN for the majority of the
table. It now searches the returned record for the strings and falls back to the adapter’s declared
store - the same two-surface arrangement `large_record` already used. That needed a new store
primitive, because length is not content: a cp1252 round-trip replaces a character and changes no
column length at all, so `content_length` could not answer the question. Both backends gained
`content_text`.

**20. Without a canary, "I cannot see it" was being reported as "it is gone".** Once the store
fallback existed, duckdb - which returns no body and declares no store - reported nine of nine
strings altered, every one of them a defect the probe had never observed. A plain ASCII record now goes
through the same path first; if that does not come back either, the verdict is UNKNOWN with the reason.
Two different answers, and only one of them is a verdict.

**21. A mutation I had already predicted changed behaviour because the probe changed under it.**
`keep-last` replaces the store with each new record, so one record survives. The probe wrote one record
when the prediction of PASS was written and writes two now, and the canary is one of them. The battery
caught it: a row marked "prediction wrong". The prediction was stale, not the code, and it is recorded
in the registry rather than quietly corrected - a prediction that is edited until it matches is not a
prediction.

### One list instead of four

The probe set lived in four files - `harness.py`, `matrix.py`, `check.py` and `mutants.py` - and every
copy was a place to forget. `check.py` had been one short: it never learned about `forget`, added a
phase earlier, and had been silently skipping it ever since. That is the same defect as the README
claim count in the previous addendum: a list nothing derives is a list that is already wrong, still
plausible, and only as wrong as the last time somebody looked. `harness.PROBE_NAMES` is now the only
copy and the other three import it.

### What this proves, and what it does not

It proves that eight subjects return text exactly as written and three cannot be asked, and that the
nine strings are a place text breaks rather than every place it can. It does not prove the eight
normalise correctly - a store may be faithfully returning bytes that no longer mean what was meant -
and it says nothing about a character this probe did not write.

The ledger gains a thirteenth claim and loses nothing: `verbatim-all` - every subject returns a record
exactly as written - FAILS, with the three unreadable subjects named, for the same reason
`can-forget` fails. Five of thirteen claims now hold in every setting measured.

### What this costs

One probe, one mutant, one store primitive and about fifteen lines of adapter. The other two axes were
not re-rolled: `matrix.py --probes-only` re-measures the probes and reads retrieval and cost from disk,
because a new probe does not change how fast a server starts or how many questions it answers, and
re-running them would move numbers that did not change and invite the reader to think they had.
---

## Addendum 21: where the retrieval score comes from

The conformance probes got a mutation battery because a probe that has never failed is not a probe.
The retrieval axis never got the same treatment. Eleven subjects have been scored out of sixty for
several phases, and nothing here had ever measured what a subject has to do to score nothing, what the
maximum is, or what "not searching at all" looks like. Forty-two out of sixty was therefore a number
on a scale whose ends were both unknown - it could have been 95% of what the corpus allows, or the top
of a scale that ends at 44.

### Four controls, one of which cheats

`calibration.py` runs the same sixty questions against four controls. Three are the positive server
broken on purpose; the fourth is the answer key wired to a search tool.

| control | what it is | hits (A) | score (A) | hits (B) | score (B) |
|---|---|---|---|---|---|
| `oracle` | the corpus own answer key, wired to a search tool | 48/60 | **60/60** | 48/60 | **60/60** |
| `control` | the positive control term overlap | 25/60 | 37/60 | 32/60 | 44/60 |
| `blind-search` | the same three records to every question | 2/60 | 2/60 | 3/60 | 3/60 |
| `mute-search` | returns nothing, ever | 0/60 | 12/60 | 0/60 | 12/60 |

**The ceiling is 48 hits and it is reachable.** Twelve of the sixty questions have no answer. The
oracle answers all forty-eight and declines all twelve, so the most a search can hit is 48 - and
memory-mcp-1file is at 42 of them, 87% of the available maximum, with the control at 52%. That is a
different sentence from the one the table used to support, and the only one that could be checked.

**The floor of the score is 12, not 0.** Declining a question with no answer is correct, so a memory
that answers nothing collects all twelve. The hit count has a true floor of zero; the score every
paired test is computed from does not.

### The part that changes how the rest should be read

| subject | corpus A | corpus B written | corpus B as keywords |
|---|---|---|---|
| `statecore-mcp` | **0** | 12 | 12 |
| `memdb` | **6** | **2** | 16 |
| a memory that answers nothing | 12 | 12 | 12 |
| `server-memory` 1.0.0 and 2.0.0, `mcp-knowledge-graph` | 12 | 12 | 14 |

**A real subject can finish below a program that does nothing.** `statecore-mcp` scores zero on corpus
A and `memdb` six; on corpus B as written `memdb` scores two. All three answer every unanswerable
question and get none of them right, so they come in under a control that never answers anything.

And on corpus B asked as keywords, nobody does - the lowest score is `statecore-mcp` at exactly 12, a
tie rather than a loss. So the claim `silence-scores-better` is **MIXED**: true in three of the four
settings, false in the fourth. It was not reworded until it passed. The setting that breaks it is the
claim real scope, which is what the ledger exists to say.

The score is doing what it says. Silence is never punished and answering is only rewarded when the
answer is right - a defensible definition, and a paired test is meant to be built on one. But it is
not a ranking, and a subject that answers freely is penalised twice while one that says nothing is not
penalised at all. That is why the headline claim is stated in **hits**, where the floor really is zero.

### The oracle is allowed to cheat, and that is the point

`oracle-search` reads `retrieval_corpus.json` and returns the expected record. It is not a subject and
appears in no other table. Its only job is to make the ceiling a measurement instead of an assumption:
if the answer key does not score sixty, the failure is in the corpus or in the scoring, and no subject
should be graded on it. It also pins the twelve-point floor, because the oracle declines the
unanswerable questions by construction and gets them right for the same reason a mute server does.

### One more of my own mistakes

**22. The corpus the oracle is given was decided by argv order.** `--mutant=oracle-search` resolved the
`--cases` path when it was parsed, so `--mutant` before `--cases` would have handed the oracle corpus
A answers on a run over corpus B - an oracle that scores 48 on a corpus it was never given is either a
miracle or a bug, and it would have been the bug. Resolved after every option is read instead. Caught
while writing the script rather than by a run; recorded because the failure would have looked like a
very good result.

### What this does not establish

It does not say the questions are good ones. A corpus can have a reachable ceiling and still ask only
easy questions, which is what the bands, the second corpus and the phrasing pair are for - and the
validator still reports eleven one-word adversarial traps in corpus A against three in corpus B, which
is a real weakness in the weaker corpus and not one this phase addressed.

It also does not make the controls subjects, and it does not add a row to any subject score. Nothing
about any real server changed: what changed is what its number is quoted against.

### What this costs

One script, one generated table, two controls that already existed, one new one, and a step in a CI job
that was already running. The ledger gains three claims - `scale-ceiling` and `floor-not-zero` hold on
both corpora in both phrasings, `silence-scores-better` is MIXED - and seven of sixteen now hold
everywhere.
---

## Addendum 22: does every question measure something

A test is not validated by its score distribution. It is validated by asking, of every item, whether the
item separates anybody - and that question had never been put to either corpus here. A question every
subject answers and a question no subject answers carry exactly the same information about the
differences between subjects, which is none, and a corpus can be made mostly of those while reporting a
perfectly respectable spread of totals.

`items.py` computes difficulty `p` (share of subjects right) and discrimination `D` (top half by total
score minus bottom half) for all sixty questions on both corpora, excluding the subject that leaks state
because letting a leak decide which questions work is the same mistake as grading it.

### What it found

| corpus | band | questions | nobody can tell apart | mean p | mean D |
|---|---|---|---|---|---|
| A | easy | 16 | 0 | 0.39 | +0.64 |
| A | hard | 16 | 5 | 0.08 | +0.16 |
| A | adversarial | 16 | 0 | 0.22 | +0.44 |
| A | absent | 12 | 0 | 0.60 | +0.00 |
| B | easy | 16 | 0 | 0.31 | +0.62 |
| B | hard | 16 | 9 | 0.06 | +0.10 |
| B | adversarial | 16 | 0 | 0.24 | +0.48 |
| B | absent | 12 | 0 | 0.71 | -0.22 |

**The hard band is a wall.** Nine of corpus B hard questions and five of corpus A are answered by
nobody. A band that nobody can enter measures nothing between subjects; it is a constant that costs
every subject the same, and the mean of 0.06 says so more plainly than the band name does.

**The easy and adversarial bands work.** Mean discrimination of +0.64, +0.62 on easy and +0.44, +0.48
on adversarial is a test that separates a strong subject from a weak one, and it is worth saying
because it had only been assumed.

### The unanswerable band is a switch, not a gradient

This is the find of the phase, and it came from looking at the raw per-subject counts rather than the
totals. **Every subject either declines all twelve unanswerable questions or declines none of them.**
There is no subject in the middle. So the band is not twelve questions about anything; it is one binary
habit, and the score hands whoever has that habit twelve of its sixty points - twenty percent of every
number in every paired test.

And the habit is not ability. Its discrimination is +0.00 on corpus A and **-0.22** on corpus B; asked
as keywords, +0.13 and **-0.40**. On corpus B the better subjects are the ones who speak rather than
decline, so the band that is supposed to reward restraint is punishing skill.

That single fact explains something the ledger had been reporting without being able to say. The pair
zenbrain against the control, on corpus A as written:

```
  only zenbrain correct   15
  only control correct    12
  exact McNemar p = 0.7011  -> not separated by this corpus
  without the 12 unanswerable questions: 15-0, p = 0.0001 -> separated
```

zenbrain wins fifteen answerable questions to none. The switch hands the control back exactly twelve,
turning 15-0 into 15-12 and a p of 0.0001 into 0.70. Asked as keywords the same switch runs the other
way and produces the mirror-image flip. `compare.py` now runs both tests and names the switch when it
decides the outcome, because a tool that publishes a number has to publish what the number rests on.

The claim `absent-band-flat` - the unanswerable questions give the stronger subjects no advantage - is
**MIXED**: a sign, not a size, because a size would have been chosen after looking. It holds on corpus
A as written and on corpus B both ways, and fails on corpus A as keywords at +0.13.

### The one-word-trap warning, measured

The validator has been warning that an adversarial question whose competitor shares only one word is
"the weakest kind". Mean discrimination is +0.42 across the eleven narrow traps in corpus A against
+0.48 across the five wider ones, and +0.33 against +0.51 on corpus B. The warning points the right way
and two groups that size cannot settle it. What the measurement changes is that the warning can now be
ignored or obeyed knowingly instead of on the strength of an adjective.

### Mistakes

**23. The trap rule lived inside the validator.** `items.py` needed the same definition of a trap and
would have grown a second copy of it - the defect this repository has now recorded three times, in the
README claim count, in the four probe lists and here. `rivals_of()` was pulled out of `check()` and both
tools call it. The first attempt at the extraction dropped the `want` variable the error message needs,
which the validator caught immediately by raising, and which is why the refactor was re-run against the
old output rather than trusted.

**24. A blank line.** The new README section was inserted with a single newline after the preceding
section, so a heading would have rendered flush against the paragraph above it. Markdown tolerates it in
some renderers and not others, which is a good definition of a bug nobody notices. Fixed before pushing.
**25. The trap table only existed in the generated file.** The CI step for this phase runs `items.py`
and greps its output for the two things the phase is about; the trap comparison had been written only
into `ITEMS.md`, so the job failed on its first push. The check was right and the tool was wrong,
and the fix belonged in the tool: a number that lives only inside a generated document is a number
nothing verifies. It prints to the console now, and the console is what CI reads.
---

## Addendum 24: how many of the comparisons this corpus can actually make

Every row of the retrieval table sits next to every other row, and the repository has been inviting
fifty-five comparisons while testing one at a time on request. Nobody had asked the instrument how many
of them it can settle.

`resolution.py` runs the exact McNemar test for all 55 pairs, on both corpora, in both phrasings, on both
metrics:

| corpus | phrasing | on the score | on hits alone |
|---|---|---|---|
| A | written | 39 of 55 | 43 of 55 |
| A | keywords | 41 of 55 | 42 of 55 |
| B | written | 37 of 55 | 38 of 55 |
| B | keywords | 31 of 55 | 39 of 55 |

Roughly two thirds, and fourteen pairs change verdict between the two phrasings on each corpus. That is
the resolution of the instrument, and it is now a number rather than an impression.

### The top of the table is a three-way tie, on the score

The groups the separation relation cannot split, on corpus A as written:

- seven subjects - `server-memory` twice, `memento`, `memdb`, `memory-lean`, `mcp-knowledge-graph` and
  `mcp-duckdb-memory-server` - of whose 21 internal pairs 8 are separated directly. A staircase.
- three subjects - `control`, `zenbrain`, `memory-mcp-1file` - of whose 3 internal pairs **none** is.
  A genuine tie, at the top of the table, between the leader, the runner-up and a toy server with a
  keyword search bolted on.

### And the two metrics disagree about which of them is ahead

This is the phase's real find. The leader against each of the others, on both metrics:

| against | score, written | score, keywords | hits, written | hits, keywords |
|---|---|---|---|---|
| `control` | 0.345 | 1.000 | **0.000** | **0.002** |
| `zenbrain` | 0.581 | **0.022** | 0.774 | **0.022** |
| `memory-lean` | **0.009** | 0.065 | **0.000** | **0.000** |

**The leader beats the control never on the score and three times out of four on hits.** The mechanism is
the one from addendum 22: the leader answers eleven of the twelve unanswerable questions, the control
declines all twelve, and the score hands eleven points straight back. Remove the switch and the gap is
there in three of four readings.

And the runner-up behaves the other way round. zenbrain against the control is separated on the score in
three of four readings and on hits in one of four. So on the score the runner-up looks better than the
leader relative to the same yardstick, and on hits the leader looks better than the runner-up. **Each
metric prefers a different subject.**

That is now the ledger's `metrics-agree` claim, and it **FAILS in all four settings**.

### Three of my own mistakes, all caught on screen

**27. Two lists read from two different keys of one dictionary.** Pairs were stored in file order in one
place and looked up alphabetically sorted in another, so the "separated from" list and the "not separated
from" list contradicted each other in the same console output - `mcp-duckdb-memory-server` appeared in
both. One canonical key per pair now.

**28. The tie groups silently collapsed when the metric dimension arrived.** `tie_groups` still read the
two-key block after every block gained a third key, so it found no pairs, unioned nothing, and reported
all eleven subjects as singletons - each one helpfully labelled "alone: separated from everybody", which
is a sentence contradicted by the table three lines above it. A `KeyError` would have been kinder; the
`.get(...) or {}` that made it silent is the reason it was not.

**29. The first version reported the score only, and the score says the opposite.** Before the metric
dimension existed, the leader's row said "not separated from the control", full stop. That is true, and
it is half the story, and it is the half that would have been published. The hits column - 0.000 and
0.002 - was added because the tie looked too neat for a subject that gets seventeen more questions right.

### What this does not do

It does not resolve the tie. Sixty questions cannot separate a leader from a runner-up on the score, and
repeating the same sixty cannot fix that; only more questions, or different ones, can. What it does is
say so in numbers a reader can check, so that "memory-mcp-1file leads" is published with its scope
attached instead of standing alone.

### What this costs

One script, one generated table, one claim that fails four times, and no re-measurement: it reads the
rows that were already on disk. Seven of eighteen claims hold everywhere.
---

## Addendum 25: cost is a function of how much is stored, and every figure here was shallow

The cost table quotes a write latency taken on an empty store and a search latency taken over the
72-record retrieval corpus. Agents store thousands over months. If either number depends on depth, the
table describes the shallow end of a curve and says nothing about what an agent pays.

### The prediction, written first

`growth.py` records, before running anything, what it expects: the control appends one line under a
lock and should be flat; the reference server parses its store into a model and rewrites the whole file
on every write - the documented reason it drops unknown fields - and should grow; memento inserts a row
into SQLite and should be flat.

### What happened

The reference server does not grow. At 3000 records its write cost is the same as at 25, because
rewriting a few hundred kilobytes is cheaper than the JSON-RPC round trip that carries the write. The
mechanism I predicted is real and too small to see at any depth an agent reaches - which is the good
outcome, and the first time in this project that a prediction has failed in the reassuring direction.

What did grow was the write cost of four subjects that rewrite nothing wholesale:

| subject | write at 25 records | at 2000 | growth | runs agreeing |
|---|---|---|---|---|
| `statecore-mcp` | 4.9 ms | 13.7 ms | x2.9 | 2 of 2 |
| `mcp-knowledge-graph` | 6.3 ms | 14.3 ms | x1.9 | 2 of 2 |
| `memory-lean` | 5.0 ms | 10.5 ms | x1.8 | 2 of 2 |
| `server-memory 1.0.0` | 6.8 ms | 13.8 ms | x1.7 | 1 of 1 |

### The searches are where it bites

Every subject costs more to search as the store fills. On memento it is not a slope, it is a cliff:

| records | 100 | 250 | 500 | 1000 | 2000 |
|---|---|---|---|---|---|
| memento, run 1 | 43 ms | 45 ms | 170 ms | **3408 ms** | **6671 ms** |
| memento, run 2 | 48 ms | 52 ms | 192 ms | **4394 ms** | **8454 ms** |

Six to eight seconds per search at two thousand records, in both runs, roughly doubling for every
doubling past five hundred. The published figure is 5 ms, taken over 72 records, and it is not wrong -
it is a measurement of a different machine from the one anybody would deploy.

The other subjects grow more gently and still grow: the control by 61x (it reads the whole store and
filters locally), duckdb by 54x to 594 ms, memdb by 25x, and the rest by three to six. Not one of the
eleven is flat, which is why the ledger claim `search-is-flat` **FAILS**.

### Two things this does not say

It does not say memento is bad. It says that a memory which is fast at seventy records is not
therefore fast at two thousand, and that a latency quoted without its depth is a number about a
corpus. The same table that makes memento look expensive at depth is the one that shows it storing a
million records for free in addendum 9.

It does not establish where each curve ends. Three thousand records is a fortnight for one agent and an
hour for another; the measurement bounds the curve, it does not close it.

### Mistakes

**30. The tool threw away other subjects when I re-ran one.** The first version of `growth.py` rewrote
GROWTH.md from the run in hand, so repeating memento to check a 6.7-second number would have deleted ten
subjects from the table. Runs accumulate in `results/growth.json` and the table is built from all of
them, which also gives the "runs agreeing" column - the only reason the four write-growth findings can
be told apart from noise.

**31. The first depth was too shallow to answer the question.** Five hundred records showed every
subject flat, including the ones that turn out not to be. The per-call transport overhead is ten
milliseconds; store work at five hundred records is a fraction of a millisecond. A flat line there says
the work is below the noise floor, not that it is absent, and the checkpoints now go to three thousand
for exactly that reason.

### What this costs

One script, one generated table, one claim that fails, and about twenty minutes of measuring. No
retrieval number and no probe verdict moved.
---

## Addendum 26: a corpus written by a different model, because a free one was already installed

The longest-open limit in this repository is that both retrieval corpora were written by the same hand
and the same model family as the analysis that grades them. Every claim of the form "corpus B
replicates corpus A" has carried that asterisk, and no amount of care produces independence from an
author who is the author.

### The tool was already here

This machine runs Ollama, with model families this repository has never used: qwen3.5 (4B, local),
ornith (9B), nimble, and cloud-proxied GLM and DeepSeek. The local models cannot load - 7.7 GB of RAM
with 341 MB free is not enough for a 3.4 GB model, and the attempt fails with an allocation error rather
than a queue. The cloud-proxied **glm-5.3** answers in about a second, needs no local memory, and is a
different family from the model writing this. That is the free tool, and it was installed already.

### The corpus

`author.py` gives the model the band rules and a one-paragraph brief for a municipal observatory whose
operations log is to be the store, and gives it nothing else: no corpus, no question, no result, no
analysis, no subject name. It asks for records in six themed batches and questions band by band.

`repair.py` then validates what came back and regenerates only what fails. The first draft was rejected
five ways - thirteen records answering two questions, six unanswerable questions that one record
actually covered, an adversarial item with nothing competing, and a hard item sharing two words with its
answer - which is the validator doing exactly what it exists for. After one repair round: **zero errors**,
all four bands populated, seventy-two records.

### What it found

| subject | corpus A | corpus B | **corpus C** |
|---|---|---|---|
| `memory-mcp-1file` | 42 | 45 | **40** |
| `control` | 25 | 32 | **31** |
| `zenbrain` | 40 | 33 | **31** |
| `memento` | 14 | 19 | **17** |
| `mcp-duckdb-memory-server` | 12 | 13 | **12** |
| five subjects | 0-14 | 0-1 | **0** |

**Spearman 0.78 against corpus A, 0.91 against corpus B.** The ranking is not an artefact of one author.

And the part worth more than the correlation: **the top of the table behaves exactly as addendum 24
said it would.** The leader is alone at 40 of 59, and behind it the control and zenbrain tie at 31 - the
same three-way shape, from a model that has never seen the questions, the analysis, or the fact that a
benchmark exists. A tie produced by one corpus is a property of the questions; the same tie produced by
two corpora and then by a third author is a property of the subjects.

### Three mistakes, all in the plumbing

**33. The JSON extractor took the first bracket to the last.** A reasoning model echoes the output
template back inside its own thinking before answering, so every reply contained a second, fake array.
Slicing from the first opener to the last closer spanned both and parsed as neither, and every band came
back "0 of 16" - which I read as the model refusing to write questions. Scanning backwards for the last
balanced JSON fixed all four bands at once.

**34. Thinking is billed to the same budget as the answer.** One reply spent 1,700 of its 2,200 tokens
deliberating and had its array cut off mid-object. `done_reason: length` is the difference between "the
model produced nothing" and "the model was not allowed to finish", and I had not been reading it.

**35. Forcing JSON made it worse.** `format: "json"` on a sixteen-question ask returned zero characters
after burning the entire budget. Constraining the decoder does not stop the reasoning that precedes it;
only a smaller question does. The hard and adversarial bands are now asked one question at a time,
sixteen times, which is slower and works.

### What this does not settle

A different model is not a different method. It is one prompt, one temperature and one brief, and it
writes the same tidy synthetic world - short declarative records, no contradictions, no noise. Every
corpus this repository uses is easier than a real memory store, and a third author does not change that.
What it changes is the specific objection that author and analyst might share a blind spot: they no
longer share an author.

The corpus also has 59 questions rather than 60, because the model produced fifteen adversarial items
and the count was left as authored rather than padded to match.

### What this costs

Two scripts, one generated corpus, one generated report, and about forty minutes of model calls on a
machine already running the model. Nothing about the ten probes, the calibration, the item analysis or
the growth curves changed.




### What this does not say

It does not say the hard band should be deleted: a question nobody answers today may be answered by the
next subject, and dropping items after seeing them answered is how a corpus gets fitted to its table.
It does not say the absent band should be removed from the score either - declining correctly is a real
virtue, and the finding is that it is being counted as if it were the same virtue, worth the same twenty
percent, as answering. What it says is that the score contains a twelve-point binary term unrelated to
retrieval quality, that the paired tests now report around it, and that the headline claim was already
stated in hits for exactly this reason.

### What this costs

One script, one generated table, one extracted function, and roughly thirty lines in `compare.py`. No
subject verdict and no retrieval number moved; the corpus was not edited, which is why nothing needed
re-measuring. Seven of seventeen claims hold everywhere, four of the additions in the last two phases
being MIXED on purpose.
---

## Addendum 23: the hard band, and an exclusion doing the work of a conclusion

Addendum 22 ended by naming the hard band as the next repair: nine of corpus B hard questions and five
of corpus A "answered correctly by nobody at all", mean p of 0.06 and 0.08. That was wrong, and it was
wrong because of a decision made one paragraph earlier for an entirely good reason.

The item analysis excludes the subject that leaks state. It is right to: its per-question answers
describe leaked state, and letting a leak decide which questions work would be the same mistake as
grading it. But the excluded subject is memory-mcp-1file, which answers **twelve of the sixteen hard
questions on corpus A and thirteen of sixteen on corpus B**. Removing the strongest subject and then
reporting that the band measures nothing is not an analysis of the band; it is an analysis of the field
with its best member deleted.

### What the band actually looks like

`items.py` now loads the excluded subject as well, tags it, and reports it beside the rest:

| corpus | band | answered by (in scope) | the excluded leader |
|---|---|---|---|
| A | easy | 6 of 10 - zenbrain 16, control 16, memory-lean 14 | 16 |
| A | hard | 3 of 10 - zenbrain 8, memento 4, duckdb 1 | **12** |
| A | adversarial | 4 of 10 - zenbrain 16, control 9, memento 7 | 14 |
| B | easy | 4 of 10 - zenbrain 16, control 16, memento 9 | 16 |
| B | hard | 4 of 10 - memento 6, zenbrain 2, memdb 1 | **13** |
| B | adversarial | 4 of 10 - zenbrain 15, control 15, memento 4 | 16 |

The hard band is a steep gradient - 12, 8, 4, 1, then six subjects at zero - not a wall. It does not
need repairing. What it needs is the truth about how few subjects it reaches.

### The number that matters more than the band

Across all three answerable bands, **four of the ten in-scope subjects answer no question at all on
corpus A, and five of ten on corpus B**. They score exactly twelve, which is their unanswerable-band
points and nothing else. The table of eleven subjects is produced by six of them, and most of it by
three. That is the honest size of the field this repository measures, and it has been sitting under
every claim in the ledger since the table was first built.

### And the band keeps its top while losing its order

The leader holds twelve hard questions on corpus A and thirteen on corpus B - stable. Beneath it,
zenbrain goes from eight to two and memento from four to six. So the hard band reproduces its leader
and not its ranking, which is the same instability the neighbouring-pair test found for the table as a
whole, now with a location: the bands that separate lexical subjects from semantic ones are the bands
where the order will not hold.

### One more of my own mistakes

**26. The exclusion decided the conclusion.** Addendum 22 said the hard band was answered by nobody. It
was answered by four subjects, one of which the analysis had removed two paragraphs earlier. The
failure was not the exclusion - it was reporting a property of the *questions* from a set of subjects
that had been filtered for an unrelated reason. `items.py` loads every subject now and tags which are
in scope, so the excluded row is visible beside the rest instead of absent from them.

This is the fourth time in this project that a number was wrong because of what had been left out
rather than what had been computed: the eight-probe suite that skipped forget, `check.py` that never
learned the list, the README count nothing derived, and now an analysis whose filter silently became a
finding.

### What this does not change

No score moves, no verdict moves, and the corpus is untouched. The ledger is unchanged at seven of
seventeen: the claims were written against scores, and this phase changed only what can be said about
the questions that produce them.

### What this costs

One function, one table, and a retraction of a paragraph published one phase earlier. The retraction is
the point - a repository that only ever appends findings accumulates wrong ones, and this one has now
corrected itself twenty-six times in writing.

## Addendum 27: what a tie is, and what it would cost to break one

Addendum 24 ended with an open item: `resolution.py` says *which* pairs this corpus cannot separate and
never said *why not*. Forty-of-forty and 42-of-60 look the same in a table and are different facts about
the subjects. The word tie was covering at least three of them at once.

### The predictions, written first

Four, before `band.py` existed:

1. The top three would be a genuine three-way tie, and corpus C would put zenbrain at the top as often as
   the control.
2. The price of breaking a top pair would be a few hundred questions - the kind of number that says *ask
   more* rather than *stop asking*.
3. A pair that disagrees on almost nothing would always look like a tie, and a pair that disagrees on
   almost everything would look like a difference.
4. No corpus would separate a pair that splits its disagreements evenly, because more questions raise
   both sides at the same rate.

### What happened to them

**One right, one wrong, two half right.** The fourth held exactly and is the reason the tool exists. The
first was wrong in an interesting direction: zenbrain leads **none** of the twelve rulers. It is not the
other half of a tie; it sits in the same band as the leader and is never once first. The second was right
for one pair and badly wrong for another - the same contest costs 371 questions on one corpus and 11,825
on the next. The third is right about the ends and wrong about the middle, which is where the top of this
table lives.

### Twelve rulers, and the winner is a property of the ruler

A ruler is one corpus, in one phrasing, on one metric.

| subject | rulers at the top | of |
|---|---|---|
| `memory-mcp-1file` 0.9.2 | **9** | 12 |
| `control` 1.0.0 | **4** | 12 |
| the other nine subjects | 0 | 12 |

The counts add to thirteen because corpus A asked as keywords puts them level. So *the best memory server
here* is not a sentence until a corpus, a phrasing and a metric are in front of it - and the positive
control, two hundred lines of append-only file, is first on four of the twelve. That has been true since
the first matrix and has never been put in one line: the top of this ranking is contested by the control,
and which of the two wins depends on how the questions are worded and on whether silence scores.

### The price, which is the useful part

The exact McNemar test is a poor instrument for a question of size and a good one for a question of
visibility. A split of b against c out of n questions carries two numbers: how surprising it is, and how
large it would have to be to be called. `band.py` computes the second by finding the number of
disagreements at which the same test reaches 80% power at the observed win rate, then dividing by the rate
at which these two subjects disagree at all.

| pair, corpus | answered differently | split | p | questions needed |
|---|---|---|---|---|
| `control` vs `1file`, A | 28 of 60 | 11-17 | 0.345 | **371** |
| `1file` vs `zenbrain`, A | 13 of 60 | 8-5 | 0.581 | **679** |
| `control` vs `1file`, C | 27 of 59 | 15-12 | 0.701 | **1,401** |
| `control` vs `zenbrain`, A | 27 of 60 | 12-15 | 0.701 | **1,425** |
| `control` vs `1file`, B | 25 of 60 | 12-13 | 1.000 | **11,825** |

Read the first and the last together. Both are *not separated*. One needs a corpus six times this one;
the other needs a corpus two hundred times this one, which is another way of saying that on corpus B the
control and the leader disagree on twenty-five questions, win twelve and thirteen of them, and no
reasonable corpus will ever call it. The two are the same row of a table and completely different
findings.

### A fourth kind I did not predict

The first version put every unseparated pair with a direction in one box, which filed the
11,825-question pair beside the 371-question one. It needed a fourth: **out of reach**, for a margin that
exists and would cost more than a thousand questions to resolve. Twenty-seven of the 198 unseparated
pair-rulers are that, and reporting them as *ask more* would have been the same mistake as the empty
comparison two sections down - a number formatted as a conclusion it does not support.

| kind | pair-rulers |
|---|---|
| identical | 73 |
| no direction | 4 |
| small but real | 94 |
| out of reach | 27 |
| separated now | 462 |

### Not separated is not similar

The widest divergence behind a non-separation is 36 of 60 questions. `memory-lean` and the leader answer
thirty-six questions differently and corpus A asked as keywords declines to rank them, at p = 0.065. The
narrowest is one question in forty-eight. Both were *tied* in the previous table, and a reader choosing a
memory server needs to know which end of that column their pair is on.

### The 0 of 0 that stood in RESOLUTION.md for three phases

While extending the separation analysis to corpus C I found the between-corpora table had been compared
with a two-part key against a dict keyed by three parts. Every row of it read **0 of 0**: an empty set
compared with an empty set, printed under the heading *pairs whose verdict differs between corpus A and
corpus B*. As a sentence, an empty comparison is indistinguishable from a finding, and this one read as
*the corpora never disagree* - the strongest possible version of a result nobody had computed.

Corrected, it is the best number in the phase:

| corpora | verdicts that differ, on the score, as written |
|---|---|
| A vs B | **16 of 55** |
| A vs C | **16 of 55** |
| B vs C | **0 of 55** |

Two corpora written by different authors about different fictional worlds reach the **same verdict on all
fifty-five pairs**. The corpus that disagrees with both is corpus A - the one written before the band
rules were written down. So the replication that Addendum 26 could only claim from a rank correlation is
exact at the level of the verdict, and what it separates is the specification rather than the author.

### Three more of my own mistakes

**36. A comparison with an empty denominator, reported as a result.** `blocks.get((corpus, shape))`
against keys of `(corpus, shape, metric)`. Three phases, one table, every row zero. CI now fails on the
string `0 of 0` in RESOLUTION.md - a check written to catch this exact class, which could have been
written three phases ago.

**37. Then I wrote the same bug twice in one afternoon.** `band.py` looked up a three-part key in a
four-part dict and printed three empty tables; `claims.py` did it again and returned *unmeasured* for a
comparison it had already computed. The fix was not another careful lookup, it was a named function -
`band.cell()` - whose docstring records how many times this has happened. Two of the three occurrences
were caught by reading the output rather than by anything failing.

**38. A power calculation that could not finish, then could not count.** The first version walked the
disagreement count upward and called `math.comb(d, k) / 2**d`, which overflows past a few thousand; it ran
for minutes before I killed it. Rewritten in log space with bisection it then disagreed with brute force
by five questions: the exact test's power is a **sawtooth**, not a ramp, because its rejection threshold
rises by one minority vote every two disagreements - 149 disagreements clear 80%, 153 does not, 154
clears it again. Bisection finds a number that works; *how many* has to walk back to the first that works.

### What this does not say

The price is computed from one observed split, and a split of thirteen has a wide interval on its win
rate. It is a floor on the effort, not a promise about the outcome. It says nothing about whether a larger
corpus keeps the same win rate - if the two subjects differ in a way the next hundred questions do not
touch, the price is infinite and the estimate is meaningless. What it does say is that the ties at the top
of this table are of two different kinds, and only one of them is a shortage of questions.

### What this costs

One script, one generated table, three claims (one of which fails, and should), and no re-measurement - it
reads the rows already on disk. The open item from Addendum 24 is closed, and closed by being replaced
with a better question.

## Addendum 28: does the retrieval score have teeth, and which ones

The probes earned their credibility the hard way, in Addendum 19: twelve broken copies of the positive
control, one promise broken each, and a verdict written down before every run. The retrieval score has
never had that. It has a measured ceiling, a measured floor and a pair of corpora, and all of them answer
the question *is the scale calibrated*. None of them answers the other one: **which defects move this
number, and which does it not see at all.**

`retrieval_mutants.py` is four levers on the control's search, and it is the same instrument pointed at
the instrument.

### The predictions, written first

Against the calibration numbers - 25 hits of 60, a score of 37, every correct answer already in first
place, no unanswerable question answered:

1. **reverse-rank** (the same records, worst first): hits 25, hit@1 **0**, score 37, speaks 0.
2. **one-result** (one answer instead of three): hits 25, hit@1 25, score 37, speaks 0 - a k that is
   already one of one.
3. **greedy-match** (one shared word is enough): speaks **12**, and eleven or twelve points of score
   given back.
4. **strict-match** (every word is required): hits fall, speaks 0.

### What happened

| lever | hits | hit@1 | score | spoke |
|---|---|---|---|---|
| *(clean control)* | 25 | 25 | 37 | 0 |
| `reverse-rank` | 25 | **15** (predicted 0) | 37 | 0 |
| `one-result` | 25 | 25 | 37 | 0 |
| `greedy-match` | **36** | 32 | **43** | 5 (predicted 12) |
| `strict-match` | 15 | 15 | 27 | 0 |

Two right, two wrong, and the wrong ones are the interesting ones.

**The score cannot see the order of the answers it counts.** Reversing the result list leaves the set
identical, so hit@3 and the score do not move by a single point, and hit@1 falls from 25 to 15. Every
comparison in this repository is computed from that score. A memory server that puts the right record
third and one that puts it first are the same subject here, and an agent that reads only the top result is
not being measured by this table at all.

The prediction of zero was wrong because of the questions with exactly one matching record: reversing a
list of one changes nothing. Fifteen of the control's twenty-five correct answers come from a search that
had no ranking to get wrong. I would not have known that number if the prediction had been right.

**The score rewards answering, and cannot tell answering from knowing.** Lower the bar to one shared word
and hits go from 25 to 36, the score from 37 to **43**, and only five of the twelve unanswerable questions
are answered - so the careless matcher comes out *ahead of the control it was built to break*, and level
with the best real server in the table.

That is the finding. The retrieval score is close to monotone in how eagerly a subject answers, and the
only thing pushing the other way is the twelve questions with no answer. A memory that returns junk and
never declines outranks a memory that retrieves well and says so when it does not know. The
`score-prefers-recalcitrance` claim in the ledger now tests exactly this and **FAILS**, as does
`score-sees-ordering`: both are statements this repository would have made without checking.

My prediction of twelve unanswerable questions answered was wrong at five, and the error is what makes
the defect pay: one shared word between a question and a record is rarer than I assumed, so the cost of
answering everything is smaller than the benefit of finding more.

### The real subjects, judged the way an agent reads

The rows have carried hit@1 beside hit@3 since the first matrix and nobody had asked whether the choice
matters. On corpus A as written, **41 of 55 pairs are separated on hit@1 and 43 on hit@3, and 6 pairs
reach a different verdict depending on how many results are read**. `memdb` is the reason: it finds six
records and puts none of them first, so it is separated from three subjects on hit@3 and from none of them
on hit@1. On corpus B the count is three pairs, including the control against the leader - separated on
hit@3, p = 0.057 on hit@1.

So a tenth of the conclusions in a table of eleven subjects depend on a property of the *reader*, not of
the server. That is worth a column and a sentence, and it now has both.

### Two more of my own mistakes

**39. The baseline was saved under a different name.** The two new claims reported *unmeasured* on their
first run because I looked for the clean control at `results/retrieval-control-A.json` and
`calibration.py` had saved it as `results/calibration-control-A.json`. The ledger did exactly what it
should - a missing file is an unmeasured claim and not a passing one - and the numbers had been on disk
the whole time.

**40. A smoke run overwrote a measurement.** `retrieval_mutants.py --repeat=1` wrote its results to the
same file names as the repeat-3 run, so the fast check in CI would have quietly replaced the measurement
the claim ledger reads with a faster answer to the same question. The repeat is in the file name now when
it is not the committed one.

### What this does not say

It does not say the corpus is bad. It says which defects it detects, with a number attached to each - the
same thing the probe battery says about the probes, and for the same reason. A set membership question is
the right question for a memory asked to surface candidates; hit@3 is the honest name for it. What the
battery establishes is that the table has been read as a ranking, and that the two readings of it are not
the same answer for a tenth of its pairs.

### What this costs

One script, four levers, two claims that fail, and about two minutes of runtime per corpus. The levers are
four lines each in the adapter. Everything else - the score, the matrix, every published conclusion -
stands exactly as it was, and now says what it does not measure.

## Addendum 29: four questions, and the answer a caller actually gets

Addendum 28 ended with a fact and no consequence. The score does not move when an answer moves from first
to third, so every paired test in this repository is computed from a number that an agent does not
experience. The consequence is a metric that was never computed: **the first record back, plus a correct
silence** - what you get if you ask a question, read the first line, and stop.

That is one line in `compare.py` and a second metric in `resolution.py`. What it cost was re-reading
every number in the table under a different question.

### The expectation I had, and what happened to it

I expected the leader to change under the agent metric in most of the six corpus and phrasing
combinations. It changed in **two** - corpus A as keywords and corpus B as written - because most of the
disagreement between the two questions is in the middle of the table and not at the top. The top of the
table is where the numbers are furthest apart and therefore where a change of a few records is least
likely to reorder anything. My expectation was a belief about where a metric bites, and it was wrong
about the place.

What did survive is bigger and was not what I was looking for.

### First place, on each of the four questions

Twenty-four rulers: three corpora, two phrasings, four metrics.

| subject | rulers at the top |
|---|---|
| `memory-mcp-1file` | **15 of 24** |
| `control` | **10 of 24** |
| `zenbrain` | **1 of 24** |

The ten belong to the positive control, and eight of them are the two questions that are not the score:

| metric | who is first | of six corpus-phrasings |
|---|---|---|
| `hits` - right record in the top three | `memory-mcp-1file` | **6** |
| `hit1` - right record first | `memory-mcp-1file` | **5** (one level with the control) |
| `score` - top three, plus silence | `control` 3, `1file` 2, level once | split |
| `top` - first record, plus silence | `control` | **5** |

**On the only one of the four that a caller experiences directly, a two-hundred-line append-only file with
term overlap is first on five of six corpora and phrasings**, by four to twelve points, ahead of every real
memory server in the table. It is not a tie and it is not a near thing: on corpus C as keywords it is 42
against 32.

That is the finding this repository was built to be able to make and had not made. It is not that the
servers are bad; five of the eleven answer nothing at all on these corpora, and the ones that answer do
real work. It is that the quantity being sold - the right thing, first, or silence - is delivered better
by a text file and a substring count than by any of the systems built for it.

### Every gap is zero or negative

Reading the same rows as an agent instead of as a scorer moves every subject down or leaves it level. Not
one subject in three corpora gains. `memento` loses thirteen on corpus B, the leader ten on corpus C,
`memdb` six on corpus A.

So the score is a generous reading and never a harsh one. Every subject's published number is the best
case of what its own rows support, and the case is optimistic by an amount that varies from zero to
thirteen points depending on how far down the ranking the subject puts its correct answers.

### Nine of fifty-five pairs change verdict

On corpus A as written, the two readings separate a different set of pairs: **9 of 55**, in both
directions. `memdb` against `server-memory` is separated on the agent reading at p = 0.000 and not on the
score at p = 0.238; `duckdb` against `zenbrain` is separated on the score at p = 0.017 and not at
p = 0.175 on the agent reading. A sixth of the conclusions in the table depend on which of the two a
reader picks, and one of them is the one the table publishes.

### One more of my own mistakes

**41. The report had its writer block in the wrong function.** `agent.py` raised `NameError: path` on its
first run because the paragraphs after the pair table were indented into `write_switch` instead of
`write_md`. Caught immediately, and worth writing down only because it is the third time this phase that
a generated file was wrong in a way the generator could not see: the tool ran, printed its summary and
wrote nothing.

### What this does not say

It does not say the score is the wrong metric or that the table should be rebuilt on `top`. A memory
asked to surface candidates is doing its job when the right candidate is among them, and a caller that
reads all three gets what it paid for. It says the table has one number in it and four questions behind
it, that the one published is the only one of the four no caller experiences directly, and that the
answer to the question a caller does experience is not the answer the table gives.

### What this costs

One function in `compare.py`, one metric in two tools, one report, and a claim that fails. No new
measurement: every number here comes from rows that were already on disk. The retrieval table, the tie
analysis and the mutation battery all stand exactly as they were, and now the choice inside them is
visible.

## Addendum 30: a corpus with no author, and what it did to the table

The limit has been open since the second corpus: the analyst writes the questions and then grades them,
so agreement between corpora proves less than it looks. A third corpus answered it once by using a
different model. This phase answered it by removing the author instead of replacing him.

The records are the real `package.json` files of 397 installed packages - real names, real descriptions,
real version strings, in whatever state their authors left them. The questions are derived by rule:
sixteen verbatim, sixteen with every third long word removed, sixteen about packages whose authors
happened to use three or more of the same long words, and twelve about **real packages that were left out
of the store**. No sentence was written for this corpus, and no question was chosen by anyone who knew an
answer.

### What it did to the table

| subject | corpus A | corpus B | corpus C | real text |
|---|---|---|---|---|
| `control` | 37 | 44 | 43 | **60** |
| `memory-lean` | 26 | 12 | 12 | **59** |
| `mcp-duckdb-memory-server` | 24 | 25 | 23 | **59** |
| `zenbrain` | 40 | 33 | 31 | 48 |
| `memory-mcp-1file` | 43 | 45 | 40 | 47 |
| `mcp-knowledge-graph` | 12 | 12 | 12 | **45** |
| `server-memory` 1.0.0 and 2.0.0 | 12 | 12 | 12 | **45** |
| `memento` | 14 | 19 | 17 | 23 |
| `statecore-mcp` | 0 | 12 | 12 | 12 |
| `memdb` | 6 | 2 | 0 | 0 |

**The five subjects that answered nothing answered.** On the authored corpora `server-memory`,
`mcp-knowledge-graph` and `statecore-mcp` score exactly twelve - the points for declining - and the finding
was published in Addendum 23 as "four of ten answers no question at all". On real text the first two
answer **33 of 48**. Nothing about either subject changed. The questions did.

That is the correction this phase has to make, and it is mine. "The smallest servers here find nothing at
all" was true of three corpora and false of a fourth, and the difference is not the author - it is that
the authored corpora paraphrase and the real corpus asks with the record's own words. A word matcher is
useless against a paraphrase and excellent against a near-quote. The table was measuring the first while
being read as a measure of memory, and the ledger's `small-servers-silent` claim has carried that
overclaim since it was written.

The claim is left standing with its scope - it holds on the corpora it was written against - and a second
one now states the version that travels. `silent-everywhere` asks whether those subjects are silent on
real text too, and it **FAILS**: `server-memory` answers 33 of 48, `mcp-knowledge-graph` answers 33 of
48, and only `statecore-mcp` is still silent everywhere.

**The leader changes entirely.** The positive control scores **60 of 60** on real text - the ceiling this
repository measured against the answer key, reached by a file that appends lines and counts words.
`memory-lean`, at the floor of every authored corpus, scores 59. `memory-mcp-1file`, first on fifteen of
twenty-four authored rulers, is fifth at 47. On the metric a caller reads the control still wins (59 of
60), so that part of the previous phase survives contact with real text and the top of the table does
not.

**The rank correlation is the honest error bar.** Real against corpus A is 0.80 on the score, against B
0.64, against C 0.68. Put that beside B vs C at **0.909** and the picture inverts: two corpora written by
different authors about different worlds agree with each other better than either agrees with real text.

### The corpus cannot test paraphrase, and the validator says so

`validate_corpus.py` fails the corpus on the hard band: all sixteen hard questions still share more than
half their long words with the record that answers them, median share 1.00. Removing every third word from
a real sentence leaves a sentence a substring counter can answer.

I could have tuned the rule until the validator passed - thin until the share dropped below half. I did
not, because that is fitting the corpus to a threshold that was written for a different kind of corpus,
and the failure is the more useful result: **real records are free, real questions are nearly free, and a
paraphrased band needs somebody to paraphrase.** An authorless corpus can test recognition, discrimination
and refusal. It cannot test understanding, and that is a limit no sampling rule removes.

### One more of my own mistakes

**42. The rule produced two bands that were not the bands they claimed.** The first build generated 3 adversarial
questions instead of 16, because a stride sample of 72 packages almost never contains the confusable pairs
the band needs. Fixed by choosing the pairs first and filling the store around them - but the lesson is
the same one the validator caught: a mechanical rule has to be checked against the property it claims, and
neither the rule nor the author notices on their own.

**43. The label was not the suffix.** The claim that compares the leaders across corpora keyed its results
by file suffix ("-c") and looked corpora up by name ("C"), so corpus C was read as absent and reported as
disagreeing with a leader it matched exactly. It is the fourth occurrence of one mistake in this
repository - the zero-of-zero table, the four-part dict keyed by three, the calibration file under another
name, and now a suffix used as a name - and it is why `band.cell()` exists. The corrected claim says one
of the three authored corpora agrees with real text, not none.

The second band was repairable and I repaired it. Four of the twelve unanswerable questions were more
than half covered by a stored record, which the validator called an unlabelled answer and was right
about - so the rule now rejects any candidate whose words are half present in the store, and the band
enforces its own definition. The hard band cannot be repaired the same way, because its definition is a
paraphrase and no sampling rule produces one.

### What this does not settle

It is real text and it is not real memory. Package descriptions are short, written to sell a library, and
share vocabulary because the vocabulary belongs to a domain rather than to a person. A question a colleague
asks a memory store is longer, more ambiguous, and often answerable only from several records at once. What
the corpus does buy is the property every other corpus here lacks: not one sentence in it was written by
anyone who knew what the answer would be.

### What this costs

One generator, one measurement run of eleven subjects, one report and a claim that fails. The subjects,
the probes, the tie analysis and the mutation battery are untouched. What moved is the answer to a
question this repository has been asking since its second corpus, and it moved against the answer it had
been giving.

## Addendum 31: four corpora were one axis, and the axis can be walked

Addendum 30 ended with a contradiction: three corpora said the small servers find nothing, and a fourth
said they find a third of everything. The explanation offered was that the authored corpora paraphrase and
the real one does not. That was a sentence, not a measurement, and it implied something nobody had
checked - that the difference between them is a single quantity that could be varied on purpose.

It can. `distance_sweep.py` takes 24 real records, derives five question forms from each by rule, and asks
all of them of every subject: the same records, the same facts, only the fraction of the record that
survives into the question changed.

| band | kept | of the record's long words, measured | pairs separated |
|---|---|---|---|
| d0 | every word | 1.00 | **26 of 55** |
| d1 | two of three | 0.71 | 35 of 55 |
| d2 | every second | 0.56 | **38 of 55** |
| d3 | one in three | 0.33 | 34 of 55 |
| d4 | two words, in a question | 0.29 | 34 of 55 |

### The subjects have shapes, not scores

| subject | d0 | d2 | d4 |
|---|---|---|---|
| `zenbrain` | 24 | 24 | **21** |
| `memory-mcp-1file` | 24 | 22 | 18 |
| `control` | 24 | 24 | 13 |
| `memory-lean` | 24 | 24 | **0** |
| `mcp-duckdb-memory-server` | 24 | **13** | 10 |
| `server-memory`, `mcp-knowledge-graph` | 24 | **0** | 0 |
| `memento` | 11 | 14 | 13 |
| `memdb`, `statecore-mcp` | 0 | 0 | 0 |

Three subjects go from perfect to zero when a third of the words are removed. Their total failure on the
authored corpora and their strong showing on real text are the same property measured at two distances,
and neither number is wrong. `memento` is flat and poor at every distance, so nothing about it was ever a
paraphrase question. `duckdb` is **non-monotone** - 24, 24, 13, 3, 10 - and the rise at the far end says
its behaviour is a function of query length rather than of meaning; a two-word query is a keyword query.

That last one is worth keeping. A benchmark that reported a single number for `duckdb` would have been
describing one point on a curve that turns twice.

### Where each corpus sat

Two coordinates place a question, not one. How much of the answering record survives into the question is
the distance this sweep walks. How much of the question is drawn from the record is a second, and the
sweep cannot move it - every band in it is made of the record's own words, so the second coordinate is
1.00 by construction.

| corpus | of the record, in the question | of the question, in the record |
|---|---|---|
| A | 0.29 | 0.50 |
| B | 0.33 | 0.57 |
| C | 0.22 | 0.60 |
| real | 0.71 | 1.00 |

Every authored corpus sits low on both and the real one sits high on both. The disagreement of the last
phase is entirely accounted for by a position, and the sweep is the easy half of the space: nobody asks a
question made only of the answer's words.

### An easier question is an instrument with no room at the top

The verbatim band separates 26 of the 55 pairs and the half-paraphrased band separates 38. Eight subjects
tie at 24 of 24 when the question quotes the record, and a tie separates nobody - which is precisely what
happened to the real corpus, where four subjects tied at 48 hits and first place came down to one point.

So "too easy" is not a complaint about difficulty. It is a statement about the top of the table: an
instrument whose easy band is the main band has nothing to say about who is best, and it will say it with
a small margin and a large p value.

### One more of my own mistakes

**44. The share was measured from the wrong end.** The first build reported that every band kept "1.00 of
the question's long words", which is true by construction - a question made by deleting words from a
record uses only that record's words. The number described the wrong quantity and was correct, which is
the kind of error that survives review; measuring the other way round, the ladder came out at 1.00, 0.71,
0.56, 0.33, 0.29 and the axis existed.

### What this does not settle

Removing words is not paraphrasing. A question that says the same thing in different words shares few of
the record's words *and* introduces words the record does not contain, and this ladder only moves the
first. So the curves are a lower bound on the difficulty of the authored corpora and an upper bound on
what a keyword matcher can do: `server-memory` scoring zero at every distance from d1 out is a fact about
substring matching, not a claim that it cannot help somebody who asks carefully.

What the sweep does buy is a number per subject instead of a contradiction between corpora. Each of the
four question sets is a position, and the disagreement between them is the slope between those positions.

### What this costs

One generator, one measurement run over eleven subjects at two repeats, one report, two claims that fail.
No subject was changed, no corpus was rewritten, and the five question sets now have a coordinate system
instead of an argument.

## Addendum 32: two letters on one word in four

Addendum 31 closed half a space and said so. The distance ladder moves how much of a record survives into
a question, and it cannot move the other coordinate: every band it builds uses only the record's own words.
A person does not ask that way. They ask about "parsers" when the record says "a parser", and the word they
typed is not in the record.

That is measurable without a thesaurus, a writer or a network. `morph_sweep.py` asks every real
description four times with a growing share of its long words pluralised - one rule for words ending in s,
x, z, ch or sh, one for a consonant before y, and `+s` otherwise - so the question brings vocabulary the
record does not contain.

| band | vocabulary the record lacks, measured |
|---|---|
| m0 | 0.00 |
| m1 | 0.17 |
| m2 | 0.40 |
| m3 | 0.83 |

### What two letters do

| subject | m0 | m1 | m2 | m3 |
|---|---|---|---|---|
| `mcp-duckdb-memory-server` | 24 | 24 | 24 | 24 |
| `memory-mcp-1file` | 23 | 23 | 23 | 23 |
| `zenbrain` | 24 | 24 | 24 | 18 |
| `memento` | 16 | 16 | 18 | 18 |
| `control` | 24 | 24 | 24 | 9 |
| `server-memory` 1.0.0 and 2.0.0 | 24 | **0** | 0 | 0 |
| `mcp-knowledge-graph` | 24 | **0** | 0 | 0 |
| `memory-lean` | 24 | **1** | 0 | 0 |

Four subjects go from perfect to nothing at the first step, where one word in four has two letters added.
They match substrings; nothing else in their retrieval normalises anything. The positive control, which is
also a substring matcher, holds two more bands because its threshold needs half the question's terms to
match and the plural still matches in a substring sense for common words - and then falls to nine.

**The family split is the same one the distance sweep found, arrived at from the other direction.** The
subjects that fail a paraphrase at d1 are the subjects that fail a plural at m1, and they are the ones
whose retrieval is a string comparison. Two independent sweeps naming the same five subjects is the
strongest evidence in this repository that the distinction is a property of the systems rather than of a
question set.

### The two coordinates, now both measured

| sweep | of the record, in the question | of the question, in the record |
|---|---|---|
| distance, d0 to d4 | 1.00 down to 0.29 | 1.00 at every band |
| morphology, m0 to m3 | 1.00 at every band | 1.00 down to 0.17 |

Neither sweep alone is what a person writes. Losing the record's words is a recall problem; using only the
record's own words is a normalisation problem; a real question does both, and a benchmark that pins one
coordinate measures one failure mode and reports it as quality.

### What this is not

Pluralisation is the cheapest case of new vocabulary: the stem is intact and two letters changed. A subject
that fails here fails the easiest version of the problem, which makes this a floor and not a measure of
understanding - the same role the real corpus's hard band plays. The honest claim is narrow: the second
coordinate can be moved at all without an author, and moving it separates the field.

### And the ledger

`plural-is-free` - the sentence a vendor would write, that answering a record's own words implies answering
the plural of them - **FAILS** for five of eleven subjects.

### What this costs

One generator, one measurement run at two repeats over eleven subjects, one report, one claim. No subject
changed, no existing corpus touched, and the question space this repository can build is now two
dimensional instead of one.

## Addendum 33: a question with three answers is not three questions

Every question this repository has asked has had one answer. The scoring asks whether the right id is in
the first three returned, so every question has been a lookup - and a memory store is asked joins as
often as lookups. "Which services use postgres" has three answers, and a benchmark of single answers
would call a subject correct for returning one of them.

The corpus is built from real descriptions and no author: records whose descriptions share four or more
long words become a **cluster**, and each cluster is one question whose required answer is the whole
cluster. The store is 72 records with 16 cluster questions beside 16 single-record ones, so the two
kinds are compared in one run. No new measurement machinery was needed - every row has carried its full
`returned` list since the first matrix.

### The result

| subject | clusters fully answered | required-set recall | single questions, hit`3 |
|---|---|---|---|
| `control` | **16 of 16** | 1.00 | 16 of 16 |
| `zenbrain` | **16 of 16** | 1.00 | 16 of 16 |
| `memory-mcp-1file` | 11 of 16 | 0.76 | 16 of 16 |
| `memento` | 9 of 16 | 0.65 | 10 of 16 |
| `memdb` | 3 of 16 | 0.25 | 0 of 16 |
| `mcp-duckdb-memory-server` | 0 of 16 | 0.06 | 16 of 16 |
| `memory-lean` | 0 of 16 | 0.03 | 16 of 16 |
| `server-memory` and `mcp-knowledge-graph` | 0 of 16 | 0.00 | 16 of 16 |
| `statecore-mcp` | 0 of 16 | 0.00 | 0 of 16 |

**Two subjects answer every cluster in full and six answer none of them, and five of those six answer
every single-record question on the same store.** The difference is therefore not retrieval quality. It
is whether returning a set is a capability the subject has at all: a search that answers with one id and
stops cannot answer a question whose answer is three, and no amount of accuracy on single questions
implies it.

That is the cleanest split in this repository and it took a new kind of question to see it. Every metric
published so far - score, hits, hit`1, what an agent reads - is single-answer, and all of them described
those five subjects as competent retrievers.

### What the single-answer metric does to a set answer

Where a subject returns part of a set, `hit3` on the arbitrary first member counts the cluster as
answered. `memento` is scored 12 of 16 that way and answers 9 in full. The overcount is small here and
it is the right shape of error: the metric asks whether one id came back, and the question asked whether
the set did.

### A finding that arrived before the measurement

The store had to be capped at 300 characters per record because `memory-lean` refuses anything longer -
"observations over 300 chars or not strings" - and the run never starts. That is a documented limit of
the subject rather than a defect, and it is the first time one of them has constrained the corpus instead
of merely failing it. It is also a fact about deployability: a memory that cannot hold a paragraph
cannot be the memory of an agent that reads documents.

### One more of my own mistakes

**45. The report asserted a number the table contradicted.** The first draft of the paragraph after the
table said "16 of 16 cluster questions were counted as hits by the single-record metric", which was the
maximum of a column rather than the gap it was describing, and the table beside it said those subjects
scored 0 of 16. The replacement sentence then said "two against nine" when the data said two against
six. Both were written from memory of what the run had said rather than from the run; the third version
computes every clause from the scores dict, and it is the only one of the three that matches the table
it sits under.

### What this does not settle

It does not test a join. Reading one record to discover the names of others - what a real multi-hop
question needs - is a different capability, and no subject here claims it. It also turns on k: the
search is asked for three results, so a three-member cluster is answerable only by a subject that ranks
all three. Raising k would make every subject that finds one member pass, which measures nothing.

### What this costs

One generator, one measurement run of eleven subjects, one report and a claim that fails. The question
space now has a third dimension - how many records the answer has - and the field splits on it two
against nine, which is a wider spread than any other axis here.

## Addendum 34: the price was right, and one tie was worth keeping

The power analysis has been the most quoted and least tested number in this repository. `band.py` puts a
price on a near-tie - 371 questions for the leader against the control, 679 against zenbrain, 11,825 on
corpus B - and all three prices were published without ever being paid.

This pays one of them at a fifth of the size: the same 72 real records, three hundred questions instead of
sixty, each record asked verbatim and at two graduated reductions. A larger store was tried first - 282
records - and abandoned inside ten minutes, because the control reads the whole store on every search and
needed about nine minutes for the first subject alone. Holding the store fixed means the only thing that
changes between the two exams is how many questions are asked.

### The three predictions, written before the run

1. The leader is the control. **Held.** 292 of 300, ahead of memory-lean at 288.
2. Control against memory-lean does not separate. **Held.** 1-0 in sixty, and 11-7 in three hundred,
   exact p = 0.48.
3. The separated-pair count rises and stays below all 55. **Held.** 41 of 55 becomes 49 of 55.

Three out of three, which is worth less than it sounds: the first restates the previous phase and the third
is nearly arithmetic. The second is the one with content, and it is the only one that could have refuted
the price calculation.

### What a longer exam actually buys

| exam | questions | pairs separated |
|---|---|---|
| small | 60 | 41 of 55 |
| large | 300 | 49 of 55 |

Eight pairs that were ties became separations, five of them at p = 0.000: control against duckdb, control
against the leader, duckdb against memory-lean, memory-lean against the leader, duckdb against the leader.
Those pairs had a real difference and the sixty-question exam could not see it - which is what a price of a
few hundred questions means.

And one pair did not move. Control against memory-lean went from one question in sixty to four in three
hundred, and four discordant questions cannot be called. The tie that four phases have described as
unreachable is unreachable for a reason that is now measured rather than assumed.

### The honest cost of the design

**Three questions about one record are not three independent draws.** The exam is five times longer but
carries less than five times the information, and the direction of that bias is the one that matters:
correlation makes separation harder. So the eight separations are real evidence and the surviving tie is
weaker evidence than three hundred questions suggests. A larger store with independent questions was the
design that would have avoided this, and it was unaffordable - which is itself a fact about whole-store
readers: the control, memory-lean and the leader all read the entire store to answer one question, so a
benchmark that grows its store to grow its exam grows the cost per question with it.

### Two more of my own mistakes

**46. The command was quoted and every subject silently failed.** `exam_size.py` built `--cmd="node ..."`
instead of the bare command matrix.py passes, so retrieval.py tried to exec a single token containing
spaces. Every subject reported "no result", the tool printed eleven lines of it, and the first I noticed was
that no result file had been written.

**47. The verdict was looked for in a tuple and never found.** The prediction test searched for the string
"memory-lean" among the elements of the pair key, which are "memory-lean 1.5.0", so it found nothing and
printed an empty section under a heading that promised a verdict. Regenerated with the substring test
applied to each element, and the verdict appeared: the prediction held.

### What this does not settle

It settles one price out of four. The 1,401 and 11,825 question pairs are still unpayable, and a corpus
where the exam can grow without the store growing - many questions per record, independent in the sense
that matters - is the design this phase did not have budget for.

### What this costs

One generator, one measurement run of eleven subjects at 300 questions, one report, one claim that fails.
The store, the subjects and every earlier table are untouched, and the repository can now say what a longer
exam buys with a measurement instead of an estimate.

## Addendum 35: no memory here knows which version of a fact is current

Thirty-four addenda have measured what a memory can find. Not one has asked the question a memory store
exists for.

A fact is written, then rewritten. The caller needs the value that replaced the old one, and the whole
value of a memory holding thousands of facts over months depends on it. `restart` covers a record that is
deleted and `forget` covers one asked to go. **Supersession - the same fact, revised - has never been in any
corpus here.**

The corpus is built from real data and no author: every chosen package record is stored twice, as two
records whose only difference is the version string in the body, and each question asks with the
description both of them carry. The current answer is the later record. Neither the id nor the text says
"latest"; the only signal is which write came second.

### The result

| subject | current, alone | stale, alone | both returned | current first |
|---|---|---|---|---|
| `zenbrain` | 5 | 0 | 67 | 55 of 72 |
| `memory-mcp-1file` | 2 | 2 | 68 | 29 of 72 |
| `control`, `duckdb`, `memory-lean`, `mcp-knowledge-graph`, `server-memory` x2 | 0 | 6 | 66 | **0 of 72** |
| `memento` | 0 | 17 | 18 | **0 of 72** |
| `memdb`, `statecore-mcp` | 0 | 0 | 0 | **0 of 72** |

**Nine of eleven subjects never once put the current record first.** They return both versions in 66 of
72 questions and rank the superseded one ahead of its replacement. Across the table 55 answers came from
the stale record alone and 549 returned both.

The mechanism is not mysterious and it is not a bug in any subject: two nearly identical records tie on
every keyword, the tie is broken by insertion order or by id, and the old record was written first. What is
missing is any notion that a later write supersedes an earlier one - a missing capability, not a ranking
defect.

### The three predictions

1. No subject above three quarters on current-alone. **Held** - the best is 5 of 72.
2. Subjects returning several results return both about as often as either. **Held** - 549 of 792 returned
   both.
3. At least one subject below a quarter. **Held** - two scored nothing at all.

All three held, and this is the first phase in the repository where every prediction was that the field
would fail.

### What this does not settle

The two versions differ in the body and not in the record name, so this measures ranking between two
candidates rather than storage semantics. A subject that overwrites on a repeated write would answer it
trivially if both writes used one name; keeping the names distinct is deliberate, because the question is
whether recency is visible at all. It also does not test an update protocol: asking a memory to *revise* a
fact, and telling a revision from a second unrelated fact, is a capability none of these subjects claims
and the probe suite has never asked for.

### What this costs

One generator, one measurement run of eleven subjects, one report, one claim that fails nine times. The
question space now has a fourth dimension - whether a fact can change - and on it the field scores close to
zero.

## Addendum 36: the cost table runs to five thousand, and the read path is the expensive half

Addendum 25 measured the cost axis to three thousand records and said so. Half the subjects had one run.
This pays for the rest: **5,000 records for nine subjects, 2,000 for two, with two or three runs each**,
and a report-only mode in growth.py so rebuilding the table no longer costs the deepest sweep in the
repository.

### The write axis was the gentler one

The worst grower is `statecore-mcp` at **x3.3** - 4.4 ms at depth 5, 35.9 ms at 5,000. `mcp-knowledge-graph`
x2.2, `memory-lean` x1.9, `server-memory` x1.8 and x1.6, and `memdb` and `zenbrain` get **cheaper** (x0.7)
because their cost is dominated by a constant the store does not touch.

### The read path is where depth bites

| subject | search at depth 5 | at 5,000 | factor |
|---|---|---|---|
| `mcp-duckdb-memory-server` | 8.3 ms | **2,187 ms** | **264** |
| `control` | 0.4 ms | 44.1 ms | 119 |
| `memdb` | 1.8 ms | 70.6 ms | 38 |
| `statecore-mcp` | 2.1 ms | 27.7 ms | 13 |
| `zenbrain` | 1.5 ms | 9.9 ms | 7 |
| `mcp-knowledge-graph` | 3.7 ms | 14.1 ms | 4 |

Five of eleven subjects grow their search by more than ten times across the range, and there is no subject
whose search cost is a constant in the size of what it is searching. Every retrieval number this repository
publishes is a search cost taken over seventy-two records.

### The prediction that was wrong, about my own subject

Addendum 25 predicted the control would be flat: it appends one line under a lock. It is in the growing list
at x1.5, and the mechanism is mine - after each append it counts the records to return a sequence number,
and counting reads the whole store. At 500 records that read sits below the noise floor, which is why the
line looked flat for two phases; at 5,000 it is a fifth of the write cost.

That is the same defect the whole addendum exists to find, committed by the control the repository uses to
prove its probes work. It is written into the generated report rather than a footnote, because a control
with an unmeasured cost curve certifies something it has not checked.

### Two subjects stop at two thousand, and both say why

`memento`'s search costs **8.5 seconds** at two thousand records - the curve climbs from 105 ms at depth 5
through 4.4 s at a thousand to 8.5 s at two thousand. `memory-mcp-1file` reads its whole store on every
write, so a second run at the existing depth was bought instead of a deeper first one. A cost curve that
stops, with the reason, is worth more than one that is extrapolated.

### What repeated runs bought

Every subject now has two or three runs and the agreement column is no longer empty for most of them. Where
the runs disagree the table says so: `memory-mcp-1file`'s search ratio is x0.9 across its own two runs,
which is noise and labelled as such.

### What this does not settle

5,000 records is not ten thousand, and the quadratic end of these curves has not been reached. What the
range does establish is the shape: every subject that is not flat at 500 is measurably worse at 5,000, and
the factor is computable from the table.

### What this costs

About fifteen minutes of sweeping for nine deep runs and two repeat runs, one flag added to growth.py, and
one prediction retracted in the generated prose.


## Addendum 37: what comes back besides the answer

Every metric in this repository asked whether the right record arrived. None asked what arrived with it. A
top-three list carrying the answer and two unrelated records scores exactly what a list carrying the answer
alone scores, so a subject that answers more questions by handing back more records is paid for the hit and
never charged for the volume. `retrieval_mutants.py` named that hole two phases ago and could not fill it.

This fills it from the rows already on disk: nine corpora, eleven subjects, eight panel adapters, both
phrasings, **no subject run again**. Three readings, and the first needs no classifier at all.

### The silence bill

On a question whose answer is nothing, every record handed back is junk by construction. 147 such questions
across five corpora. **Eight of the eleven subjects hand records back on at least one of them**, four of them
on nearly all: `memento` and `zenbrain` answer every one, `memdb` 145, `1file` 141, and
`memento` alone hands back **47,985 characters on questions that have no answer.**

The first prediction held and the second did not, and the second is the finding. `items.py` reported that
every subject either declines all twelve unanswerable questions or none of them - which made the twelve
points a habit, and the ledger says so. At ten times the sample the habit becomes a **threshold**: the seven
subjects that decide per question answer 15 of 336 unanswerable questions on the four short bands and **36 of
99 on the long exam**.

The mechanism is in the corpus, not in the subjects. Every one of those 36 answers landed on a question that
shares a word with a stored record, and no subject that decides per question ever answered a question whose
words appear nowhere in the store - one exception, `statecore-mcp`, which hands back a record for all sixty
questions on corpus A and so has no threshold there to fail. **The twelve points are the price of a clean
band.** A subject does not collect them for judgement; it collects them because the band had no neighbours,
and a band built from a real pool of packages always does.

### Junk around the answer

Near miss or noise, mechanically: same name token of four characters or more, or three or more shared words
that are not common to half the corpus. Words in half the corpus are dropped because they cannot distinguish
anything - `Version` and `Licensed` sit in every package description here.

| subject | correct | records back | noise | noise per correct |
|---|---|---|---|---|
| `memdb` | 14 | 2,128 | **2,075** | 148.21 |
| `memento` | 326 | 2,133 | **1,169** | 3.59 |
| `zenbrain` | 666 | 2,125 | **765** | 1.15 |
| `memory-mcp-1file` | 664 | 2,069 | **674** | 1.02 |
| `control` | 625 | 1,208 | **75** | 0.12 |
| `server-memory` | 232 | 331 | **0** | 0.00 |

`memento` answers 326 questions correctly and hands back 1,169 records nobody asked for; the control
answers 625 and hands back 75. No published table separates the two, and they are not the same thing.

### The panel, where the axis moves a verdict

| adapter | score, written | noise per correct | answer share |
|---|---|---|---|
| `greedy-match` (answers anything) | **43 of 60** | **1.86** | 28% |
| `control` | 37 of 60 | 0.32 | 63% |
| `one-result` (one record only) | 37 of 60 | 0.04 | 93% |
| `strict-match` (exact words only) | 27 of 60 | **0.00** | 100% |
| `blind-search` (one shared word) | 2 of 60 | **69.00** | 1% |

The tidiest adapter here is the second worst, and the one that answers anything beats the positive control by
six points while carrying eighteen times the noise. `blind-search` is where the reading earns its keep: it
answered all 48 answerable questions, handed back 144 records, got 2 right, and **138 of the rest share
neither a name nor three words with what was asked for.** That is the number the mutation battery could not
produce.

### The exam had never been validated

Pointing `validate_corpus.py` at `large_corpus.json` for the first time needed an `--exam` mode,
because three of its rules - every known band populated, only the four known labels, one record answers one
question - are consequences of what an exam is. Under that mode the exam is charged with two things:

**12 duplicated questions: 300 slots for 288 distinct questions.** Two packages can share a description word
for word, so the same words are asked twice with a different expected record and a subject that returns the
other one is graded wrong for being right. The published 300-question totals understate two subjects.

**8 unanswerable questions half covered by one record.** Reading them changes the charge: `obliterator` is
not a path library. What the rule detects is that a word-overlap matcher will answer the question - and the
positive control answered exactly those eight. **A checker and a subject that share one idea cannot check each
other.** The charges are pinned in `corpus-known.json` with that reading beside them; that the exam is 300
slots for 288 questions is now written down instead of assumed.

### Five more self-bugs, numbered 48 to 52

**48. The tool grew its own tokenizer.** The first `precision.py` measured question coverage with a second
tokenizer and reported 12 of 12 corpus-A questions as sharing a word with a record, where the validator's own
tokenizer says 4. Two tokenizers in one repository is how a corpus gets certified by one and measured by the
other; `words.py` exists to prevent it, and the tool now imports it.

**49. A question asked twice was counted as two draws.** The exam's 12 duplicated slots were counted twice in
every per-question ratio. A question asked twice is one question; the reader now keeps a set of what it has
seen, and the exam's absent band dropped from 100 to 99.

**50. One subject's report answered questions the corpus no longer asks.** `memory-mcp-1file`'s real-corpus
report carried 12 absent rows measured against a version of the corpus that was rebuilt afterwards, so the
report said 0 of 0 unanswerable questions - a band that does not exist. Re-measured (47 of 60), and the tool
now counts orphan rows out loud instead of dropping them.

**51. A prediction named the wrong adapter.** Prediction 4 was framed on "the matcher that scores 43 against
the control's 37" and named `blind-search`. That number belongs to `greedy-match`; `blind-search`
scores 2. The prediction is left as it was written and the report says which adapter is which, because a
prediction that can be edited after the run is not a prediction.

**52. A prediction assumed a record size.** Prediction 6 said the largest reading bill would exceed 25,000
characters on corpus A. It does not: corpus A's records are one sentence each, so the top bill is 10,474
(`memdb`). The prediction was about record length while pretending to be about behaviour.

### What this does not settle

The near rule is a rule. It is checked in one direction only - the supersession band contains near pairs by
construction, and the rule finds all 578 that came back - and nothing checks the other direction: a record
called near may still be useless. So the noise column is a count of records that share neither a name nor
three distinguishing words with the answer, and not a count of wasted attention. The silence bill is the part
that needs no rule.

Deciding whether a returned record **helps** a caller is not a counting question, and it is the one place in
this repository where a model reading the record would beat any rule. It is left unmeasured rather than faked
with a longer rule.

### What this costs

Two hours, no subject runs, one new tool, one validator mode, two pinned defects, and three claims - all three
of which fail.


## Addendum 38: a question two records answer equally

The precision phase found that the exam's three hundred slots were 288 distinct questions. This found the
same defect in three more corpora and fixed it everywhere: a question text that two records answer equally
is not a question, and none of its copies belongs in a corpus.

The cause is not carelessness, it is real data. Two packages can carry the same description word for word -
a fork and its original, a client and a server generated from one template - so a corpus that derives one
question per description asks the same words twice with a different expected record and grades whichever
answer the author did not pick as wrong. The counts, before this phase:

| corpus | questions | distinct | slots two records answer equally |
|---|---|---|---|
| the exam | 300 | 288 | **24** |
| the morphology sweep | 96 | 88 | **16** |
| the distance ladder | 120 | 115 | **8** |
| the supersession corpus | 72 | 69 | **6** |
| multi-record, and the four hand-written corpora | 60 each | all distinct | 0 |

Four of this repository's reports were scoring subjects on questions with two right answers, and the four
hand-written corpora were clean only because a person chose every question.

### The fix is a drop, not a merge

`questions.py` now holds the rule once, and each builder calls it before writing: if a question text
appears more than once, **every copy goes**. Merging the two expectations instead - crediting either record
- would keep the slot, but the slot could then no longer separate a subject that found the fact from one
that found its sibling, and a question that cannot separate anything is not worth the measurements it costs.

The four corpora were rebuilt. Every retained question is **byte-identical** to the one already asked
(verified against the committed files) and every record is unchanged, so no subject was re-measured: rows
about retained questions stand, and the 594 rows about dropped questions - 54 slots across eleven subjects -
are excluded from every count rather than rescued. Each corpus file now records what it dropped, so the
report can say which questions went and why.

### What changed in the published numbers

The exam went from 300 questions to 276 and from 49 of 55 pairs separated to **43 of 55**; the two flips
that survive are `control` against `duckdb` and `duckdb` against `memory-lean`, both at p = 0.000. The
near-tie the power analysis was betting on - `control` against `memory-lean` - is unaffected: 11-7, p = 0.48.
**Six of the eight separations the first version reported were the exam grading a coin toss**, which is also
why the exam's totals had been understating two subjects.

The other three reports moved by arithmetic rather than by finding: the morphology sweep is 20 questions per
band instead of 24 and the same subjects fall at the same place; the distance ladder is 24 per band except
d4, which is 16; supersession is 66 questions instead of 72 and `zenbrain` puts the current version first on
52 of them. No conclusion in any of the four changed.

### The claim that said the opposite of its own code

Fixing the exam exposed a defect in the ledger. `longer-exam` read "asking three hundred questions instead of
sixty changes which pairs the corpus can separate" and returned true only when **nothing** changed, so for
two phases it printed FAILS beside a measurement that satisfied the sentence it was printed under. Sentence
and code now agree on the reading the reports publish: more questions separate the pairs the short exam
could not, and unsay no separation the short one found. It holds, and the ledger is 9 of 36.

### Two more self-bugs, numbered 53 and 54

**53. A guard that could be fooled by its own backups.** The first run of `questions.py` scanned
`*corpus*.json` and counted the four copies I had saved to compare against - which are corpora by the
glob and not by intent. The copies were deleted; the guard now says how many files it looked at, so the
number can be argued with.

**54. A report printed a sentence twice and a number once.** Splitting a hard-wrapped line in
`distance_sweep.py` to change "out of 24" left "half of what it / it answered verbatim" in the generated
report, and nothing in the pipeline reads its own prose. Regenerated and read by eye before committing - which
is the only check there is for that class.

### What this does not settle

The rule treats one kind of ambiguity. Two records can also be equally good answers with *different*
descriptions - a generic question about "a memory server" and two packages that both describe one - and
nothing here detects that, because detecting it needs a judgement about meaning rather than a comparison of
strings. What is fixed is the case a rule can see: the same words, twice, with two answers.

Nor does any corpus now prove it has no ambiguous question. `questions.py` proves that no question text
repeats; it cannot prove that no two *different* question texts name the same fact, and no cheap rule can.

### What this costs

Two hours, one new module, four builders touched, four reports regenerated, one claim corrected, and no
subject run. The check that would have caught it five phases ago is forty lines long and runs in CI now.

### What this proves about the instrument

The corpus is part of the instrument, and this is the second time in two phases that a defect in it was
found by reading the rows rather than by running anything. A checker whose question set can grade a right
answer wrong is measuring the author, and the guard that prevents it costs less than the measurements it
protects.


## Addendum 39: the front door, and the page that was a wall

Two product phases in one, and both were mostly about finding out what was not true.

### Quickstart

The instrument had no install step to package - nothing outside the Python standard library - so
"packaging" was a non-question. What it did not have was a page a new reader could act on, and the README's
own first code block was a hand-trimmed run from before the eleven-subject table existed.

`QUICKSTART.md` is three commands, and every command in it was run to write it. The interesting one is
the first: @@--adapter=auto` against a server nobody wrote an adapter for. It discovers the binding from
the tools the server publishes, builds the argument mapping from their own JSON schemas, and **proves it by
round-tripping a unique token before a probe runs**. Against the reference server it returns 6 PASS, 4
UNKNOWN and 0 fails - and the UNKNOWNs are the honest ones: two probes need to read bytes on disk and that
subject's store is not declared, two need a record body the tools do not return.

**Nothing in this repository had ever exercised that path.** The CI probed three servers through
hand-bound adapters. A front door nobody walks through is a door propped open with nothing behind it, so the
probe job now runs @@--adapter=auto` against the reference server and fails if it reaches a FAIL or if the
binding it proved stops holding @@ack_readback`, @@restart` or @@findable`.

Two smaller things the pass fixed: the ten-probe table had no header (it is the output most people ever see
once, so it now names its own columns), and three counts in the quickstart were wrong when written - one
server rather than three, seventeen optional subjects rather than twenty, three pinned subjects rather than
four. Every one of them was checkable against @@package.json` and the CI file, and two of them I got right
only after checking.

### The README split

1,529 lines, twelve hundred of them a history of phases in the order they happened rather than in the order
a reader needs. It is now **534 lines** with five pages under @@docs/@@:

| page | lines | what moved |
|---|---|---|
| @@docs/probes.md@@ | 156 | the ten probes, the two controls, the three errors the harness caught in itself, the per-subject probe result |
| @@docs/corpora.md@@ | 291 | the eight question sets, from the twelve-question original to the exam |
| @@docs/cost.md@@ | 96 | the cost axis and the growth sweep |
| @@docs/precision.md@@ | 91 | what comes back besides the answer |
| @@docs/subjects.md@@ | 114 | every subject, with the live matrix block |

The pages are the sections moved **verbatim** - one diff, no rewriting - and a checker compared every
non-empty line of the old README against the new files: **zero lines lost**, eleven lines relinked (the
@@../@@ a link needs once it lives one directory down). The front page keeps the argument: the claim, the
opening run, what holds, the retrieval spine from a score to a tie, how to run it, and the limits.

### Three more self-bugs, numbered 55 to 57

**55. A tool that truncates a file, and a write that would have followed it.** The read tool returns at most
about fifty thousand characters and says nothing about it, and I read @@harness.py` (84 KB) through it with
the intention of editing and writing back. The anchor I needed sat past the cut, so the edit threw instead of
applying - which is the only reason @@harness.py` was not replaced by its own first two thirds. The rule
that comes out of it: a file big enough to be truncated must be edited through a script that reads it whole.
Every later edit in this phase did.

**56. A sync tool that only looked in one file.** @@sync_readme.py` regenerates the live matrix block inside
the README. After the split that block lives in @@docs/subjects.md`, and the tool went looking for the first
@@python matrix.py` it could find - which was now an inline mention in prose - and reported "the matrix
block is not fenced". A number synced by a tool is only synced where the tool looks. It now finds the block by
what the block says, in any page, prints which page it filled, and the CI runs it.

**57. Positional prose after a move.** The README said "see the retrieval table above", "numbers above are",
both of which pointed at text that had just left the page. Two sentences, both fixed to name the page
instead of the position.

### What this does not settle

The split changes where the argument sits, not what it claims. No number moved: the matrix block was
regenerated by its own tool, the claim count is rewritten by the ledger, and every generated report is where
it was. What moved is prose, and prose has no checker - the conservation test proves no line was lost, not
that the remaining page reads well. That is a judgement and it is the author's, which is why the pages are
verbatim rather than rewritten.

### What this costs

An afternoon, one new page, one split, one tool made location-independent, and three documented self-bugs -
two of which would have been silent if the tooling had been slightly more forgiving.


## Addendum 40: the instrument changed its mind about what it was measuring

The precision phase ended with a sentence it could not act on: the validator charged eight of the exam's
unanswerable questions as "an unlabelled answer", and reading them showed the charge was wrong every time.
`obliterator` is not a path library. This pays that debt by splitting one measurement into two.

### Two things a word overlap can and cannot tell you

| what is shared | what it means | what the validator does |
|---|---|---|
| most of **each other's** words, with one record | the question **is** that record in disguise, so its answer is in the store and nobody labelled it | error |
| half the question's words, but the question is not what the record says | a word-overlap matcher will fire | warning, with the fraction, never charged |

The first test is symmetric on purpose: two documents that share most of each other's vocabulary are the
same document, and that is a fact about text. The second is one-directional and is a fact about a matcher,
which is why the warning says "a word-overlap matcher will answer it" and stops there. Nothing that compares
strings can decide whether it should be answered, and a validator that says it can is measuring itself.

**The eight exam questions moved from the error list to the warning list, and the exam's pin in
`corpus-known.json` is now empty and gone.** The exam passes its own validator for the first time: no
errors, eight neighbours printed.

### The rule had never been seen firing, which is the same problem

Nine corpora, zero copies found. A rule that has never fired is a decoration, and this repository has spent
six phases insisting that anything unfalsifiable is not an instrument. So CI now **plants a record's own text
as an unanswerable question** in a copy of corpus B and requires exactly one charge - `'line-estuary-speed'
in disguise: they share 90, coble, estuary...` - then throws the corpus away. A checker that cannot fail is
not a checker; a checker that has not been shown to fail is one nobody has tried.

### One self-bug, numbered 58

**58. A sentinel that was also a threshold.** The rewritten rule seeded its best-match tuple with a score of
0.5, which was also the line between "neighbour" and "nothing", so every question whose best overlap was
below half stayed at the sentinel and was reported as sharing nothing with `None`: 93 warnings naming no
record at all. Running it once showed it. The seed is 0.0 and the thresholds are named constants, which is
what they should have been from the start.

### What this does not settle

The copy test has one weakness the neighbour test does not: it needs a *record* to exist. A question copied
from an external document that nobody ingested is unanswerable and shares nothing, which is correct, and a
question paraphrased from a record shares little in both directions, so a copy that has been reworded enough
is invisible to it. The rule catches the case it names and no more.

### What this costs

An afternoon, one validator rule split in two, one pin retired, one CI self-test, and the only instrument in
the repository that has been changed by a measurement rather than by an argument.


## Addendum 41: the second opinion, and what it said about the first

Every number in the precision reading came from a rule about words: same name token, or three shared
distinguishing words, else noise. The report said so and named the limit in a sentence - deciding whether
a returned record HELPS a caller is not a counting question, and it is the one place a model reading the
record would beat any rule. That sentence was the end of the conversation. This makes it a measurement.

`judge.py` takes pairs the rule has already labelled, shows a model the question and the record and
**nothing else** - no label, no corpus, no hint of which kind the rule thinks it is - and asks whether the
record would help the person who asked. Sixty pairs, four corpora, three classes, one model at temperature
zero. Every judgment is cached and committed, so the report re-derives itself with no model and no network,
which is what the CI runs.

### What the reader said

| the rule says | pairs | the reader says relevant |
|---|---|---|
| answer | 20 | **20** |
| near miss | 14 | **5** |
| noise | 20 | **0** |

**Calibration: the reader called all twenty expected records relevant**, so it is not a contrarian and the
numbers beside it mean something. Agreement with the rule's reading - answer or near counts as relevant,
noise does not - is **45 of 54 pairs, Cohen's kappa 0.67**, which is the substantial band by the usual
reading and which the ledger now records as a claim that **holds** (10 of 37).

### The disagreements all run one way, which is the finding

**Nine of the fourteen records the rule excuses as near misses are, to a reader, unrelated.** Not one of
the twenty it calls noise did the reader want. So the rule is conservative about noise and generous about
near misses, and both of those push the published numbers in the same direction: the noise column is a
**floor**, exactly as PRECISION.md has been claiming in a caveat for two phases - except that the caveat is
now a measurement, and it has a size.

The examples are ordinary and checkable by hand, which is the test of whether a judge is doing anything:

- "Does shutting the window log me out?" -> `auth-lockout`. The judge: *record covers failed sign-in
  lockouts, not logout from closing windows.* A shared word and a shared family, and not the same fact.
- "Determine the East Width of a Unicode" -> `fast-string-truncated-width`. The judge: *record is about
  string truncation, not measuring East Asian width.*
- "Which units use a 3+2 seating layout?" -> `class-dunmere-age`. The judge: *record covers unit age and
  service date, not seating layout.*

Each of those is a record a caller pays for and cannot use, and each is currently excluded from the noise
count because it shares a name token or three words with the answer.

### What this does not settle

One model at one temperature is a reader, not a standard. Two readers would disagree with each other, and
the number here is the distance between this rule and this reader, not between the rule and the truth. A
second model would make that visible and a third would make it quantifiable; neither is done, and the
report says so in its own words rather than in this one.

The prompt is a judgement call of its own: it asks whether the record would help, not whether it is the
answer, because the corpus already says which record is the answer and asking again would test nothing.

### And a self-bug that got worse before it got caught

**59. The read cap truncated a source file and the write put it back short.** `claims.py` had grown past
the fifty-thousand-character ceiling of the read tool, so the copy I edited was missing its last function -
including the `if __name__` block. The edit applied, the file was written, and the ledger then ran
**silently, doing nothing, exiting 0**: exactly the failure class this repository exists to find, in the
tool that counts its own claims. It was caught by running it, seeing no output, and checking the file
against `git show HEAD`. Restored from git and re-applied through a script that reads the whole file, which
is what bug 55 already said to do.

### What this costs

Twenty minutes of model time, sixty cached judgments, one new tool, one new claim, one CI step that needs
neither model nor network, and no subject measured - because the thing under test this time was the
checker.


## Addendum 42: two readers, and a claim that stopped holding

The last phase's number was one model's distance from one rule. A single kappa cannot say whether the
disagreement belongs to the rule or to the reader, so this asks a second model the same sixty questions -
same pairs, same prompt, no label and no corpus in it - and reports the **ceiling**: how far the two readers
are from each other on the pairs both judged.

| reader | pairs | agreement with the rule | kappa | rule says near, reader says no | reader wants what the rule calls noise |
|---|---|---|---|---|---|
| `glm-5.3:cloud` | 54 | 45 | **0.67** | 9 | 0 |
| `deepseek-v4.1-flash:cloud` | 60 | 46 | **0.53** | 12 | 2 |
| the two readers, against each other | 54 | 49 | **0.81** | - | - |

**The ceiling is high, which makes the rule's distance real.** Two readers agree with each other at kappa
0.81 on the same pairs and split on only 5 of 54, so the rule's 0.53 to 0.67 is not the noise of an
unstable question - it is a rule disagreeing with a fairly stable reading.

**And the claim flipped.** `rule-reads-like-a-reader` held last phase at 0.67 against one reader. It now
requires **every** reader to clear 0.6, and one of them does not: it **FAILS**, and the ledger is 10 of 38.
That is the whole point of asking twice, and it is worth stating plainly that the previous phase's verdict
was a verdict about one model.

### The readers, where both agreed, against the rule

| the rule says | both readers say relevant | both say not | they split |
|---|---|---|---|
| answer | 18 of 20 | 0 of 20 | 2 |
| near miss | 5 of 14 | **8 of 14** | 1 |
| noise | 0 of 20 | 18 of 20 | 2 |

**Eight of the fourteen records the rule excuses as near misses are, to both readers, unrelated** - and
two of the twenty it calls noise are records both readers would use. The first number is the one that
matters: it means the noise column in PRECISION.md is a floor, which that report has now claimed for three
phases on the strength of an argument. It has a size now, in two directions, agreed by two readers.

The pairs they split on are instructive in the other direction: two of them are records the corpus says
**answer** the question, and the readers disagree about whether the record helps. `deepseek-v4.1-flash`
refused two of the twenty expected answers, which is why its other numbers are printed beside its
calibration rather than on their own.

### One self-bug, numbered 60, caught before it could lie

**60. The cache key did not include the reader.** The first version of `judge.py` keyed a judgment by the
pair alone, which was right while there was one model and silently wrong the moment a second was added:
the second model's verdict would have overwritten the first's, and the tool would have reported two
opinions that were one opinion counted twice. The keys carry the model now, old entries are re-keyed by the
model they recorded, and the migration printed how many it moved.

### What this does not settle

Two readers at one temperature are two opinions, not a standard. Neither is calibrated against a person,
and that is the next rung: the same sixty pairs, put to somebody who actually asked these questions, would
say whether the readers are right about what helps. It is expensive, it is the only way to get a number
that is not a model's opinion, and naming it is all this phase does about it.

### What this costs

Sixty more model calls, one cache migration, one claim split in two, one claim that stopped holding, and no
subject measured - because the thing under test was still the checker.


## Addendum 43: the third labeller was a person, and it said the readers were right

The last phase ended at the only rung it could not climb: two readers are two models, and neither is
calibrated against a human. So six pairs went to the person who asked for this work - the question and the
record, no label, no rule verdict and no reader verdict in front of them.

**Four of the six were chosen BECAUSE the rule and both readers disagree about them.** That is a probe, not
a sample, and no kappa is computed over it: it answers one narrow question, and it carries one control.

| the rule says | pairs asked | the readers | the person |
|---|---|---|---|
| answer (control) | 1 | agree on 1 of 1 | said relevant |
| **near miss** | **4** | agree on 4 of 4 | **called all 4 unrelated** |
| noise | 1 | agree on 0 of 1 | said unrelated |

**On all four records the rule excuses as near misses, the person said unrelated** - the same answer both
readers gave. The floor under the noise column is no longer two models' opinion of a rule: on exactly the
pairs where that judgement is questionable, a person read the record and agreed. And the control held, so
the labeller was reading rather than clicking.

**The noise row is the interesting one.** That pair is where the readers disagreed with each other - one
called it relevant, one did not - and the person sided with the rule that called it noise. A human being
settled a split between two models in favour of the string rule, which is worth remembering the next time
somebody suggests a model's judgement is simply better than a rule's: on this evidence it is sometimes
better and sometimes not, and the rule was right when they disagreed.

### What this changes in the published numbers

Nothing moves, and that is the result. The near-miss count stays a floor with the same size - eight of
fourteen in the two-reader sample, four of four in the person's - and the direction is confirmed by a third,
non-model labeller. The ledger gains `readers-match-a-person`, which **holds** at 4 of 4 and 1 of 1, and is now
11 of 39.

### What this does not settle, and now it is a real limit rather than an excuse

Six pairs is a probe. It says the readers and a person agree where the rule is questionable; it does not
say by how much, and it cannot, because the pairs were picked for disagreement rather than at random. A
random sixty pairs put to a person would give a kappa - and that is an hour of somebody's time, which is
the honest price of turning this from a probe into a measurement.

The control is one pair, which is too few to establish that a labeller is reliable; it establishes only
that this one was not clicking through.

### What this costs

Six questions, one file of labels, one claim, and the end of the ladder this repository could climb on its
own. Everything above it needs somebody who is not a model.


## Addendum 44: the guard that found two stale reports and a lie in a title

Twenty-odd files in this repository open with **"Generated by X. Do not edit by hand."** Nothing checked it.
The CI regenerated a few of them to grep for sentences, which proves they run, not that they match. So the
next increment was the cheapest unguarded claim in the repository, and the first thing it did was fail.

The guard regenerates every report from the committed results - report modes only, nothing that would
re-measure a subject, because a check that edits the evidence it is checking is not one - and fails on a
single changed byte. On its first run, two of the twenty-one had drifted:

**@@REAL-CORPUS.md@@ had been wrong for two phases.** When `memory-mcp-1file`'s real-corpus report was found
stale and re-measured - it had been answering twelve questions the corpus no longer asked - its numbers
moved from 47 hits to 48, and the report that quotes it was never regenerated. Every Spearman correlation
in that file moved with it: 0.798 to 0.777 against corpus A, 0.639 to 0.632 against B, 0.675 to 0.664
against C. Nothing published in prose depended on the difference, which is luck rather than discipline.

**@@GROWTH.md@@ contradicted itself in its own first sentence.** It said "Up to 5000 records per subject" beside
a table of five-thousand-record runs, and regenerating it produced "Up to 500". The table was right; the
**report mode was wrong** - @@--report-only@@ printed the depth from a default flag value instead of from the runs
it was printing, so the same command that made the report reproducible also made its title false. That is
self-bug 61, and it is the exact shape of bug the repository keeps finding: a number taken from the thing
that asked for the work rather than from the thing that did it.

### What the guard covers, and what it does not

It covers the seventeen reports whose mode re-reads committed results: @@MATRIX.md@@, @@RESOLUTION.md@@, @@BAND.md@@,
@@AGENT.md@@, @@ITEMS.md@@, @@REAL-CORPUS.md@@, @@DISTANCE.md@@, @@MORPHOLOGY.md@@, @@MULTI-RECORD.md@@, @@SUPERSESSION.md@@,
@@EXAM-SIZE.md@@, @@PRECISION.md@@, @@JUDGE.md@@, @@GROWTH.md@@, @@CLAIMS.md@@, the live block in @@docs/subjects.md@@, and
@@README.md@@'s claim count.

It does **not** cover @@CALIBRATION.md@@, @@MUTANTS.md@@ or @@RETRIEVAL-MUTANTS.md@@, because refreshing those means
re-running subjects or mutants rather than re-reading rows - they are checked by their own jobs for
content, not for currency. That is a hole and it is stated rather than left for a reader to discover: a
report is only as current as the cheapest way somebody can rebuild it, and three of them cost a run.

### What this proves

Not that the generators are right - the guard compares a report to its generator, and a wrong generator is
a consistent wrong report. What it proves is that no report here can drift from the numbers under
@@results/@@ without the build going red, which is a property this repository has claimed in prose for eight
phases and has now earned.


## Addendum 45: the hole in the guard, closed the same day

Addendum 44 said the new regeneration guard covered seventeen report modes and named the three it could
not: @@CALIBRATION.md@@, @@MUTANTS.md@@ and @@RETRIEVAL-MUTANTS.md@@, because refreshing them meant re-running
subjects or mutants rather than re-reading rows. That is closed. Each of the three now has a @@--report@@ that
renders from committed data, and the guard runs all twenty.

**@@calibration.py --report@@** reads the eight saved control runs - four controls against two corpora, all of
them already in @@results/@@ - and rebuilds the table. **@@retrieval_mutants.py --report@@** reads the eight saved
lever runs the same way. **@@mutants.py@@** now writes @@results/mutants.json@@ (the twelve verdict sets it already
computed and threw away), and @@--report@@ renders @@MUTANTS.md@@ from it.

### What the three said when they were first pointed at their own output

**@RETRIEVAL-MUTANTS.md@ and @MUTANTS.md@ reproduced byte for byte.** That is a real result rather than a
formality: the mutant tables claim that every predicted verdict was written down before the run and that
the run matched, and now the committed table is provably the render of the committed verdicts rather than a
file somebody typed.

**@@CALIBRATION.md@@ did not, and the fault was mine in the new code.** The report mode printed "Repeated 2
times per question" where the table had said 3, because the run count was taken from
@len(rows[0]["per_run"])@ - and @@per_run@@ is a **dict with two keys**, @@hit3@@ and @@answered@@, so its length is
2 however many times the question was asked. Self-bug 62, and a good one: a plausible-looking wrong measure
that produces a small integer in a sentence nobody would check. The count now comes from the runs inside
that dict, which is where it lives.

### What the guard now guarantees, and what is still outside it

Twenty report modes, every one of them regenerating from committed results and failing the build on a
changed byte. The remaining blind spot is nothing published: it is the three measurement jobs (probes,
mutants, retrieval levers) whose *outputs* are the inputs to these reports, and a stale measurement is
invisible to a check that compares a report to the results under it. That is the boundary of what
regeneration can prove, and it is the same boundary this repository has been drawing all along: a report
can only be as true as the rows it reads.


## Addendum 46: the work is prepared, the person is not

Addendum 43 ended at the rung this repository cannot climb: the judge's six pairs are a **probe** - chosen
for disagreement - and a rate needs a random draw put in front of a person. Asking for that is one thing;
asking for it *unprepared* is another. So the preparation now exists.

`judge.py --export-human=60` draws sixty pairs **at random** from the 5,336 the repository holds, writes a
questionnaire - question, record, one line each, nothing else - and a file beside it whose only empty field
is `verdict`. `--import-human` takes the answers back, refuses anything that is not YES or NO, and the report
renders a section that did not exist before: agreement with the rule on a **random** sample, with a kappa,
and a sentence saying how wide that interval is while the count is small.

**Two sampling frames, and confusing them would flatter the first.** The readers were asked twenty of each
kind because the question there is *where does the rule disagree with a reader*; a person is asked a random
draw because the question there is *how often is the rule wrong*. The report keeps them apart, in separate
sections, with the frame of each written at the top of it.

### A bug that only a real key name would have found

The new section read `human["sample"]` for its labels - and the probe file already used `sample` for a
sentence describing how those six pairs were chosen, so the report tried to read a **string** as a dictionary
and died with `'str' object has no attribute 'get'`. Renaming the new key to `random` fixed it. Two things had
the same name because they were two things with the same name; this repository has made that mistake often
enough that it is worth naming the class rather than the instance.

### What is now guarded

The CI draws the sixty pairs again on every push and asserts the draw is **reproducible**, that no pair is
repeated, that the questionnaire is not pre-answered, and that the committed files are byte-identical to
what the draw produces. A questionnaire that quietly contained the answers would measure the person's
patience rather than their reading.

### What is still missing, and it is one thing

Somebody to read sixty pairs and type YES or NO sixty times. The report says so in its own words now, at the
end, with the path to the file that is waiting. Everything else on this ladder is measured, guarded, or
written down as a limit with a number beside it.


## Addendum 47: the noise reading gets a mutation battery, and the score fails it

The probes have had twelve deliberately broken servers since Addendum 19. The retrieval score has had four
levers since the phase before this one. **The noise reading had none** - it was validated by a rule, a
judge and a person, which is three opinions about a scale nobody had tried to break.

So: two levers of its own, against the positive control. Same search, same store, with two records appended
that are not the answer - `pad-far` appending records that share no word with the question, `pad-near`
appending records that share one. They are appended **after** the control's own top three, so hit@1 and
hit@3 cannot see them by construction, and anything that moved moved for exactly one reason.

| run | corpus | score | hit@3 | noise records | noise per correct | answer share | near misses |
|---|---|---|---|---|---|---|---|
| control | A | 37 | 25 | 8 | 0.32 | 63% | 7 |
| `pad-far` | A | **37** | 25 | **48** | **1.92** | **31%** | 8 |
| `pad-near` | A | **38** | 26 | 32 | 1.23 | 35% | 15 |
| control | B | 44 | 32 | 5 | 0.16 | 58% | 18 |
| `pad-far` | B | **44** | 32 | **44** | **1.38** | **33%** | 23 |
| `pad-near` | B | **44** | 32 | 35 | 1.09 | 33% | 30 |

**The score cannot see any of it.** On both corpora the padded subject scores exactly what the control
scores, while the noise count multiplies by six and nine and the share of characters that are an answer
halves. The ledger's @padding-is-free@ claim **HOLDS**, and it is in the ledger because it is a defect: a
number that does not move when a subject triples its output is not measuring output.

**And the near-miss padding RAISED the score.** On corpus A, `pad-near` scores 38 where the control scores
37 - because a padder choosing records in the question's own vocabulary can stumble onto the answer the
control missed, and a score that counts a set of three cannot distinguish finding a fact from surrounding
it. Volume is not always noise; sometimes it is recall, and this repository's headline number has no way to
say which one it is looking at.

### What the levers say about the reading

The two paddings land where the reading says they should: unrelated padding moves the noise count and
leaves the near-miss count almost untouched (7 to 8), near-miss padding moves the near-miss count and
raises noise per correct answer less than the other does (1.23 against 1.92). A reading that could not tell
those two apart would not be a reading of what it claims. This one can.

**And one process finding: the first version of the lever measured nothing.** It called the control's search
with k=1 and appended two records, which changed two things at once - the returned list lost whatever the
control had found at ranks two and three, and gained padding - so the difference from the control could be
attributed to neither. It was caught by looking at the numbers and finding that hit@3 had *fallen* on
corpus B, which is impossible for a lever that only appends. A lever that moves two things measures
nothing; this repository has now made that mistake once in the probes and once here.

### What this does not settle

Two levers, one corpus pair, one padding width of two records. A padder that appends ten, or that pads with
records from the same family as the answer, is not tested. What is established is narrower and enough to
act on: the score is blind to the quantity the precision reading prices, and padding can even pay.


## Addendum 48: four corpora, and a denominator bug in my own table

Addendum 47 published the padding mutants on two corpora. The levers were then run on the authorless
corpus and on the 276-question exam as well, because those are where most of this repository's numbers
come from, and the section now covers all four.

| corpus | control score | padded score | control noise per correct | padded |
|---|---|---|---|---|
| A | 37 | **37** | 0.32 | **1.92** |
| B | 44 | **44** | 0.16 | **1.38** |
| real | 60 | **60** | 0.06 | **1.40** |
| the exam | 268 | **268** | 0.10 | **1.29** |

**Sixteen checks, all holding**, and the exam is the sharpest: padding with unrelated records multiplies
the noise count by **12.8** while the score does not move by one point.

### And the first version of that table was wrong, in the way this repository keeps catching

The exam's control row first read **292 against a padded 268**, which looked like a finding - padding costs
you 24 points. It was not a finding. The score and hit@3 columns were summed over *every* row in each result
file while the columns beside them were summed over the live questions only, so the control row counted 300
rows against the padded row's 276: **the same defect as the "0 of 0" that sat in RESOLUTION.md for three
phases, and the same one as counting a question twice.** The rows are now filtered once, at the top, and
every number in the table is over the same questions.

Two things follow, and only one of them is about the code. The first is that a comparison table is the
easiest place in the world to compare two different things, and this one did it inside a section whose
subject is *not being able to see what came back*. The second is that the fix made the result stronger
rather than weaker: with one denominator, the score is identical on all four corpora, which is a cleaner
statement of the blindness than the two-corpora version.

## Addendum 49: nine corpora, and a lever that did not know where it was aiming

The padding battery now runs on all nine corpora rather than four, and the count is **35 of 36**.
The score does not move by a point anywhere - A 37/37, B 44/44, C 43/43, real 60/60, distance
104/104, morph 69/69, multi 32/32, the exam 268/268, supersession 66/66 - while the noise count
multiplies by between 4.8 and 22.3 times. `padding-is-free` in the ledger now reads from the same
panel the report prints instead of rescoring raw rows, so it is checked on every corpus here and
not only on the two the calibration controls cover.

### The new number turned out to be about my own lever

A lever is evidence only if it moves the thing it is named after. The appended records are the
difference between a lever's row and the control's row for the same question, so asking what the
classifier made of them needs no new run:

| lever | appended records | called near | called noise | called the answer |
|---|---|---|---|---|
| `pad-far` | 629 | 7 | 622 | 0 |
| `pad-near` | 607 | 66 | 540 | 1 |

`pad-far` earns its name - 99% noise. `pad-near` does not. It appends the first records in name
order whose body contains **one** non-stopword from the question, and the classifier calls a record
near only when it shares a name token with the answer or **three** distinguishing words with it.
One word against three, and the gap is 89% of everything that lever touches.

Closing it would mean handing the lever the corpus-wide word frequencies that make a word
distinguishing. An adapter talking to a server over a tool call does not have them, and the other
way out - tuning the lever until it agrees with the rule that judges it - would make the two
sections agree by construction and measure nothing. The lever stays weak, and the weakness is
printed beside its numbers instead of being left for a reader to discover.

### Which is also why one check fails for the first time

On `morph` the near lever leaves a higher bill than the unrelated one, 1.01 against 0.93, so the
check that near padding costs less than unrelated padding fails. The landing table says why: 9 of
the 75 records it appended there were called near and 66 were called noise. On a corpus built out
of morphological variants of one word each, the two levers are one lever by the only rule that
tells them apart, so the difference between their bills is a difference in degree between two
things that rule cannot separate. The check stays in the report as a failure rather than being
redefined as not checkable, because the first thing a weaker result tempts you to do is change the
test.

And the one answer in that table is the mechanism behind the score that rose on corpus A: a padder
picking records in the question's own vocabulary appended the answer the control had missed, and a
score that counts a set of three cannot tell that from the padding beside it.

## Addendum 50: the guard was checked, the list of what it guards was not

The regeneration guard exists because two published documents had drifted while every check passed:
it re-runs nineteen generators from committed results and fails if a byte moves. Nothing anywhere
checked that the list of nineteen was complete. A document added after the guard was written would
carry the same sentence, be edited by hand, and pass - the same defect one level up, which is this
repository's most reliable way of producing one.

`guard_cover.py` reads the claim out of each document (`Generated by X. Do not edit by hand.`), reads
the guard out of the workflow file, and compares the two sets. It found exactly one escapee:
**THIRD-CORPUS.md**, generated by `third_corpus.py`, committed, grepped in CI for two sentences, and
never once re-run from its own inputs. The tool reads only committed results - it was always cheap
enough to guard, nobody had put it in the list.

Run the other way round it found a second thing: `CLAIMS.md` is written entirely by `claims.py` and
carried no banner, so nothing in it claimed to be generated and nothing could object to a hand edit.
The banner is emitted by the generator now, not typed into the file, so a document without one is a
document this check can see again.

| direction | what it catches | how it is proven |
|---|---|---|
| a generated document is not in the guard | THIRD-CORPUS.md, and the next one | CI writes `docs/_plant.md` naming a tool nobody has |
| a guard line regenerates nothing | a stale entry left behind by a rename | `--workflow` points at a copy with `python nothing.py` in it |

Both directions now fail the build on purpose in CI, because a coverage check that cannot be seen
failing is the same shape of thing as the line it was written to find. Two tools are exempted by
name rather than by silence - `matrix.py` prints the block `sync_readme.py` writes into a page whose
prose is written by hand - so an exemption is a sentence in the code instead of an absence.

**What this still does not do.** It checks coverage, not freshness: replace a results file and
regenerate, and every document will agree with the new numbers and this check will pass. The
published headline figures are quoted in prose in the README, and nothing pins them.

## Addendum 51: the check for checks nobody has seen fail, seen failing

The step added in the last commit failed on the runner, and the log ended at a line that had
succeeded. That is the whole problem with a step made of silent commands: four of them print nothing
when they work, so the log names none of them when one does not. It now prints seven numbered
sentences and the next failure will be attributable to a number.

The failure itself was worth the round trip. The step plants a document naming a generator that does
not exist and requires the coverage check to refuse it; the second plant is a workflow whose guard
re-runs a tool that regenerates nothing, and the assertion was

    grep -q "regenerating nothing: nothing.py" /tmp/stale.txt

The message the check prints is **"in the guard and generating nothing: nothing.py"**. `regenerating`
is `generating` with two letters in front of it, and the grep could never have matched anything. The
check under test had done exactly what it was built for; the line asserting it had not.

Fixing it exposed a second one, which is the more interesting of the two. The planted page was
written with

    printf "%s\n" "Generated by `nothing.py`. Do not edit by hand." > docs/_plant.md

and in bash a backtick inside double quotes is a command substitution: the shell tried to run
`nothing.py`, pasted the empty result, and planted a page that named no generator at all. The check
then passed it, the step reported that the coverage check had passed a document it should have
refused, and the whole thing failed as a false alarm. **A plant that does not plant the thing it
claims to plant is not a test of anything** - the assertion was right and the fixture was empty, which
is the same defect as the `0 of 0` table and the denominator bug in Addendum 48, one layer further
out. Single quotes fix it: a literal backtick is what the page needs to say.

Both are fixed and the step now exits 0 locally with each of its seven stages named in the log. The
general lesson is the one this repository keeps relearning from a new angle: **the assertion is part
of the instrument**, and an assertion that can never be true fails exactly like an instrument that
measures the wrong thing - quietly, in the direction of a green build, until somebody runs it.

## Addendum 52: the hand-copied table was wrong for four phases

Addendum 50 ended by naming what the coverage check does not do: it checks coverage, not freshness.
Replace a results file, regenerate, and every page agrees with the new numbers. The prose was worse
than that, because it was not regenerated at all. `docs/precision.md` is the docs version of the
precision argument, moved out of the README when the README got long, and it carried its own copy of
two generated tables.

When the first pin ran, the copy said:

| the page said | the results say |
|---|---|
| `memento` answers 326 questions correctly | **294** |
| and hands back 1,169 records nobody asked for | **1115** |
| the control answers 625 | **585** |
| five corpora carry a silence band of 147 questions | **146**, and 98 of them the exam's, not 99 |
| the whole junk table, 7 rows by 7 columns, `memdb` at 148.21 noise per correct | **160.42** |

Every one of those was true when the page was written and none of them was true any more: the exam
lost 24 duplicate slots, the corpora were repaired, and the page kept its copy. Nothing in this
repository would have noticed - the guard re-runs generated pages, the claims are re-evaluated, and a
hand-written sentence has no connection to anything a build can break.

### The fix is to let the sentence be the pin

`figures.py` names a file, a regular expression that must match it exactly once, and the readings
behind each captured number. There is no second copy of a value to keep in step: the word in the page
is the pin, and the comparison is against the same module that owns the definition. Rewording a
pinned sentence is a build failure until the pin is restated, which is the intended cost - a sentence
nobody can check is a sentence nobody has checked.

Twenty numbers are pinned across three pages, and the check has been seen failing: CI moves the
README's 37 to 38, requires the failure, requires it to name `control.score.A`, and puts the file back.

### The tool was called numbers.py for one commit, and that cost a claim

`numbers` is a standard library module. Python's `statistics` imports it, `claims.py` imports
`statistics` somewhere down its stack, and a file called `numbers.py` in the working directory
replaces the stdlib module for every script that runs from this directory. The first regeneration
after it was added turned `search-is-flat` from **FAILS** into **UNMEASURED** - *module numbers has
no attribute Rational* - and the ledger's headline would have gone from 12 of 40 to 11 of 40 for a
reason that had nothing to do with any subject, any corpus or any server.

Nothing was looking for that. It surfaced because the guard regenerates `CLAIMS.md` and the change
appeared in a routine `git status`; a smaller shadowing bug - one that changed a number nobody
regenerates - would have gone through. The file is `figures.py` now, which is a better name for what
it holds, and CI refuses any file in this directory whose name is a standard library module.


### Two things the pins found that are not drift

The page said *the subjects that decide per question answer 15 of 336 on the four short bands and 36
of 99 on the long exam.* The 15 of 336 held exactly. The second half never made sense: 99 was one
subject's band before the exam lost its duplicate slots, and 36 is a count pooled over seven subjects.
Both halves had drifted independently and the sentence read like a measurement the whole time. It is
**36 of 686** now.

And the page's two full tables are three rows each now, with a line pointing at the generated one.
Duplicating a generated table into prose is a promise to keep forty numbers in step by hand, and the
promise had already been broken for four phases. The argument survives on the rows it turns on.

The limit is honest and narrow: **the check covers the numbers somebody thought to pin**, and only
sentences, not tables. A page can gain an unpinned figure tomorrow and nothing will object. What has
changed is that the failure mode this repository keeps hitting - a number quietly outliving its
evidence - now has a place where it is caught, for the numbers that argue the case.

## Addendum 53: the instrument, measured on itself

Every number in the judge ladder compares two different readers. That leaves the central question
open: when two models agree on 49 of 54 pairs (kappa **0.81**), is the disagreement the *task* - the
pairs are genuinely arguable - or is it the *model*, sampling a different answer each time? A person
is asked once and cannot answer that. A model can be asked twice.

So every pair each reader had already judged was put to it again, at temperature **0.70** rather than
0.0. The temperature is the whole design: a model at zero returns what it returned, and a repeat that
cannot disagree is not a test of anything. The second answers live in their own file
(`results/judgments-again.json`) so the first ones cannot be overwritten by a re-run.

| reader | pairs asked twice | said the same thing | kappa | relevant then not | not then relevant |
|---|---|---|---|---|---|
| `deepseek-v4.1-flash` | 60 | 56 (93%) | **0.87** | 2 | 2 |
| `glm-5.3` | 53 | 53 (100%) | **1.00** | 0 | 0 |

Both readers are steadier with themselves than the pair of readers is with each other - 0.87 and 1.00
against 0.81 - so the ceiling is on the task and not on the dice. That is the answer the ladder was
missing, and it is the first measurement in this repository where the *instrument* is the subject
rather than another server.

### The half of it that is suspicious

`glm-5.3` repeated perfectly. Under sampling, a perfect repetition means one of two things and this
report cannot tell them apart: the judgement never came near the boundary, or the endpoint was not
sampling at all. The evidence that asking twice really was asking twice is the other reader, which
moved on **4 of 60** pairs under an identical request - if the framework had been returning a cached
reply, both would read 100% and the number would be worthless. It is written beside the result rather
than below it, because a suspicious 1.00 that goes unremarked is how this repository has been wrong
before.

### The claim was made harder on purpose

The first version of `a-reader-is-steady` compared the **steadiest** reader's repeatability against the
agreement between readers, and it held with room to spare - the kind of claim that is true because of
which reader got picked. It now requires **every** reader to beat the inter-reader agreement, which
still holds (0.87 > 0.81) and no longer rests on a choice.

The ledger reads **13 of 41**: the count moved because a claim was added and holds, not because any of
the twelve that failed were repaired. Two of the forty-one - `padding-is-free` and this one - hold
*because* they are defects.

### What it does not settle

One model, one prompt and one training set reading a pair twice is also one way of being wrong twice:
a reader that calls every near miss useful is perfectly repeatable and still wrong, and only the
rule-against-reader table can see that one. And the pairs come from the **enriched** sample, twenty of
each kind, so this measures repeatability where the rule and a reader disagree rather than on a random
draw - an easier test than it looks, and the only sample the readers were asked about.

## Addendum 54: a pin cannot see an absence

Addendum 52 ended by naming what the prose pin does not do: it checks the numbers somebody wrote
down. The cost page showed why that is not enough. Its table is a *copy* of one the matrix tool
prints, and the copy held nine subjects. The timings on disk hold **eleven**: `statecore-mcp` at
5,710 bytes per question (98x the answer) and `mcp-duckdb-memory-server` at 210 had been measured
since and never copied over. Every number in the copied rows was exactly right, which is precisely
the case a pin cannot catch - `figures.py` would have checked all nine rows and passed.

The same page also said "the two subjects that cost 39 bytes per question return *nothing*" when
there are three, the third being `mcp-knowledge-graph` at 0.7x. That one a pin could have caught,
and does now.

### The transcripts are generated from the command they name

`sync_readme.py` filled the first `$ python matrix.py` block it found, in the first page that had
one. The cost block was excluded by name (`not "--cost-only"`), because `matrix.py --cost-only`
**forces a re-measurement** - it is a timing pass, and a page cannot be rendered from a pass that
runs eleven servers. So:

- `matrix.py --cost-only --report-only` now prints that table from the cached `results/*-cost.json`
  and launches nothing, which is the rule the file already stated about `--report-only`.
- `sync_readme.py` fills **every** report-shaped transcript in **every** page, by running the
  command the block names with `--report-only` added, and preserves the fence's own indentation
  because a block inside a bullet belongs to the bullet.

Filling the rest found two more transcripts that had drifted, both in `compare.py` blocks, and one
of them was worse than stale.

| the page said | the results say |
|---|---|
| README: zenbrain vs memory-mcp-1file, 33 both, 4-10, p = 0.1796 | 35 both, 5-8, p = 0.5811 as written; **separated as keywords, p = 0.0225** |
| subjects: memento vs server-memory, 11-12, p = 1.0000 | 14-12, p = 0.8450 on the score, and **14-0, p = 0.0001 once the twelve unanswerable questions come out** |
| and the prose under it: "they are statistically identical" | identical **on the score**, separated on hits - the twelve-point switch decides it |

The second one is the one that matters. The paragraph's subject is a paired test that decides by
counting, and the copy beside it was four questions out of date and pointed at the opposite
conclusion from the one the current rows support. Nothing in this repository could see it: the
block was not generated, was not pinned, and the tool that was supposed to fill it exited 0 having
filled nothing.

### Two things found while doing it

The pin caught my own reading rather than the page. `its 4.3 MB store` - I pointed the reading at
memdb, whose floor is 0.75 MB, and the sentence's antecedent is memento. The check failed, the page
was right, and the mistake was in the translation from English to a computation. That is the
position a reader is in with every number in this repository, and it is now the position the
checker is in too.

And `sync_readme.py` silently skipped the README after a checkout gave it CRLF line endings: every
block's first line read as a carriage return, no block matched, the tool printed four successes and
exited 0. The stale transcript lived in exactly the page it skipped. Normalising line endings on
read costs nothing; trusting a tool that reports success without saying which files it touched does
not.







