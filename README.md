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
verbatim         PASS              7.9s  all 9 strings came back byte for byte, over the wire: 2, 3 and 4-byte UTF-8, ...
restart          PASS             15.7s  three writes across three server lifetimes; read back [restart-0, ...]
forget           PASS              3.0s  asked to forget one record; the other two came back and it did not
findable         PASS              2.3s  all 8 acknowledged records came back in the top 3 for a search on their own name
foreign_field    FAIL              7.8s  the extra field was silently dropped by the next write
foreign_record   PASS              5.0s  the unmodelled record survived
concurrent       PASS              3.6s  20 of 20 acknowledged writes survived two servers on one store
large_record     PASS              1.9s  wrote 100000 characters, read back 100000
1 probe(s) failed
```

## What holds, and on how many corpora

`claims.py` re-checks every claim this repository makes against the committed results, on two
independently written corpora and in two phrasings, and writes the verdicts to `CLAIMS.md`:

```
$ python claims.py
**7 of the 25 claims hold in every setting measured.**
```

Five survive everywhere, including the one that matters most: **memory-mcp-1file answers more
answerable questions than anything else here**, on both corpora and in both phrasings, alone at the top.
The rest are printed beside the setting that breaks them, because that setting is their real scope.
Three of them:

- "server-memory answers no question at all" - true as written, false when the words are stripped: it
  answers two.
- "memory-lean returns fewer bytes than any subject that answers anything" - true on corpus A, and void
  on corpus B, where it answers nothing as written and so does not qualify.
- "zenbrain is better than the positive control" - false in all four readings. The control, a server
  written to pass every probe here with a keyword search bolted on, is ahead on three of them.

The suite's own error bar is in there too: five of the ten neighbouring pairs in the ranking do not reach
the same conclusion on both corpora.

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

## Retrieval: keeping is not finding

Retention is not retrieval. `retrieval.py` writes twelve memories and asks twelve questions - six that
share vocabulary with the memory they want, six paraphrases - then reports hit@1 and hit@3 on a server
that has just restarted, so search cannot ride on anything the writing process still held in memory.

> *This section records the original twelve-question run against `retained` and `basic-memory`. The
> corpus is now 72 records and 60 questions in fourteen clusters - including near-duplicate distractors and
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

## What the retrieval score means

Forty-two out of sixty describes a subject. It does not say whether sixty was ever available, and
until this phase nothing here had measured either end of that scale - the retrieval table was eleven
subjects and no controls at all. `calibration.py` runs the same sixty questions against four of them,
each the positive memory server with one thing changed:

| control | what it is | hits (A) | score (A) | hits (B) | score (B) |
|---|---|---|---|---|---|
| `oracle` | the corpus own answer key wired to a search tool | 48/60 | **60/60** | 48/60 | **60/60** |
| `control` | the positive control term overlap | 25/60 | 37/60 | 32/60 | 44/60 |
| `blind-search` | the same three records to every question | 2/60 | 2/60 | 3/60 | 3/60 |
| `mute-search` | returns nothing, ever | 0/60 | 12/60 | 0/60 | 12/60 |

**The ceiling is 48 hits and one subject is at 42 of them.** Twelve of the sixty questions have no
answer; the oracle answers all forty-eight and declines all twelve, so the most any search can hit is
48 and it is reachable. memory-mcp-1file is at 87% of that ceiling and the control is at 52%, which is
a different sentence from "best of a bad bunch" - and the only one that can be supported.

**The floor of the score is 12, not 0.** Declining a question that has no answer is correct, so a
memory that answers nothing collects all twelve of them. The hit count has a true floor of zero; the
score every paired test is computed from does not, and the gap is exactly the twelve unanswerable
questions.

**And a subject can finish below the floor.** On corpus A, `statecore-mcp` scores 0 and `memdb` 6. On
corpus B as written, `memdb` scores 2. All three answer every unanswerable question and get none of
them right, so they finish under a program that says nothing at all. On corpus B asked as keywords
nobody does - `statecore-mcp` ties at 12 - which is where the ledger leaves `silence-scores-better`
as MIXED rather than adjusting it until it passes.

That is the score doing what it says: silence is never punished, and answering is only rewarded when
the answer is right. It is a defensible metric for a paired test and it is not a ranking, which is why
the headline claim is stated in hits and not in score. The full table is
[`CALIBRATION.md`](CALIBRATION.md).
## Does every question measure something?

A question every subject answers and a question no subject answers carry the same information about
the differences between subjects: none. `items.py` is the analysis a test gets before anyone trusts it -
difficulty `p`, the share of subjects that got the question right, and discrimination `D`, the gap
between the top half of subjects by total score and the bottom half. One subject is excluded from it:
memory-mcp-1file leaks state, and letting a leak decide which questions work would be the same mistake
as grading it.

| corpus | band | questions | nobody can tell apart | mean p | mean D |
|---|---|---|---|---|---|
| A | easy | 16 | 0 | 0.39 | **+0.64** |
| A | hard | 16 | **5** | 0.08 | +0.16 |
| A | adversarial | 16 | 0 | 0.22 | **+0.44** |
| A | absent | 12 | 0 | 0.60 | **+0.00** |
| B | easy | 16 | 0 | 0.31 | **+0.62** |
| B | hard | 16 | **9** | 0.06 | +0.10 |
| B | adversarial | 16 | 0 | 0.24 | **+0.48** |
| B | absent | 12 | 0 | 0.71 | **-0.22** |

**The hard band is a steep gradient, not a wall - and my first report of it was wrong.** The analysis
excludes the subject that leaks state, and that subject answers **twelve of the sixteen hard questions**
on corpus A. Removing it and then reporting that the band measures nothing let an exclusion do the work
of a conclusion. Counted properly:

| corpus | band | answered by (in scope) | the excluded leader |
|---|---|---|---|
| A | easy | 6 of 10 - zenbrain 16, control 16, memory-lean 14 | 16 |
| A | hard | 3 of 10 - zenbrain 8, memento 4, duckdb 1 | **12** |
| A | adversarial | 4 of 10 - zenbrain 16, control 9, memento 7 | 14 |
| B | easy | 4 of 10 - zenbrain 16, control 16, memento 9 | 16 |
| B | hard | 4 of 10 - memento 6, zenbrain 2, memdb 1 | **13** |
| B | adversarial | 4 of 10 - zenbrain 15, control 15, memento 4 | 16 |

**So the table is smaller than it looks.** On corpus A four of the ten in-scope subjects answer no
question in any band - they score exactly 12, their absent points - and on corpus B five do. The
ranking is produced by six subjects, and most of it by three.

**And the hard band does not replicate below the leader.** The leader holds 12 then 13 of sixteen. Under
it, zenbrain goes from 8 to 2 and memento from 4 to 6: the band keeps its top and loses its order. A
band that ranks its subjects differently on a second corpus is a band whose ranking should not be
quoted alone, which is the same finding the neighbouring-pair test produced for the table as a whole and
this one gives a reason for.


**The unanswerable band measures a habit, and it is worth twelve of the sixty points.** Every subject
on both corpora either declines all twelve unanswerable questions or declines none of them - there is
no gradient in between. Its discrimination is +0.00 on corpus A and -0.22 on corpus B; asked as
keywords, +0.13 and -0.40. On corpus B the better subjects are the ones who speak, so the band that is
supposed to reward restraint is punishing ability.

**So `compare.py` now runs its paired test twice.** The second run drops the twelve unanswerable
questions, and a conclusion that depends on them says so:

```
  as written
    only zenbrain correct   15
    only control correct    12
    exact McNemar p = 0.7011  -> not separated by this corpus
    without the 12 unanswerable questions: 15-0, p = 0.0001 -> separated
    THE TWELVE-POINT SWITCH DECIDES THIS ONE
