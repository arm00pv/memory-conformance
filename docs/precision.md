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
for it to be. Five corpora carry such a band, 146 questions in all, 98 of them the long exam's.

| subject | unanswerable questions answered | records handed back | characters |
|---|---|---|---|
| `memento` | **146 of 146** | 438 | 47,678 |
| `control` | 8 of 146 | 10 | 980 |

The whole table is generated in [`PRECISION.md`](../PRECISION.md) - these are the two rows the
argument turns on, and every number copied onto this page is now pinned to the results it came
from by `figures.py`. **This page carried the old copy for four phases**: 147 where the band held
146, and eleven subject rows that no longer matched anything, because a hand-copied table has no
connection a build can break.

**Two subjects answer every unanswerable question, three answer none, and six answer part of the band** — and
that last group is the finding. `items.py` reported that every subject either declines all twelve
unanswerable questions or none of them, which made the twelve points a *habit*. Read at ten times the sample
the habit becomes a **threshold**: the subjects that decide per question answer 15 of 336 on the four short
bands and **36 of 686 on the long exam** - the same 15-and-36 the old copy reported, against denominators
that were one subject wide where they should have been seven.

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
| `memdb` | 659 | 12 | 1972 | 29 | **1925** | 160.42 | 1% |
| `memento` | 659 | 294 | 1977 | 555 | **1115** | 3.79 | 14% |
| `control` | 589 | 585 | 1098 | 419 | **75** | 0.13 | 54% |

Three rows out of ten, and the same note as the table above: the full one is generated in
[`PRECISION.md`](../PRECISION.md). Every figure in this copy was stale when the pin was written -
`memento` at 326 correct rather than 294, the control at 625 rather than 585 - because the corpora
kept being repaired and this page kept its copy.

`memento` answers 294 questions correctly and hands back **1115 records nobody asked for**; the control
answers 585 and hands back 75. The score separates them in no published table, and they are not the same
thing. Per question the reading bill runs from **4 characters** (`statecore-mcp`) to **403** (`memdb`),
against a control at 147.

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
- **The 8 absent charges were word-overlap alarms, not unlabelled answers** — and this reading changed the
  rule that made them. `obliterator` is not a path library. What the validator could see was that a
  word-overlap matcher would answer the question, and the positive control answered exactly those eight,
  because the control is one. **A checker and a subject that share one idea cannot check each other**, so
  the charge is gone: the rule now charges only a question that shares most of *each other's* words with one
  record — that record in disguise — and merely prints a question that sits half inside a record, with the
  fraction. Nine corpora, zero copies found, and a planted one is charged, in CI, because a check that has
  never been seen firing is not a check.

`python questions.py` now runs in CI, so a corpus that asks a question twice fails the build instead of
quietly becoming the sample size, and the exam passes its own validator with no errors and eight
neighbours printed.

`silence-is-a-habit`, `exam-questions-distinct` and `noise-is-charged` all **FAIL** in the ledger,
on all four settings. Three claims added, and none of them survived contact.
