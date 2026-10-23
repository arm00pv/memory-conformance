#!/usr/bin/env python3
"""replicate.py - does the ordering survive a corpus this table was not built on?

A RETRIEVAL SCORE HAS TWO AUTHORS AND ONLY ONE OF THEM IS AN INSTRUMENT. The corpus decides what counts
as answering and what counts as a near miss, and it was written by the same hand that wrote the
analysis. Nothing in the pipeline could catch a question set that quietly suits the answer the table
already gives, because the questions and the table came from the same place.

The only real defence is a second corpus written by something that never saw the results, and a test
that runs the same subjects on both. This does that, and it is deliberately not a test of absolute
scores: two corpora contain different questions, so 43 of 60 and 44 of 60 are not comparable numbers.
What IS comparable is the ORDER, and the separation between neighbours in that order. Those are the
published claims. If they reproduce, the corpus was not doing the work. If they do not, it was.

  python replicate.py                 # measure corpus B where not already measured, then compare
  python replicate.py --compare-only  # read what is on disk and print the comparison
  python replicate.py --force         # re-measure corpus B even where a result exists
  python replicate.py memdb zenbrain  # by subject name

PAIRED, WITHIN A CORPUS. Every subject answers the same questions, so two subjects can be compared
question by question with an exact McNemar test, which is sharper than reading two marginal intervals
against each other - the same reason compare.py exists. Between corpora there is no pairing to exploit,
so the ordering is compared with a rank correlation and the neighbours are compared one at a time.
"""
import json
import math
import os
import sys

import compare
import matrix

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_A = "retrieval_corpus.json"
CORPUS_B = "retrieval_corpus_b.json"
SUFFIX_A = ""
SUFFIX_B = "-b"
OUT = []


def say(line=""):
    """Print a line and keep it, so the same report can be written beside MATRIX.md."""
    print(line, flush=True)
    OUT.append(line)


def mcnemar(x, y):
    """Exact two-sided McNemar: how surprising is this split of the questions the two did not tie on?"""
    k = sum(1 for a, b in zip(x, y) if a and not b)
    m = sum(1 for a, b in zip(x, y) if b and not a)
    return compare.exact_mcnemar(k, m), k, m


def ranks(values):
    """Average ranks, so ties do not invent an order that the data does not have."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(a, b):
    """Rank correlation between the two corpora's ordering of the same subjects."""
    if len(a) < 3:
        return None
    ra, rb = ranks(a), ranks(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    return None if not da or not db else num / (da * db)


def load_rows(path, corpus_path=None):
    """The saved rows, unless they were measured against a different corpus than the one on disk.

    THE INSTRUMENT CAN CHANGE UNDER A NUMBER. Edit one question in a corpus and every saved result
    silently becomes an answer to a question nobody asked any more, and nothing about the file's
    existence says so. So the saved rows are checked against the corpus they claim to be about, and a
    mismatch is treated as no measurement rather than as a measurement.
    """
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh).get("rows") or []
    if corpus_path and os.path.isfile(corpus_path):
        with open(corpus_path, encoding="utf-8") as fh:
            doc = json.load(fh)
        want = [(q.get("query"), q.get("expect"), q.get("difficulty")) for q in doc["queries"]]
        got = [(r.get("query"), r.get("expect"), r.get("difficulty")) for r in rows]
        if got != want:
            print("  STALE: %s was measured against a different %s" %
                  (os.path.basename(path), os.path.basename(corpus_path)))
            return []
    return rows


def hits(rows):
    """Per-question outcome, in corpus order, so two subjects can be paired question by question.

    IMPORTED FROM compare.py RATHER THAN REWRITTEN. The first version of this file called a question
    answered if hit@3 was true, and hit@3 is never true on an absent question - so the entire absent
    band counted as a tie and a subject that answers every unanswerable question looked identical to
    one that declines. It reported zenbrain as separated from the positive control, p = 0.002, on the
    very corpus where compare.py says p = 1.0. Two definitions of "correct" in one repository is how a
    table ends up contradicting itself, so there is now one, and it lives in compare.correct.
    """
    return [compare.correct(r) for r in rows]


def total(rows, band=None):
    sel = [r for r in rows if band is None or r.get("difficulty") == band]
    return sum(1 for r in sel if r.get("hit3")), len(sel)


def spoke(rows):
    sel = [r for r in rows if r.get("difficulty") == "absent"]
    return sum(1 for r in sel if r.get("answered")), len(sel)