```

zenbrain wins fifteen answerable questions to none, and the twelve-point switch hands the control back
exactly twelve of them - a 15-0 result becomes 15-12 and a p of 0.0001 becomes 0.70. Asked as keywords
the same switch runs the other way. Neither number is the answer; the pair is.

**The one-word-trap warning is directionally right and not established.** Mean `D` is +0.42 across the
eleven narrow traps in corpus A and +0.48 across the five wider ones; on corpus B, +0.33 across three
and +0.51 across thirteen. Two groups of that size over ten subjects cannot settle it, and what the
measurement does is stop the warning from being either ignored or obeyed without a number next to it.

Full tables, including every question that separates nobody, are in [`ITEMS.md`](ITEMS.md).

## What the corpus can separate

Every row of the retrieval table sits next to every other, and `compare.py` answers the question for one
pair at a time. `resolution.py` asks it for all **55 pairs** at once, which is the question the tie block
makes urgent: six subjects score the same twelve points, and a table that lists them in some order invites
a reader to read an order into it.

| corpus | phrasing | pairs separated, on the score | on hits alone |
|---|---|---|---|
| A | written | **39 of 55** | 43 of 55 |
| A | keywords | **41 of 55** | 42 of 55 |
| B | written | **37 of 55** | 38 of 55 |
| B | keywords | **31 of 55** | 39 of 55 |
| C | written | **37 of 55** | 38 of 55 |
| C | keywords | **38 of 55** | 39 of 55 |

So the instrument settles roughly two thirds of the comparisons it invites, and 14 pairs change verdict
between the two phrasings on each corpus. The groups it cannot split, computed from the separation
relation rather than from the scores:

- **`server-memory` 1.0.0 and 2.0.0, `memento`, `memdb`, `memory-lean`, `mcp-knowledge-graph`,
  `mcp-duckdb-memory-server`** - one group, but 8 of its 21 internal pairs are separated directly. A
  staircase, not a tie.
- **`control`, `zenbrain`, `memory-mcp-1file`** - one group, and **none** of its three internal pairs is
  separated on the score. On corpus A as written that is a three-way tie; measured across all twelve
  rulers it is a contest between two of them, with the third inside the band and never once first. The
  next section is the difference between those two sentences.
- **`statecore-mcp`** - alone, separated from everybody.

### The leader is not ahead of the control, until you remove the twelve-point switch

| `memory-mcp-1file` against | score, written | score, keywords | hits, written | hits, keywords |
|---|---|---|---|---|
| `control` | 0.345 | 1.000 | **0.000** | **0.002** |
| `zenbrain` | 0.581 | **0.022** | 0.774 | **0.022** |
| `memory-lean` | **0.009** | 0.065 | **0.000** | **0.000** |
| everyone else | **separated on all four readings** | | | |

Bold is a pair the corpus separates. The leader beats the positive control **never** on the score and
**three times out of four** on hits, and the reason is the twelve-point switch: the leader answers eleven
of the unanswerable questions and the control declines all twelve, which hands eleven points back and
cancels a gap the hit count can see. Against the runner-up the pattern has the same shape and a different
cause - phrasing, not the switch.

That is what the ledger's `metrics-agree` claim tests, and it **FAILS in all four settings**: the two
metrics do not rank the top of this table the same way, and each of them prefers a different subject.

Full tables, including every pair and every flip, are in [`RESOLUTION.md`](RESOLUTION.md).

### The 0-of-0 that sat in that file for three phases

The "between the corpora" table in `RESOLUTION.md` looked its rows up with a two-part key against a dict
keyed by three parts, so it compared an empty set with an empty set and printed **0 of 0** on every row.
As a finding, an empty comparison reads exactly like a result - *the corpora never disagree* - which is
the failure mode this repository is about, committed by the tool that reports it. Fixed, and the
corrected table is the most interesting one in that file:

| corpora | verdicts that differ, on the score, as written | on hits alone |
|---|---|---|
| A vs B | **16 of 55** | 15 of 55 |
| A vs C | **16 of 55** | 15 of 55 |
| B vs C | **0 of 55** | **0 of 55** |

Two corpora written by different authors about different worlds reach the **same verdict on all 55
pairs**. The corpus that disagrees with both is corpus A - written before the band rules were written
down, by the hand that then wrote them down. Replication here is real between B and C, and what changed
the answer was the specification rather than the author. The ledger's `corpora-agree` claim
**FAILS**, which is its honest form: *every pair of corpora agrees* is false, while *B and C agree on
every pair* is a scope rather than a claim.

## What it would take to break a tie

"Not separated" is the instrument saying it cannot rank two subjects. That is not one fact but four, and
only one of them a longer corpus fixes cheaply. `band.py` sorts every pair on every ruler - three
corpora, two phrasings, two metrics, twelve rulers - into those kinds, and computes the price of the ones
that have a price: [`BAND.md`](BAND.md).

| kind | pair-rulers | what it means |
|---|---|---|
| identical | 73 | same outcome on every question; nothing to separate |
| no direction | 4 | they disagree evenly; no corpus separates a coin |
| small but real | 94 | one side wins the disagreements and the corpus is too short |
| out of reach | 27 | a real margin, worth more than 1,000 questions to resolve |
| separated now | 462 | already settled |

**The tie at the top is not zenbrain's, and it is only half the leader's.** Across the twelve rulers
`memory-mcp-1file` is first on nine and the **positive control is first on four** - the counts overlap
because corpus A asked as keywords puts them level. No subject leads all twelve, so *the best memory
server here* is not a sentence until a corpus, a phrasing and a metric are in front of it:

| subject | rulers at the top |
|---|---|
| `memory-mcp-1file` 0.9.2 | **9 of 12** |
| `control` 1.0.0 | **4 of 12** |
| everything else | none |

And the price. A split favours one side by a margin, across however many questions they answered
differently; at that margin, this is how long a corpus would have to be for the same exact test to call
it at 80% power:

| pair, corpus | answered differently | split | p | questions needed |
|---|---|---|---|---|
| `control` vs `1file`, A | 28 of 60 | 11-17 | 0.345 | **371** |
| `1file` vs `zenbrain`, A | 13 of 60 | 8-5 | 0.581 | **679** |
| `control` vs `1file`, C | 27 of 59 | 15-12 | 0.701 | **1,401** |
| `control` vs `1file`, B | 25 of 60 | 12-13 | 1.000 | **11,825** |

That last row is the argument. On corpus B the control and the leader disagree on **25 of 60 questions**
and split them **12 to 13**. A one-question margin across twenty-five disagreements is not a corpus being
too short - it is two subjects that differ on nearly half the questions and win equally often, and calling
it at 80% power would take a corpus two hundred times this one. The pair is settled by being unimportant
rather than by being measured. The first row is the opposite case: corpus A's sixteen-question margin is
worth about 371 questions, which is a grant application and not an impossibility, and **on hits alone that
same pair is already separated on all three corpora** - the twelve-point switch is the entire difference
between a tie worth 371 questions and no tie at all.

**Not separated is not similar.** At one end of that column `mcp-knowledge-graph` and `memdb` differ on
**one question out of 48** and no ruler separates them, because there is almost nothing to separate. At
the other end `memory-lean` and the leader differ on **36 of 60** and corpus A asked as keywords does not
separate them either, at p = 0.065 - just over the line, on a difference of twelve points. Both read as
"tied" in the table above. A reader choosing a memory server needs to know which end of that column their
pair is on, and the ranking as published does not say.

## Does the retrieval score have teeth

The ten probes have been mutation-tested since Addendum 19: twelve broken copies of the positive control,
one promise broken each, and a verdict written down before every run. The retrieval score never has been.
`retrieval_mutants.py` gives it the same treatment - four levers on the control's search, each a plausible
way to answer a question badly, with the expected numbers written before the first run.
[`RETRIEVAL-MUTANTS.md`](RETRIEVAL-MUTANTS.md)

| lever | what it does | hits | hit@1 | score |
|---|---|---|---|---|
| *(clean control)* | | 25 | 25 | 37 |
| `reverse-rank` | worst match first, **the same set of records** | 25 | **15** | **37** |
| `one-result` | the same search cut down to one answer | 25 | 25 | 37 |
| `greedy-match` | one shared word is enough to be an answer | **36** | 32 | **43** |
| `strict-match` | every word of the question is required | 15 | 15 | 27 |

### The score cannot see the order of the answers it counts

Reverse the result list and nothing changes: the same records, the same hit@3, the same score of 37 - and
hit@1 **falls from 25 to 15**. hit@3 is a set membership question, it answers that question honestly, and
every comparison in this repository is drawn from it. So a memory server that puts the right record third
and one that puts it first score identically here, and **an agent that reads only the first result is not
being measured by that table at all.**

This is not theoretical. On corpus A, **6 of the 55 pairs reach a different verdict on hit@1 than on
hit@3**: `memdb` is separated from three subjects on hit@3 and not on hit@1, because it finds six records
and puts none of them first. Whether `memdb` is worse than `server-memory` here depends on how many
results the caller reads, which is not a property of a memory server.

### The score rewards answering, and cannot tell answering from knowing

Lower the bar to one shared word and the score goes **up**, from 37 to **43**, with hits from 25 to 36.
Raise the bar to every word and it falls to 27. The careless matcher returns records it should not, and
the twelve unanswerable questions are the only thing pushing back - it only trips five of them, because
one shared word between a question and a record is rarer than I assumed when I predicted twelve.

So the retrieval score is close to monotone in how eagerly a subject answers. A memory that retrieves
badly and never stays quiet outranks one that retrieves well and declines what it does not know, and that
is the ordering this table has been publishing. Two claims in the ledger now say so and both **FAIL**:
`score-sees-ordering` and `score-prefers-recalcitrance`.

Two of my four predictions missed, and both misses are printed beside their predictions rather than
edited out. The `reverse-rank` miss is the more interesting one: hit@1 fell to 15 and not to zero because
15 of the control's 25 correct answers come from a search that found exactly one record - there was no
ranking there to get wrong.

## What an agent actually reads

The mutation battery left a question open: the score credits the right record anywhere in the top three,
an agent reads the first one, and the score does not move when the answer moves from first to third. So
the table has one number in it and four questions behind it. `agent.py` asks all four of the same saved
rows: [`AGENT.md`](AGENT.md)

| question | right record in the top three | right record first | credits a correct silence |
|---|---|---|---|
| `score` | yes | no | yes |
| `hits` | yes | no | no |
| `hit1` | no | yes | no |
| `top` | no | yes | yes |

Twenty-four rulers - three corpora, two phrasings, four metrics - and the subject at the top is not the
same on all of them. First place, per ruler:

| metric | A written | A keywords | B written | B keywords | C written | C keywords |
|---|---|---|---|---|---|---|
| `score` | 1file | **level** | 1file | control | control | control |
| `hits` | 1file | 1file | 1file | 1file | 1file | 1file |
| `hit1` | 1file | 1file | 1file | **level** | 1file | **zenbrain** |
| `top` | 1file | **control** | **control** | **control** | **control** | **control** |

| subject | rulers at the top |
|---|---|
| `memory-mcp-1file` | **15 of 24** |
| `control` | **10 of 24** |
| `zenbrain` | **1 of 24** |

**On the only one of the four questions a caller experiences directly, the positive control wins five of
six.** The leader wins every hit@3 ruler and five of six hit@1 rulers; the score splits three to two to
one tie; and when the metric becomes *the first record back, or nothing when there is nothing*, a two
hundred line append-only file with term overlap is first on five of the six corpora and phrasings, by a
margin of four to twelve points.

That is the answer to the question this table was built to ask. A field of memory servers, eleven of them
measured, and the best of them is not better than a file.

### The score has never flattered anybody, and it has flattered everyone

Reading the rows as an agent instead of as a scorer moves every subject down or leaves it level. Nothing
gains - not one subject in three corpora - which says the score is a generous reading and never a harsh
one: `memento` loses thirteen points on corpus B, the leader ten on corpus C, `memdb` six on corpus A. A
memory that answers the question third is being given credit it does not collect from any caller.

And it is not only the totals. On corpus A as written, **9 of the 55 pairs reach a different verdict**
depending on which reading is used, and the disagreements run in both directions: `memdb` is separated
from `server-memory` on the agent reading at p = 0.000 and not on the score at p = 0.238, while
`duckdb` against `zenbrain` is separated on the score at p = 0.017 and not on the agent reading at
p = 0.175.

The ledger's `agent-agrees-with-score` claim tests the top of the table and **FAILS**: on corpus B the
subject on top changes when the metric becomes the one a caller sees.

## A second corpus, written blind

Every retrieval number in this file rests on a question set written by the same hand that wrote the
analysis. `retrieval_corpus_b.json` is a second one - 72 records and 60 questions about a fictional
railway, deliberately a different world from corpus A's ops estate - written by an author given only a
specification and told not to read this repository's corpus, matrix or results. `replicate.py` runs
every subject on both and reports the comparison to `REPLICATION.md`.

The totals are not comparable: 42 of 60 and 45 of 60 count answers to different questions. The order and
the separations are. Of the ten neighbouring pairs in the corpus A table, **five reach the same
conclusion on both corpora**. That is the honest error bar on this project's own ranking, and it is
larger than any interval in it.

Two findings from that replication are worth more than the table:

- **A score of 40/60 beat a score of 25/60 by nothing at all.** zenbrain against the positive control is
  fifteen questions to twelve, p = 0.70, on corpus A: the twelve unanswerable questions and the control's
  keyword matching cancel the recall gap. On corpus B the control wins, thirteen to two.
- **memory-lean's 14/60 was the corpus, not the subject.** It scores 0/60 on corpus B as written and
  28/60 on the same questions put as keywords, because its matching is word-based and corpus B asks
  questions. Which of those numbers is "its score" depends on who is typing.


## A third corpus, written by a different model

Every corpus in this file before today was written by the same hand and the same model family as the
analysis grading it, which makes "corpus B replicates corpus A" weaker than it reads: a shared blind spot
is indistinguishable from a finding. That limit has been open since the second corpus.

`retrieval_corpus_c.json` was written by **glm-5.3**, a different model family, through `author.py`. It
was given the band rules and a one-paragraph brief for a municipal observatory, and nothing else - no
corpus, no question from either, no result, no analysis, not even a subject name. `repair.py` then ran
the validator over what it wrote and regenerated only the failures, because a model can write a corpus
and cannot check one: the first draft had thirteen records answering two questions, six unanswerable
questions a single record actually covered, an adversarial item with nothing to compete against, and a
paraphrase that was a keyword match in disguise. After repair it passes with zero errors.

| subject | corpus A | corpus B | **corpus C** |
|---|---|---|---|
| `memory-mcp-1file` | 42 | 45 | **40** |
| `control` | 25 | 32 | **31** |
| `zenbrain` | 40 | 33 | **31** |
| `memento` | 14 | 19 | **17** |
| `mcp-duckdb-memory-server` | 12 | 13 | **12** |
| `memdb`, `memory-lean`, `server-memory` x2, `mcp-knowledge-graph`, `statecore-mcp` | 0-14 | 0-1 | **0** |

**The ranking survives an independent author: Spearman 0.78 against corpus A and 0.91 against corpus B.**
And the top three behave exactly as the score-based analysis said they would - the leader alone at
**40 of 59**, then the control and zenbrain tied at **31**. The tie is not an artefact of who wrote the
questions; it reappeared from a model that had never seen them.

What this does not settle: a different model is not a different method. It is still one prompt, one
temperature and one brief, and it still writes a synthetic world in tidy sentences. What it buys is that
no shared blind spot between author and analyst can explain the agreement.

Full table and both correlations in [`THIRD-CORPUS.md`](THIRD-CORPUS.md).
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
[`MUTANTS.md`](MUTANTS.md), CI runs the whole battery on every push, and `--only=no-forget` runs
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

## The subjects measured so far

```
$ python matrix.py

