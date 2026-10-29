# The question sets

Moved here from `README.md` unchanged, so that page can stay an argument rather
than an archive. The numbers are the same numbers; the generated reports they quote are still
at the top of the repository.

## A corpus with no author

Every question set above was written by somebody: by the analyst, by a different model, by hand to a
specification. The limit that has been open since the second corpus is that agreement between corpora
written by the same hand proves less than it looks. `retrieval_corpus_real.json` answers it by removing
the author instead of replacing him. [`REAL-CORPUS.md`](../REAL-CORPUS.md)

The records are the **real `package.json` files installed under `node_modules`** - 397 packages with a
usable description, 72 kept by a fixed stride, 325 left out. The questions are derived from those
descriptions by a rule applied without judgement: sixteen verbatim, sixteen with every third long word
removed, sixteen about packages that share three or more long words with another record in the store, and
twelve about **real packages that were left out**. Nobody chose a question, and nothing in the corpus was
written by anyone who knew the answer.

### The five subjects that answered nothing, answered

| subject | corpus A | corpus B | corpus C | **real text** |
|---|---|---|---|---|
| `control` | 37 | 44 | 43 | **60** |
| `memory-lean` | 26 | 12 | 12 | **59** |
| `mcp-duckdb-memory-server` | 24 | 25 | 23 | **59** |
| `zenbrain` | 40 | 33 | 31 | 48 |
| `memory-mcp-1file` | 43 | 45 | 40 | 48 |
| `mcp-knowledge-graph` | 12 | 12 | 12 | **45** |
| `server-memory` 1.0.0 and 2.0.0 | 12 | 12 | 12 | **45** |
| `memento` | 14 | 19 | 17 | 23 |
| `statecore-mcp` | 0 | 12 | 12 | 12 |
| `memdb` | 6 | 2 | 0 | 0 |

The columns are the **score as written**, which is why the last one is 48 and not the 47 the same
subject reaches with the words stripped: this table was a hand-copy, and that single cell was the
keyword figure sitting in a written column for as long as nobody checked a cell instead of a
sentence. `figures.py` checks every cell of it now.

On the three authored corpora, five subjects answer no answerable question at all and score exactly the
twelve points for declining. On real text they answer **33 of 48**; `memory-lean`, near the floor
everywhere else at 12 to 26, scores **59 of 60**; and **the positive control scores 60 of 60**, which is
the ceiling this repository measured against the answer key, reached by a file that appends lines.

Nothing about those subjects changed. What changed is the question: the authored corpora paraphrase
("how many retries…"), and the real corpus asks with the record's own words. A word matcher is worthless
against a paraphrase and excellent against a near-quote, and the previous table was measuring the first
while being read as a measure of memory.

The rank correlation with corpus A is 0.78 on the score, which sounds reassuring until it is put beside
**B vs C, which is 0.909**: two corpora written by different authors about different worlds agree more
than either agrees with real text. Against B it is 0.63 and against C 0.66.

All three read one to two hundredths higher in the copy that stood here - 0.80, 0.64, 0.68 - and this
page has now been wrong in that way three times. The argument never noticed because it only needs the
three ordered, and a rank correlation is exactly the kind of number that moves when one subject is
re-measured: the ranks shift, the ordering mostly does not. `figures.py` pins all four now.

### The corpus cannot test paraphrase, and it says so

`validate_corpus.py` **fails** this corpus, and the right thing to do with that is publish it. All
sixteen hard questions still share more than half their long words with the record that answers them,
because removing every third word from a real sentence leaves a sentence a substring counter can answer.

That is the limit of a corpus with no author, stated precisely: **real records are free and real questions
are nearly free, but a paraphrased band needs somebody to paraphrase.** The easy, adversarial and absent
bands are real tests; the hard band is a keyword band wearing the name, and the one finding above is what
that distinction costs.

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

Full table and both correlations in [`THIRD-CORPUS.md`](../THIRD-CORPUS.md).

## How much paraphrase does a memory survive

The four corpora disagree, and the disagreement turned out to be one axis rather than four question sets:
how far a question sits from the text that answers it. `distance_sweep.py` walks that axis on one fixed
set of real records - each record asked with a third, then a half, then two thirds of its words taken
away, down to two words and a question frame. [`DISTANCE.md`](../DISTANCE.md)

