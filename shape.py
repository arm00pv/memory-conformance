#!/usr/bin/env python3
"""shape.py - does the server need you to guess its keywords?

A SCORE COMPUTED FROM ONE PHRASING MEASURES THE PHRASING AS MUCH AS THE SERVER. Corpus B proved it by
accident: memory-lean scored 14/60 on corpus A and 0/60 on corpus B, and a six-query controlled test
showed why - it matches words, corpus A's easy band is written as word strings and corpus B's as
questions. Nothing in that difference was about memory-lean's ranking.

The fix is not another corpus, because an author's phrasing is always in the corpus. It is to ask each
question twice in the same pass: once as written, once with the words that carry no meaning taken out.
The second form is derived by words.keyword_form from the first, so it is identical for every subject
and has no author in it. The gap between the two answers is then a property of the server - how much of
its score depends on being asked the way a search box would have asked.

  python shape.py --measure   # re-measure every subject, both corpora, with the shape axis on
  python shape.py             # read what is on disk and print the comparison

A subject that scores the same both ways is phrasing-independent. A subject that scores well on one
form and badly on the other has told you exactly which kind of question it can be asked, which is the
thing a user needs to know and a single hit@3 number throws away.
"""
import json
import os
import sys

import compare
import matrix

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_A = "retrieval_corpus.json"
CORPUS_B = "retrieval_corpus_b.json"
BANDS3 = ("easy", "hard", "adversarial")
OUT = []


def say(line=""):
    print(line, flush=True)
    OUT.append(line)


def ok(row, shape):
    """Correct, using compare.py's definition, read from whichever phrasing is being scored.

    ONE DEFINITION OF CORRECT, AGAIN. A question with no answer counts as answered correctly when the
    subject returned nothing, and compare.correct already says so; this only chooses which phrasing's
    outcome to feed it.
    """
    if shape == "written":
        return compare.correct(row)
    return compare.correct({"difficulty": row["difficulty"],
                             "answered": bool(row.get("answered_keyword")),
                             "hit3": bool(row.get("hit3_keyword"))})


def has_shapes(rows):
    return bool(rows) and all("hit3_keyword" in r for r in rows)


def totals(rows, shape):
    out = {}
    for band in BANDS3 + ("absent", "all"):
        sel = [r for r in rows if band == "all" or r.get("difficulty") == band]
        out[band] = (sum(1 for r in sel if ok(r, shape)), len(sel))
    return out


def load(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("rows") or []


def measure(subjects, want, force):
    for entry in subjects:
        if want and entry["name"] not in want:
            continue
        slug = matrix.slug_of(entry)
        label = "%s %s" % (entry["name"], entry["version"])
        for cases, suffix in ((None, ""), (CORPUS_B, "-b")):
            path = os.path.join("results", slug + "-retrieval" + suffix + ".json")
            if not force and has_shapes(load(path)):
                continue
            print("measuring %s on %s (both shapes) ..."
                  % (label, os.path.basename(cases or CORPUS_A)), flush=True)
            matrix.run_retrieval(entry, int(entry.get("timeout", 60)), cases=cases,
                                 suffix=suffix)


def ranks(values):
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
    if len(a) < 3:
        return None
    ra, rb = ranks(a), ranks(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    return None if not da or not db else num / (da * db)


def main(argv):
    os.chdir(HERE)
    want = set(a for a in argv if not a.startswith("--"))
    rerun = "--measure" in argv or "--force" in argv
    with open("subjects.json", encoding="utf-8") as fh:
        subjects = json.load(fh)
    if rerun:
        measure(subjects, want, "--force" in argv)

    say("# The same question, asked two ways")
    say()
    say("Each question is put to every subject twice in one pass: as written, and as the same words with")
    say("the words that carry no meaning removed. The second form is derived mechanically, so it is the")
    say("same for everybody and has no author's vocabulary in it.")
    say()
    say("The totals are CORRECT ANSWERS, the metric the paired test in compare.py pairs on: the right")
    say("record in the top three, or silence on a question that has no answer. They are therefore not the")
    say("same as MATRIX.md's hit@3 column, which counts hits only - a subject that finds nothing but")
    say("declines all twelve unanswerable questions scores 12 here and 0 there. The easy, hard and")
    say("adversarial columns count hits only, so a +1 there and a +0 in the total is the absent band")
    say()

    for corpus, suffix in ((CORPUS_A, ""), (CORPUS_B, "-b")):
        table = []
        for entry in subjects:
            if want and entry["name"] not in want:
                continue
            label = "%s %s" % (entry["name"], entry["version"])
            rows = load(os.path.join("results",
                                     matrix.slug_of(entry) + "-retrieval" + suffix + ".json"))
            if not has_shapes(rows):
                continue
            table.append((label, rows, totals(rows, "written"), totals(rows, "keyword")))
        if not table:
            say("no measurement with the shape axis for %s - run python shape.py --measure" % corpus)
            say()
            continue
        say("## %s" % corpus)
        say()
        W = max([26] + [len(t[0]) for t in table])
        say("| %-*s | as written | as keywords | change | easy | hard | adversarial |"
            % (W, "subject"))
        say("|---|---|---|---|---|---|---|")
        moved = 0
        for label, _rows, w, kw in table:
            change = kw["all"][0] - w["all"][0]
            if change:
                moved += 1
            say("| %-*s | %d/%d | **%d/%d** | %+d | %s |" % (
                W, label, w["all"][0], w["all"][1], kw["all"][0], kw["all"][1], change,
                " | ".join("%+d" % (kw[b][0] - w[b][0]) for b in BANDS3)))
        say()
        rho = spearman([t[2]["all"][0] for t in table], [t[3]["all"][0] for t in table])
        say("Rank correlation between the two phrasings: **%s** over %d subjects. %d of %d subjects"
            % ("n/a" if rho is None else "rho = %.2f" % rho, len(table), moved, len(table)))
        say("score differently depending on how the question is put.")
        say()
        flips = []
        for label, rows, _w, _kw in table:
            for r in rows:
                if ok(r, "written") != ok(r, "keyword"):
                    flips.append((label, r.get("difficulty"), r.get("query"),
                                  ok(r, "written"), ok(r, "keyword")))
        if flips:
            say("Questions that change outcome between the two phrasings, first twelve:")
            say()
            say("| subject | band | question | right as written | right as keywords |")
            say("|---|---|---|---|---|")
            for label, band, query, wrote, keyed in flips[:12]:
                say("| %s | %s | %s | %s | %s |" % (
                    label, band, (query or "").replace("|", "/"),
                    "yes" if wrote else "no", "yes" if keyed else "no"))
            say()
            say("%d question outcomes in total change with the phrasing alone - no subject changed,"
                % len(flips))
            say("no store changed, no ranking changed, only the words used to ask.")
        say()

    with open("SHAPE.md", "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(OUT) + chr(10))
    print()
    print("written to SHAPE.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