subject                         isol     ack      restart  forget   find     field    record   conc     large    ceil
---------------------------------------------------------------------------------------------------------------------
control 1.0.0                   PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS     PASS      60s
server-memory 1.0.0             PASS     PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS      60s
server-memory 2.0.0             PASS     PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS      60s
memento 0.7.0                   PASS     PASS     PASS     PASS     FAIL     PASS     PASS     PASS     FAIL     180s
memdb 1.4.0                     PASS     PASS     PASS     UNKNOWN  PASS     PASS     PASS     PASS     PASS      60s
memory-lean 1.5.0               PASS     PASS     PASS     PASS     PASS     FAIL     FAIL     PASS     PASS      60s
mcp-knowledge-graph 1.3.2       PASS     PASS     PASS     PASS     PASS     PASS     FAIL     FAIL     PASS      90s
zenbrain 0.3.0                  PASS     PASS     PASS     UNKNOWN  PASS     PASS     PASS     PASS     PASS      60s
memory-mcp-1file 0.9.2          FAIL     (PASS)   (PASS)   (UNKNOWN)  (PASS)   (UNKNOWN)  (UNKNOWN)  (FAIL)   (UNKNOWN)   60s
statecore-mcp 1.0.0             PASS     PASS     PASS     UNKNOWN  FAIL     PASS     PASS     FAIL     UNKNOWN   60s
mcp-duckdb-memory-server 1.1.10 PASS     PASS     PASS     UNKNOWN  PASS     UNKNOWN  UNKNOWN  FAIL     UNKNOWN   90s

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
efficiency. The highest retriever (`memory-mcp-1file`, 42/60 as written and 42 as keywords) is also
among the most expensive per question at 34× the size of the answer. And one marketing claim survives
measurement intact:
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