| band | the question keeps | of the record's long words, **measured** |
|---|---|---|
| d0 | every word | 1.00 |
| d1 | two of every three | 0.71 |
| d2 | every second | 0.56 |
| d3 | one in three | 0.33 |
| d4 | the first two, in a question | 0.33 |

hit@3 out of the questions in each band, 24 per band and 16 at d4:

| subject | d0 | d1 | d2 | d3 | d4 | half at |
|---|---|---|---|---|---|---|
| `control` | 24 | 24 | 24 | 23 | 9 | d3 |
| `zenbrain` | 24 | 24 | 24 | 23 | **16** | d4 |
| `memory-mcp-1file` | 24 | 24 | 22 | 20 | 15 | d4 |
| `memory-lean` | 24 | 24 | 24 | 23 | **0** | d3 |
| `mcp-duckdb-memory-server` | 24 | 24 | **13** | **3** | 8 | d2 |
| `server-memory` 1.0.0 and 2.0.0 | 24 | **0** | 0 | 1 | 0 | d0 |
| `mcp-knowledge-graph` | 24 | **0** | 0 | 1 | 0 | d0 |
| `memento` | 11 | 12 | 14 | 12 | 11 | - |
| `memdb` | 0 | 0 | 0 | 1 | 0 | - |
| `statecore-mcp` | 0 | 0 | 0 | 0 | 0 | - |

**The subjects do not differ in quality; they differ in shape.** Three of them drop from a perfect 24 to
**zero** when a third of the words are removed - they are exact-match engines, and their total failure on
the authored corpora and their strong showing on real text are the same fact seen from two distances.
Three hold most of the way and then fall. `memento` is flat and low at every distance, which is not a
paraphrase problem at all. And `duckdb` is **not monotone** - 24, 24, 13, 3, then back up to 8 of 16 - because a
two-word query is a keyword query and it does better with less text than with the middle of a sentence.

### Where each corpus actually sat

Two coordinates, measured the same way on every question set here: how much of the answering record
survives into the question, and how much of the question is drawn from the record.

| corpus | of the record, in the question | of the question, in the record |
|---|---|---|
| A | 0.29 | 0.50 |
| B | 0.33 | 0.57 |
| C | 0.22 | 0.60 |
| real | 0.71 | **1.00** |

Every authored corpus sits at the far end on **both** coordinates and the real one sits at the near end on
both. That is the entire disagreement of the last phase, and it also means the sweep is the easy half of
the space: every band in it is still a question made from the record's own words, which is a thing no
person has ever asked.

### An easier question is not a weaker instrument, it is one with no room at the top

| band | pairs separated |
|---|---|
| d0 | **26 of 55** |
| d1 | 35 of 55 |
| d2 | **38 of 55** |
| d3 | 34 of 55 |
| d4 | 33 of 55 |

The verbatim band separates **fewer** pairs than the middle of the ladder, because eight subjects tie at
24 of 24 and a tie separates nobody. That is exactly what happened to the real corpus, where four subjects
tied at 48 hits and the leader had to be decided by a single point.

The ledger tests both readings and both **FAIL**: `ranking-survives-paraphrase` (eight subjects tie
verbatim, `zenbrain` is first when two words survive) and `near-end-separates` (26 against 38).

## Does a memory survive a plural

The distance ladder moves one coordinate — how much of a record survives into a question — and it is
pinned at 1.00 on the other, because a question built by deleting words uses only the record's own words.
**A person does not ask that way.** `morph_sweep.py` moves the other coordinate: every description asked
four times with a growing share of its long words pluralised, so the question contains vocabulary the
record does not. [`MORPHOLOGY.md`](../MORPHOLOGY.md)

| band | the question | vocabulary the record lacks, **measured** |
|---|---|---|
| m0 | the record's own words | 0.00 |
| m1 | every fourth long word pluralised | 0.14 |
| m2 | every second long word pluralised | 0.38 |
| m3 | every long word pluralised | 0.83 |

hit@3 out of 20 questions per band:

| subject | m0 | m1 | m2 | m3 |
|---|---|---|---|---|
| `mcp-duckdb-memory-server` | 20 | 20 | 20 | **20** |
| `memory-mcp-1file` | 19 | 19 | 19 | **19** |
| `zenbrain` | 20 | 20 | 20 | **15** |
| `memento` | 12 | 12 | 14 | 14 |
| `control` | 20 | 20 | 20 | **9** |
| `server-memory` 1.0.0 and 2.0.0 | 20 | **0** | 0 | 0 |
| `mcp-knowledge-graph` | 20 | **0** | 0 | 0 |
| `memory-lean` | 20 | **1** | 0 | 0 |