def main(argv):
    os.chdir(HERE)
    compare_only = "--compare-only" in argv
    force = "--force" in argv
    argv = [a for a in argv if a not in ("--compare-only", "--force")]
    want = set(argv)
    with open("subjects.json", encoding="utf-8") as fh:
        subjects = json.load(fh)

    if not os.path.isfile(CORPUS_B):
        print("no %s - the second corpus has not been written yet" % CORPUS_B)
        return 2

    rows = []
    missing = 0
    for entry in subjects:
        if want and entry["name"] not in want:
            continue
        label = "%s %s" % (entry["name"], entry["version"])
        slug = matrix.slug_of(entry)
        path_b = os.path.join("results", slug + "-retrieval" + SUFFIX_B + ".json")
        if not compare_only and (force or not load_rows(path_b, CORPUS_B)):
            print("measuring %s on %s ..." % (label, CORPUS_B), flush=True)
            matrix.run_retrieval(entry, int(entry.get("timeout", 60)), cases=CORPUS_B,
                                 suffix=SUFFIX_B)
        a = load_rows(os.path.join("results", slug + "-retrieval" + SUFFIX_A + ".json"), CORPUS_A)
        b = load_rows(path_b, CORPUS_B)
        if not b:
            print("  no corpus-B result for %s" % label)
            missing += 1
        rows.append((label, a, b))

    have = [r for r in rows if r[1] and r[2]]
    if not have:
        print("nothing measured on both corpora")
        return 1

    with open(CORPUS_B, encoding="utf-8") as fh:
        n_rec = len(json.load(fh)["records"])

    say("# Replication on a corpus written blind")
    say()
    say("%d subjects, the same conformance harness, two question sets of %d records each. Corpus B was"
        % (len(have), n_rec))
    say("written by an author that never saw corpus A, the matrix or any result. The two totals below")
    say("are NOT comparable as numbers - they count answers to different questions. The order is.")
    say()
    scores = [(label, total(a), total(b), a, b) for label, a, b in have]
    W = max([24] + [len(label) for label, _x, _y, _a, _b in scores])
    say("| %-*s | A hit@3 | B hit@3 | B easy | B hard | B adversarial | B no-answer spoken |" % (
        W, "subject"))
    say("|" + "---|" * 7)
    for label, (ka, na), (kb, nb), a, b in scores:
        cells = []
        for band in ("easy", "hard", "adversarial"):
            k, n = total(b, band)
            cells.append("%d/%d" % (k, n))
        sp, sn = spoke(b)
        say("| %-*s | %d/%d | **%d/%d** | %s | %s | %s | %d/%d |" % (
            W, label, ka, na, kb, nb, cells[0], cells[1], cells[2], sp, sn))

    by_a = sorted(scores, key=lambda s: -s[1][0])
    by_b = sorted(scores, key=lambda s: -s[2][0])
    rho = spearman([s[1][0] for s in scores], [s[2][0] for s in scores])
    pos_a = {s[0]: i + 1 for i, s in enumerate(by_a)}
    pos_b = {s[0]: i + 1 for i, s in enumerate(by_b)}
    say()
    say("Rank correlation between the two orderings: **%s** over %d subjects."
        % ("n/a" if rho is None else "rho = %.2f" % rho, len(scores)))
    say()
    say("| %-*s | rank A | rank B | move |" % (W, "subject"))
    say("|---|---|---|---|")
    for label, _ka, _kb, _a, _b in scores:
        move = pos_a[label] - pos_b[label]
        say("| %-*s | %d | %d | %s |" % (W, label, pos_a[label], pos_b[label],
                                       "same" if move == 0 else ("%+d" % move)))

    # --- the claims, which are about neighbours ----------------------------
    # A TABLE'S REAL CLAIMS ARE ALL ADJACENT PAIRS. "A is above B" is asserted by every pair that ends
    # up next to each other, and those are exactly the pairs where the published table either
    # separates them or says it cannot. So the neighbours are tested one at a time on both corpora
    # rather than picking the comparisons after the fact.
    say()
    say("## Every neighbouring pair, tested on both corpora")
    say()
    say("Exact McNemar on the questions where the two subjects disagree; the split is questions the")
    say("first subject answered and the second did not. A question counts as answered correctly the")
    say("same way compare.py counts it: the right record in the top three, and on a question with no")
    say("answer, silence. sep is p < 0.05.")
    say()
    say("| pair | corpus A | corpus B | same conclusion |")
    say("|---|---|---|---|")
    agree = disagree = 0
    for i in range(len(by_a) - 1):
        l1, _k1, _m1, a1, b1 = by_a[i]
        l2, _k2, _m2, a2, b2 = by_a[i + 1]
        pa, xa, ya = mcnemar(hits(a1), hits(a2))
        pb, xb, yb = mcnemar(hits(b1), hits(b2))
        sa = "sep" if pa < 0.05 else "not"
        sb = "sep" if pb < 0.05 else "not"
        ok = sa == sb
        agree += ok
        disagree += not ok
        say("| %s / %s | %.3f (%d-%d) %s | %.3f (%d-%d) %s | %s |" % (
            l1, l2, pa, xa, ya, sa, pb, xb, yb, sb, "yes" if ok else "**no**"))
    say()
    say("%d of %d neighbouring pairs reach the same conclusion on both corpora." %
        (agree, agree + disagree))
    if disagree:
        say()
        say("A pair that changes conclusion is the corpus talking, not the subjects. A separation")
        say("that holds on only one of two question sets is conditional on that question set, and")
        say("should be read that way until a third corpus agrees.")
    if missing:
        say()
        say("%d subject(s) have no corpus-B measurement and are left out of every comparison above."
            % missing)

    with open("REPLICATION.md", "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(OUT) + chr(10))
    print()
    print("written to REPLICATION.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