## Cost is a function of depth, and every figure above was taken at the shallow end

The cost table times a write into an empty store and a search over the 72-record retrieval corpus.
Agents store thousands over months. `growth.py` takes each subject to **3000 records inside one server
lifetime** and times the writes and the searches as the store fills.

**Every subject costs more to search when the store is large, and memento costs enormously more.**

| subject | search at 100 records | at 2000 | growth |
|---|---|---|---|
| `memento` | 43-48 ms | **6.7-8.5 s** | **x140** |
| `control` | 1.3 ms | 20.1 ms | x61 |
| `mcp-duckdb-memory-server` | 20.3 ms | 594 ms | x54 |
| `memdb` | 7.8 ms | 62 ms | x25 |
| `statecore-mcp` | 2.3 ms | 11.7 ms | x6 |
| `memory-lean`, `mcp-knowledge-graph`, `zenbrain` | ~3 ms | 9-10 ms | x3 |
| `server-memory` 1.0.0 and 2.0.0 | 1.8-2.5 ms | 6.5-6.9 ms | x3 |

memento is the one that matters. On a 72-record store a search costs 5 ms and looks free; at 2000
records it costs **six to eight seconds**, in both runs, roughly doubling for every doubling past 500.
An agent with a ten-second tool budget loses it somewhere between five hundred and a thousand memories.