**Changing two letters on one word in four is enough to erase four subjects completely.** `server-memory`,
`mcp-knowledge-graph` and `memory-lean` go from a perfect 20 at m0 to zero at m1 — they match substrings and
nothing else. `duckdb` and the leader hold all the way, `zenbrain` loses a quarter, and the positive
control — which is also a substring matcher — survives m2 and falls to nine at m3.

That is the same family split the distance sweep found, arrived at from the other direction: the subjects
that fail a paraphrase at *d1* are the subjects that fail a plural at *m1*, and they are the ones whose
retrieval is a string comparison.

### The two coordinates

| sweep | of the record, in the question | of the question, in the record |
|---|---|---|
| distance, d0 to d4 | 1.00 down to 0.29 | **1.00 at every band** |
| morphology, m0 to m3 | **1.00 at every band** | 1.00 down to 0.18 |

Neither sweep alone is what a person writes, and the two failure modes they isolate are different: losing
the record's words is a recall problem, using only the record's own words is a normalisation problem. A
real question changes both at once, which is why a field of this many servers produces this much spread —
and why a benchmark that holds one coordinate fixed measures one failure and calls it quality.

`plural-is-free` joins the ledger and **FAILS**: five of eleven subjects lose more than half their answers
when the question pluralises the record's words.

## Questions with more than one right answer

Every question in this repository has had one answer — a query names a record, the subject returns a list,
and the scoring asks whether the right id is in the first three. That makes every question a lookup, and a
memory store is asked joins as often as lookups. `multi_query.py` builds the other kind from real data and
no author: records whose descriptions share four or more long words are gathered into a **cluster**, and
each cluster becomes one question whose required answer is the whole cluster.
[`MULTI-RECORD.md`](../MULTI-RECORD.md)

The store is 72 records with 16 cluster questions beside 16 single-record ones, so the two kinds are
compared within one run. Scored by required-set recall — how much of the required set came back.

| subject | clusters fully answered | required-set recall | single questions, hit@3 |
|---|---|---|---|
| `control` | **16 of 16** | 1.00 | 16 of 16 |
| `zenbrain` | **16 of 16** | 1.00 | 16 of 16 |
| `memory-mcp-1file` | 11 of 16 | 0.76 | 16 of 16 |
| `memento` | 9 of 16 | 0.65 | 10 of 16 |
| `memdb` | 3 of 16 | 0.25 | 0 of 16 |
| `mcp-duckdb-memory-server` | **0 of 16** | 0.06 | **16 of 16** |
| `memory-lean` | **0 of 16** | 0.03 | **16 of 16** |
| `server-memory` 1.0.0 and 2.0.0 | **0 of 16** | 0.00 | **16 of 16** |
| `mcp-knowledge-graph` | **0 of 16** | 0.00 | **16 of 16** |
| `statecore-mcp` | **0 of 16** | 0.00 | 0 of 16 |

**Two subjects answer every cluster in full; six answer none of them — and five of those six answer every
single-record question on the same store.** So the difference is not retrieval quality. It is whether
returning a set is something the subject does at all: a search that answers with one id and stops cannot
answer a question whose answer is three. Every metric this repository has published would have described
those five as competent retrievers on the strength of the single-record column.

Where a subject does return part of a set, the single-record metric overcounts: `memento` is scored 12 of
16 that way against 9 answered in full. The ledger's `set-answers` claim **FAILS** for six subjects.

One finding arrived before the measurement did: the store had to be **capped at 300 characters per record**
because `memory-lean` refuses anything longer — "observations over 300 chars or not strings" — and the run
never starts. A documented limit of that subject, and a real constraint on any corpus a store like it could
ever ingest.

## Does a memory know which version of a fact is current

Every corpus here asks about a record that does not change. A memory store is not used that way: a fact is
written, then rewritten, and the first thing its owner needs is the current value rather than the one it
replaced. `restart` and `forget` cover a record that is **deleted**; nothing covered a record that is
**superseded**, which is the ordinary case. [`SUPERSESSION.md`](../SUPERSESSION.md)

Every chosen package record is stored twice, as two records differing only in the version string in the
body, and each question asks with the description both carry. The current answer is the later record.

