# What comes back besides the answer

Moved here from `README.md` unchanged, so that page can stay an argument rather
than an archive. The numbers are the same numbers; the generated reports they quote are still
at the top of the repository.

## What comes back besides the answer

Every number above counts whether the right record arrived. **None of them counts what arrived with it.** A
top-three list carrying the answer and two unrelated records scores exactly what a list carrying the answer
alone scores, so a subject that answers more questions by handing back more records is paid for the hit and
never charged for the volume. `precision.py` charges it, from rows that were already on disk — no subject
was asked twice. [`PRECISION.md`](../PRECISION.md)

Three readings, and the first of them needs no rule at all.

### The silence bill

On a question whose answer is nothing, every record handed back is junk **by construction** — there is nothing
for it to be. Five corpora carry such a band, 147 questions in all, 99 of them the long exam's.

| subject | unanswerable questions answered | records handed back | characters |
|---|---|---|---|
| `memento` | **147 of 147** | 441 | 47,985 |
| `zenbrain` | **147 of 147** | 439 | 47,310 |
| `memdb` | 145 of 147 | 435 | **59,264** |
| `memory-mcp-1file` | 141 of 147 | 410 | 41,498 |
| `mcp-duckdb-memory-server` | 18 of 147 | 34 | 3,495 |
| `memory-lean` | 13 of 147 | 14 | 1,500 |
| `statecore-mcp` | 12 of 147 | 12 | 720 |
| `control` | 8 of 147 | 10 | 980 |
| `server-memory` ×2, `mcp-knowledge-graph` | **0 of 147** | 0 | 0 |

**Two subjects answer every unanswerable question, three answer none, and six answer part of the band** — and
that last group is the finding. `items.py` reported that every subject either declines all twelve
unanswerable questions or none of them, which made the twelve points a *habit*. Read at ten times the sample
the habit becomes a **threshold**: the subjects that decide per question answer 15 of 336 on the four short
bands and **36 of 99 on the long exam**.

The reason is the corpus, not the subject. Every one of those 36 answers landed on a question that shares a
word with a stored record, and no subject that decides per question ever answered a question whose words
appear nowhere in the store — with one exception, `statecore-mcp`, which hands back a record for all sixty
questions on corpus A and so has no threshold there to fail. **The twelve points are neither a virtue nor a
habit. They are the price of a clean band, and the same subject pays a different price on a different
corpus.**

### Junk around the answer

All nine corpora, both phrasings, every returned record that was not the expected one, split mechanically
into near misses — same family, one word off, which is what a top-three list is for — and noise.

| subject | answered | correct | records back | near | **noise** | noise per correct | answer share |
|---|---|---|---|---|---|---|---|
| `memdb` | 711 | 14 | 2,128 | 33 | **2,075** | 148.21 | 1% |
| `memento` | 711 | 326 | 2,133 | 625 | **1,169** | 3.59 | 15% |
| `zenbrain` | 711 | 666 | 2,125 | 675 | **765** | 1.15 | 31% |
| `memory-mcp-1file` | 704 | 664 | 2,069 | 715 | **674** | 1.02 | 32% |
| `control` | 635 | 625 | 1,208 | 489 | **75** | 0.12 | 52% |
| `memory-lean` | 489 | 464 | 711 | 223 | **23** | 0.05 | 65% |
| `server-memory` ×2 | 238 | 232 | 331 | 99 | **0** | 0.00 | 72% |

`memento` answers 326 questions correctly and hands back **1,169 records nobody asked for**; the control
answers 625 and hands back 75. The score separates them in no published table, and they are not the same
thing. Per question the reading bill runs from **4 characters** (`statecore-mcp`) to **401** (`memdb`),
against a control at 151.

### Does the score charge for this

Every adapter whose verdict this repository publishes, on corpus A, read through the same lens:

| adapter | what it is | score, written | noise per correct | answer share |
|---|---|---|---|---|
| `oracle-search` | search knows the answer | 60 of 60 | 0.00 | 100% |
| `greedy-match` | mutant: answers anything | **43 of 60** | **1.86** | 28% |
| `control` | positive control | 37 of 60 | 0.32 | 63% |
| `one-result` | mutant: one record only | 37 of 60 | 0.04 | 93% |
| `strict-match` | mutant: exact words only | 27 of 60 | **0.00** | 100% |
| `mute-search` | returns nothing, ever | 12 of 60 | — | — |
| `blind-search` | one shared word | 2 of 60 | **69.00** | 1% |

**The tidiest adapter on the shelf is `strict-match` — no noise at all, every character it hands back part
of an answer — and it scores 27 of 60. The mutant built to answer anything, `greedy-match`, scores 43, six
points above the positive control, while carrying 1.86 noise records per correct answer.** The score cannot
tell those two apart as different kinds of thing. This column can. The ledger's `noise-is-charged` claim
**FAILS**.

`blind-search` is the extreme, and it shows what the axis measures: it answered every question it was
given - the answerable ones and the twelve with no answer - handed back 144 records, got 2 right, and
**138 of the rest share neither a name nor three words with what was asked for.** Its score is 2.

### What the exam actually asks

The precision axis found something about the exam that nothing had checked. `validate_corpus.py` had never
been pointed at `large_corpus.json`; it now has an `--exam` mode for the three rules an exam
legitimately breaks — band names, one record asked at several distances, more than one right answer — and
under it the exam is charged with **12 duplicated questions and 8 questions half covered by one record**.
The first twelve are fixed; the second eight are not defects, and the difference between the two is the
finding.

- **300 slots for 288 distinct questions**, every one of the 24 surplus slots a question two records answer
  equally. Those are dropped at build time now: `questions.py` holds the rule, the exam is 276 questions,
  and the four generated corpora lost 54 slots between them. A subject that returned the sibling used to be
  graded wrong for being right, and the exam's totals understated two of the eleven.
- **The 8 absent charges are word-overlap alarms, not unlabelled answers.** `obliterator` is not a path
  library. What the rule detects is that a word-overlap matcher will answer the question, and the positive
  control answered exactly those. **A checker and a subject that share one idea cannot check each other**,
  which is why the absence of a semantic check is stated in `PRECISION.md` instead of being implied away.

The eight absent charges stay pinned in `corpus-known.json` — a new defect fails the build, a pinned one that
stops happening is reported as drift — and `python questions.py` now runs in CI, so a corpus that asks a
question twice fails the build instead of quietly becoming the sample size.

`silence-is-a-habit`, `exam-questions-distinct` and `noise-is-charged` all **FAIL** in the ledger,
on all four settings. Three claims added, and none of them survived contact.