**The predictions were wrong in an instructive direction.** The rewrite-on-every-write server - the
architectural choice that loses fields, and the one predicted to make writes grow - shows no clear write
growth at all: rewriting a few hundred kilobytes is cheaper than the round trip carrying the write. What
did grow was the write cost of four subjects that are not rewriting anything wholesale, by 1.7x to 2.9x
at 2000 records, three of them reproducing in both runs.

So the honest reading of the cost table is that it is **not wrong, it is shallow**. Every figure in it
describes a memory holding under a hundred records, which is what the conformance and retrieval runs use.
The ledger's `search-is-flat` claim tests the obvious extrapolation and **FAILS**.

Full tables, both runs, in [`GROWTH.md`](GROWTH.md).
## Run it on your own server

One command, no configuration, and it tells you what it could not measure:

```
$ python check.py "node my-server.js"

subject : node node_modules/mcp-knowledge-graph/dist/index.js --memory-path .
binding : discovered, proven by round-trip
attempt : 1, ceiling 60s

conformance
  isolation       PASS       store A's record was not visible from store B
  ack_readback    PASS       acknowledged alpha; a fresh read returned 1 entities: ['alpha']
  restart         PASS       three writes across three server lifetimes; read back [...]
  findable        PASS       all 8 acknowledged records came back in the top 3 for a search on their own name
  foreign_field   UNKNOWN(not-applicable)  no store is declared for this subject [...]
  foreign_record  UNKNOWN(not-applicable)  no store is declared for this subject [...]
  concurrent      FAIL       10 of 20 acknowledged writes survived two servers on one store
  large_record    UNKNOWN(not-applicable)  adapter cannot measure record content [...]
  4 kept, 3 unknown, 1 failed

retrieval (72 records, 60 questions, cold start)
  hit@3  easy 0/16  hard 0/16  adversarial 0/16  ->  all 0/60
  hit@3, the same 60 questions put as keywords          ->  all 2/60  (+2)
  questions with no answer answered anyway: 0/12 as written, 0/12 as keywords

cost
  startup 0.10s   first write 0.02s   write 0.004s   search 0.004s
  39 bytes per question (1x the size of the answer)   - bytes per record

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
written, and does the same for a delete tool - a name that looks like deletion is not a deletion, so
the candidate is called on a record this adapter wrote and kept only if the next read no longer has it.
A binding that has not been proven is never used. This reaches five of the ten probes. The rest
report UNKNOWN, either because they need to look behind the transport - `foreign_field`,
`foreign_record`, `large_record` and now `verbatim`, since a discovered binding proves which tools to
call and says nothing about where the bytes end up - or because no tool could be shown to delete a
record (`forget`).

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
a record that was just written through the server. Every probe then becomes answerable.

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
- **`verbatim` scores characters, not order.** Nine strings are compared byte for byte and the order
  they come back in is printed beside the verdict rather than judged. A subject that returns a
  record's lines sorted has kept every character and lost the sequence, and both facts are worth
  knowing; scoring that as a character failure would tell a reader the text was garbled, which is not
  what happened. The nine strings are also not every string - they cover four UTF-8 widths, a
  combining pair, right-to-left text, JSON escapes, a zero-width space and an embedded newline,
  which is where text usually breaks first, not where it always breaks.
- **The probes are not a spec.** They cover retention, deletion, concurrency, findability and one
  precondition - not retrieval quality, latency or token cost. Retrieval is measured separately
  (`retrieval.py`, and the second table in `MATRIX.md`) and reported as a score, because
  "relevant" is a judgement while "returned" is a fact.
- **`forget` is UNKNOWN for five of eleven subjects, and that is a result.** memdb, zenbrain,
  memory-mcp-1file, statecore and duckdb publish no tool that can be shown to delete one record, so the
  promise cannot be tested against them - the probe reports UNKNOWN(not-applicable) with the reason and
  never FAIL. Nobody in the field was asked to forget and kept the record. A subject that cannot be asked
  is not a subject that lied; it is a memory with no documented way to correct itself, which is worth
  knowing before you store anything you might need to take back.
- **The mutations are one author's idea of what breaks.** Eleven subjects were built to break one
  promise each and every probe failed the one aimed at it, which shows the probes have teeth; it does
  not show they would catch every defect a real memory server can have, only the ones somebody here
  thought of. Each mutant is the control's own code with one lever in it, so they inherit its shape.
  The honest count is "every probe, twelve demonstrations of failure", not "every probe, complete".
- **Cost is measured once, not repeatedly.** A single quiet pass beats a timing taken while nine
  other subjects run, and it is still not a distribution: there is no p90 on any cost column and no
  repeat. Bytes are used rather than tokens because bytes are what the transport carries and what can
  be counted exactly; a token estimate would be a guess wearing a number's clothes.
- **Retrieval is repeated three times and is deterministic.** Every subject's `runs` column is a
  single number: three complete repetitions of the experiment moved nothing. An earlier draft of this
  README blamed a 22/30 → 24/30 difference on instability (both on the then thirty-question corpus); that difference was observed across two
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
- **Every probe is run three times.** `--repeat=N` repeats all nine, reports the modal outcome,
  prints the tally, and marks any disagreement `unstable`. A tie breaks toward the worse outcome, so
  an unstable subject is never rounded up to PASS. Repeating only the probes that have been *seen* to
  flake is the assumption that has been retracted twice in this project already.
  `--repeat-probes=` narrows the list when you deliberately want to save time.

  The result of repeating all of them: **99 verdicts, 297 executions, no unstable row** in the run that
  added `forget`. The one unstable row this suite has ever recorded belonged to the subject already
  excluded for leaking state: its `restart` probe passed twice and failed once, and the evidence it
  printed contained a record written by a *different probe* in a *different store*. That flakiness is a
  downstream symptom of the isolation failure, which is the strongest argument for `isolation` first.
- **Retrieval numbers come with an interval, and the interval is the honest part.** 60 questions
  separates the ends of the table and not the middle. Every row carries a 95% Wilson interval, and
  because every subject answers the *same* 60 questions, `compare.py` runs the paired test
  (exact McNemar) that the marginal counts cannot replace:

  ```
  $ python compare.py zenbrain memory-mcp-1file
    questions                 60
    correct for both          33
    only zenbrain correct      4
    only memory-mcp-1file     10
    exact McNemar p = 0.1796  -> not separated by this corpus
  ```

  A question with no answer counts as answered correctly when the subject returns nothing, so this
  pairing prices silence: a subject that answers every unanswerable question loses those questions even
  where its recall matches.

- **The retrieval corpus is authored by this project, and a second corpus written blind says half of
  the pairwise separations do not survive it.** See `REPLICATION.md` and Addendum 13. What replicated:
  the ordering overall (rho = 0.86), the top two in their order, the four subjects at zero, and one
  subject's recall advantage concentrated in the hard band (13 of 16 on both corpora). What did not: five
  of the ten neighbouring pairs, including the second-place subject against the positive control.
  `validate_corpus.py` checks the corpus itself - unique ids, one answer per question, no unanswerable
  question covered by a record, a real competitor behind every adversarial question, and every hard
  question genuinely paraphrased rather than sharing its answer's words - and it found six defects in the
  corpus every earlier number was computed from: two hard questions that shared their answer's wording,
  six records answering two questions each, and three "adversarial" questions with nothing to compete
  against. **All six are repaired**: ten questions rewritten, no record touched, and `corpus-known.json`
  is now empty, so the next defect is a build failure rather than a table entry. The repair moved the
  ranking - the runner-up gained three questions and the leader lost one, which is the direction a
  defective corpus always leans. See Addendum 16.
- **Every question is now asked twice, and that is the point.** Corpus A's easy band is written as
  keyword strings ("access token fifteen minutes"), corpus B's as questions ("How long does an access
  token last?"). For a subject whose search matches words, that difference is worth 14 of 60 questions -
  memory-lean scores 14/60 on one and 0/60 on the other. So `retrieval.py` asks each question again with
  the meaningless words removed, in the same pass and on the same store, and `shape.py` reports the gap:
  the same question asked two ways, with the difference belonging to the server rather than to whoever
  wrote the corpus. See `SHAPE.md`.
- **`python matrix.py --report-only`** re-renders both tables from the reports already under
  `results/` without re-running a subject. A verdict is worth little if the table around it can only
  be produced by a twenty-minute run.

MIT licensed.