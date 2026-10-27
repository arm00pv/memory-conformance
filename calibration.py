#!/usr/bin/env python3
"""calibration.py - where does the retrieval score come from, and how far up does it go.

THE RETRIEVAL AXIS HAS NEVER HAD A CONTROL. The conformance probes have a mutation battery that proves
each of them can fail; the retrieval score has been published for eleven subjects without anybody
measuring what a subject has to do to score nothing, what the maximum is, or what "not searching at all"
scores. Every number in that table was therefore relative to a scale whose ends were unknown - 42/60
could be near the top of a scale that ends at 44, and nobody could say.

Four controls, each the positive control with one thing changed, answer that:

  oracle        returns the corpus's own answer key. Not a subject: the ceiling, measured.
  control       the positive control's keyword overlap - the baseline every claim is compared to.
  blind-search  returns the same three records whatever the question. A search that does not search.
  mute-search   returns nothing, ever.

WHAT A MUTE SUBJECT SCORES IS THE FIRST SURPRISE. Twelve of the sixty questions have no answer, and the
score counts returning nothing as correct, so a subject that answers no question at all still scores 12
out of 60. That is not a defect in the scoring - declining an unanswerable question really is the right
behaviour - but it means the floor of the scale is 12 and not 0, and every number in the table is
quoted against 60. calibration.py reports both the hit count, which has a true floor of 0, and the
score, which does not.

  python calibration.py                 # all controls, both corpora, both phrasings
  python calibration.py --repeat=1      # faster, when checking the harness rather than the numbers
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "control", "memory_server.py")

CORPORA = [("A", "retrieval_corpus.json"), ("B", "retrieval_corpus_b.json")]

CONTROLS = [
    ("oracle", "mutant", "oracle-search",
     "the answer key wired to a search tool: the ceiling, measured rather than assumed"),
    ("control", "control", "",
     "the positive control's term overlap, the baseline every claim here is compared to"),
    ("blind-search", "mutant", "blind-search",
     "the same three records whatever is asked - a search that does not search"),
    ("mute-search", "mutant", "mute-search",
     "returns nothing, ever: the floor, and the twelve points available for declining"),
]


def run_one(kind, mutant, corpus, repeat):
    cmd = '"%s" "%s"' % (sys.executable, SERVER)
    out = os.path.join(HERE, "results", "calibration-%s-%s.json"
                       % (mutant or "control", corpus[0]))
    args = [sys.executable, "retrieval.py", "--adapter=" + kind, "--cmd=" + cmd,
            "--cases=" + corpus[1], "--timeout=120", "--repeat=%d" % repeat,
            "--shapes", "--json=" + out]
    if mutant:
        args.append("--mutant=" + mutant)
    proc = subprocess.run(args, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace")
    if not os.path.isfile(out):
        return None, proc.stdout[-800:]
    with open(out, encoding="utf-8") as fh:
        return json.load(fh), proc.stdout


def read_saved(mutant_name, label):
    """One saved control run, or None when it is not on disk.

    read by --report, which re-renders CALIBRATION.md from what was measured rather than measuring again.
    """
    path = os.path.join(HERE, "results", "calibration-%s-%s.json" % (mutant_name, label))
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def counts(rows):
    """Hits, and the score the paired tests use, for one phrasing."""
    hits = sum(1 for r in rows if r.get("hit3"))
    hits_kw = sum(1 for r in rows if r.get("hit3_keyword"))
    return hits, hits_kw


def score(rows, shape):
    """compare.py's definition of correct: a hit, or silence on a question with no answer."""
    import compare
    n = 0
    for row in rows:
        if shape == "keywords":
            n += 1 if compare.correct_keyword(row) else 0
        else:
            n += 1 if compare.correct(row) else 0
    return n


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    repeat = 3
    report_only = "--report" in argv
    if report_only:
        # A REPORT IS NOT A MEASUREMENT. This file was one of three published reports with no way to rebuild
        # it except by running four controls against two corpora, so it could drift from the results under it
        # and nothing would notice - which is exactly what the regeneration guard found in two other reports
        # on its first run. The eight saved runs are on disk; this renders from them.
        repeat = 0
    md = os.path.join(HERE, "CALIBRATION.md")
    for a in argv:
        if a.startswith("--repeat="):
            repeat = max(1, int(a.split("=", 1)[1]))
        elif a.startswith("--md="):
            md = a.split("=", 1)[1]

    table = []
    for name, kind, mutant, what in CONTROLS:
        row = {"name": name, "what": what, "bands": {}}
        for label, path in CORPORA:
            if report_only:
                doc, log = read_saved(mutant or "control", label), ""
            else:
                doc, log = run_one(kind, mutant, (label, path), repeat)
            if doc is None:
                print("%s %s: COULD NOT RUN" % (name, label))
                print(log)
                row["bands"][label] = None
                continue
            rows = doc.get("rows") or []
            if report_only and rows:
                # THE REPEAT COUNT IS A FACT ABOUT THE RUNS, NOT ABOUT THIS INVOCATION. A report says
                # "repeated N times per question", and N is what the saved rows recorded.
                repeat = max(repeat, len((rows[0].get("per_run") or {}).get("hit3") or []) or 1)
            hits, hits_kw = counts(rows)
            n = len(rows)
            absent = sum(1 for r in rows if r["difficulty"] == "absent")
            answered = sum(1 for r in rows if r["difficulty"] == "absent" and r["answered"])
            row["bands"][label] = {
                "n": n, "hits": hits, "hits_kw": hits_kw,
                "score": score(rows, "written"), "score_kw": score(rows, "keywords"),
                "absent": absent, "spoke": answered}
            b = row["bands"][label]
            print("%-13s %-12s corpus %s: hits %2d/%d as written, %2d/%d as keywords;"
                  " score %2d and %2d; spoke on %d of %d unanswerable"
                  % (name, "(%s)" % mutant if mutant else "", label, b["hits"], n,
                     b["hits_kw"], n, b["score"], b["score_kw"], b["spoke"], b["absent"]),
                  flush=True)
        table.append(row)
    write_md(md, table, repeat or 3)
    return 0