| subject | current, alone | stale, alone | both returned | **current first** |
|---|---|---|---|---|
| `zenbrain` | 3 | 0 | 63 | **52 of 66** |
| `memory-mcp-1file` | 0 | 0 | 66 | **28 of 66** |
| `control`, `duckdb`, `memory-lean`, `mcp-knowledge-graph`, `server-memory` ×2 | 0 | 0 | 66 | **0 of 66** |
| `memento` | 0 | 13 | 18 | **0 of 66** |
| `memdb`, `statecore-mcp` | 0 | 0 | 0 | **0 of 66** |

**Nine of the eleven subjects never put the current record first — not once in sixty-six questions.**
They return *both* versions nearly every time and rank the **superseded one ahead of the one that replaced
it**, because the two bodies are almost identical and nothing in either says which is later. An agent
reading a single result reads the fact that was replaced.

Across the whole table 13 answers came from the superseded record alone and 543 returned both. `zenbrain`
is the only subject with a recency preference worth the name, and it gets it right about three times in
four. The ledger's `recency-visible` claim **FAILS** for nine of eleven.

## The price of a longer exam, paid once

`band.py` has been quoting prices for three phases — 371 questions for the leader against the control, 679
against zenbrain, 11,825 on corpus B — and none of them had ever been paid, so the arithmetic had never
been checked against an experiment. `exam_size.py` pays one of them at a little over four times the size.
[`EXAM-SIZE.md`](../EXAM-SIZE.md)

**The store is identical to the sixty-question authorless corpus.** Same 72 real records, already ingested;
only the question count changes — each record asked verbatim, with a third of its words gone, and with half
of them gone, plus a drawn absent band.

| subject | 276 questions | 60 questions |
|---|---|---|
| `control` | **268 of 276** | 60 of 60 |
| `memory-lean` | **264 of 276** | 59 of 60 |
| `mcp-duckdb-memory-server` | **231 of 276** | 59 of 60 |
| `zenbrain` | **178 of 276** | 48 of 60 |
| `memory-mcp-1file` | **178 of 276** | 48 of 60 |
| `mcp-knowledge-graph`, `server-memory` ×2 | **160 of 276** | 45 of 60 |
| `statecore-mcp` | **98 of 276** | 12 of 60 |
| `memento` | **72 of 276** | 23 of 60 |
| `memdb` | **2 of 276** | 0 of 60 |

| exam | pairs separated |
|---|---|
| 60 questions | **41 of 55** |
| 276 questions | **43 of 55** |

**Two pairs that were ties became separations**, both at p = 0.000: `control` against `duckdb`, and `duckdb`
against `memory-lean`. That is the power analysis working as advertised — those pairs had a real difference
and the short exam could not see it. It is fewer than the eight the first version of this exam found, and the
next paragraph says why.

**And the prediction that mattered was that one tie would survive.** `control` against `memory-lean` was
1-0 in sixty and is **11-7 in 276** — exact p = 0.48. The longer exam did not break it, which is what a price
of a few hundred questions predicts: the exam grew, the margin did not. All three predictions written before
the run held.

**The exam was 300 slots for 288 distinct questions, and 24 of those slots were not fair questions.** Two
packages can carry the same description word for word — a fork and its original, a client and a server
generated from one template — so the same words were asked twice with a different expected record, and a
subject returning the other one of the two was graded wrong for being right. `questions.py` now holds the
rule that drops every copy of a question two records answer equally. The four generated corpora were rebuilt
with it and lost 54 slots between them, the exam 24, and **no subject was re-measured**: a retained question
is byte-identical to the one already asked, so its rows stand, and the rows measured against a dropped
question are excluded from every count rather than rescued.

Honesty about what this costs: **three questions about one record are not three independent draws**, so the
exam carries less than 276 questions' worth of information. A larger store was tried first and abandoned —
at 282 records the control alone needed nine minutes for three hundred questions, because it reads the whole
store on every search. Correlated questions make separation *harder*, so a tie broken here is real evidence
and a tie that survives here is weaker evidence than 276 suggests.

The ledger's `longer-exam` claim **HOLDS**, and it took a correction to get there: its sentence said a longer
exam "changes which pairs the corpus can separate" while its code reported the opposite — true only when
nothing changed — so for two phases it printed the word FAILS beside a measurement that satisfied its own
wording. Sentence and code now agree on the reading the reports publish: more questions separate the pairs
the short exam could not, and unsay no separation the short one found.
