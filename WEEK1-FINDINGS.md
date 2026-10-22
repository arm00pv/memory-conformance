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