def write_md(path, table, repeat):
    lines = []
    add = lines.append
    add("# Where the retrieval score comes from")
    add("")
    add("Generated by `calibration.py`. Do not edit by hand.")
    add("")
    add("Every retrieval number this repository publishes is a count out of 60 questions. This table says")
    add("what the ends of that scale are, by running the same questions against four controls that are")
    add("the positive memory server with one thing changed.")
    add("")
    add("| control | what it is | corpus | hits as written | hits as keywords | score | score as keywords |")
    add("|---|---|---|---|---|---|---|")
    for row in table:
        for label in ("A", "B"):
            b = row["bands"].get(label)
            if not b:
                add("| %s | %s | %s | could not run | | | |" % (row["name"], row["what"], label))
                continue
            add("| %s | %s | %s | %d/%d | %d/%d | %d/%d | %d/%d |"
                % (row["name"], row["what"], label, b["hits"], b["n"], b["hits_kw"], b["n"],
                   b["score"], b["n"], b["score_kw"], b["n"]))
    add("")
    add("Repeated %d times per question; the per-question outcome is the majority." % repeat)
    add("")
    add("## What the four controls establish")
    add("")
    muted = [r for r in table if r["name"] == "mute-search"]
    if muted and muted[0]["bands"].get("A"):
        b = muted[0]["bands"]["A"]
        add("- **The floor of the score is not zero.** A subject that returns nothing at all scores")
        add("  **%d of %d**, because %d of the questions have no answer and returning nothing on them is"
            % (b["score"], b["n"], b["absent"]))
        add("  correct. The hit count has a true floor of zero; the score every paired test is computed")
        add("  from does not, and the difference is the %d points a do-nothing subject collects." % b["absent"])
        add("")
    blind = [r for r in table if r["name"] == "blind-search"]
    if blind and blind[0]["bands"].get("A"):
        b = blind[0]["bands"]["A"]
        add("- **A search that does not search scores %d of %d.** Returning the same three records to"
            % (b["score"], b["n"]))
        add("  every question is not a weak search, it is not a search, and the corpus says so.")
        add("")
    oracle = [r for r in table if r["name"] == "oracle"]
    if oracle and oracle[0]["bands"].get("A"):
        b = oracle[0]["bands"]["A"]
        add("- **The ceiling is %d of %d, and it is reachable.** The oracle is the corpus's own answer"
            % (b["score"], b["n"]))
        add("  key wired to a search tool. It is not a subject and is not in any other table; it is here")
        add("  so that a published score can be read against a maximum that was measured rather than")
        add("  assumed.")
        add("")
    add("## What this does not establish")
    add("")
    add("It does not say the questions are good ones. A corpus can have a reachable ceiling and still ask")
    add("only easy questions; that is what the bands, the second corpus and the phrasing pair are for. It")
    add("also does not make the controls subjects: three of the four are broken on purpose and one cheats")
    add("by construction, which is exactly what a control is for.")
    add("")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print()
    print("written to %s" % path)


if __name__ == "__main__":
    sys.exit(main())
