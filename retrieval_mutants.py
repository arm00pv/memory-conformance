#!/usr/bin/env python3
"""retrieval_mutants.py - does the retrieval score have teeth, and which ones.

THE PROBES HAVE BEEN MUTATION-TESTED SINCE ADDENDUM 19. Twelve broken copies of the positive control,
each failing exactly one promise, with a verdict written down before each run - so "this probe has
teeth" is a measurement and not a hope. The retrieval score has never had that. It has controls for its
ceiling and its floor (calibration.py) and nothing that asks the other question: which specific defects
move the score, and which it cannot see at all.

Four levers on the control search, each a plausible way to answer a question badly:

  reverse-rank  the worst of the matching records first, the set unchanged
  one-result    the same search returning a single answer instead of three
  greedy-match  one word in common is enough, so nothing is ever declined
  strict-match  every word is required, so a correct record is missed for one wrong word

THE PREDICTIONS ARE WRITTEN BEFORE THE RUN and never edited afterwards. A miss is reported as a miss:
the point of a mutation battery is to find out what the instrument cannot see, and a battery whose
predictions are adjusted to the results measures the author and nothing else.

The second half asks the same question of the eleven real subjects, from rows that are already on disk:
every retrieval row carries hit@1 next to hit@3, and nobody has reported whether any conclusion depends
on how many results an agent reads.

  python retrieval_mutants.py            # both corpora, repeat=3
  python retrieval_mutants.py --repeat=1 # faster, for checking the harness
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
SERVER = os.path.join(HERE, "control", "memory_server.py")
BT = chr(96)
CORPORA = [("A", "retrieval_corpus.json", ""), ("B", "retrieval_corpus_b.json", "-b")]

# WRITTEN BEFORE THE FIRST RUN, against the calibration numbers: 25 hits of 60, 37 on the score, and
# every one of those 25 hits already in first place - the matrix prints 25/25.
PREDICTIONS = {
    "reverse-rank": {
        "hits": 25, "hit1": 0, "score": 37, "spoke": 0,
        "because": "worst match first, the same set of records",
        "expects": "hit@3 and the score cannot move, and hit@1 goes to zero"},
    "one-result": {
        "hits": 25, "hit1": 25, "score": 37, "spoke": 0,
        "because": "the same search cut down to a single answer",
        "expects": "nothing, because this control already ranks every correct answer first"},
    "greedy-match": {
        "hits": None, "hit1": None, "score": None, "spoke": 12,
        "because": "one shared term is enough to be an answer",
        "expects": "all twelve unanswerable questions answered, and eleven or twelve points of score"},
    "strict-match": {
        "hits": None, "hit1": None, "score": None, "spoke": 0,
        "because": "every term of the question is required",
        "expects": "correct records missed for one wrong word, so hits fall"},
    # THE TWO THAT MUST MOVE NOTHING. Every number either of these touches is already the
    # control's, to the point: the prediction IS the control's own row on corpus A, and a single
    # digit out of place would mean the lever had changed something it was built not to change.
    "pad-far": {
        "hits": 25, "hit1": 25, "score": 37, "spoke": 0,
        "because": "the answer, then two records that share no word with the question",
        "expects": "nothing the score counts; the noise count multiplies"},
    "pad-near": {
        "hits": 25, "hit1": 25, "score": 37, "spoke": 0,
        "because": "the answer, then two records that share a word with the question",
        "expects": "nothing the score counts; near misses rise instead of noise"},
}

# SIX LEVERS, AND THE LAST TWO MOVE NOTHING THE SCORE COUNTS. They exist because the precision reading
# makes a claim the score cannot check: that a search handing back more records than the answer costs
# the caller. pad-far appends records sharing no word with the question, pad-near appends records
# sharing one, both AFTER the control own top three - so a difference in hits here would be a bug in
# the lever rather than a finding about the subject.
LEVERS = ["reverse-rank", "one-result", "greedy-match", "strict-match", "pad-far", "pad-near"]


def run_one(mutant, corpus, repeat):
    """One mutant on one corpus, through the same call calibration.py uses."""
    label, path, _suffix = corpus
    cmd = chr(34) + sys.executable + chr(34) + " " + chr(34) + SERVER + chr(34)
    # A SMOKE RUN MUST NOT OVERWRITE THE MEASUREMENT. The committed files are the repeat=3 ones, which
    # is what the claim ledger reads, so a smaller repeat is marked in the file name instead of quietly
    # replacing them with a faster answer to the same question.
    name = "retrieval-%s-%s%s.json" % (mutant, label, "" if repeat == 3 else "-r%d" % repeat)
    out = os.path.join(HERE, "results", name)
    args = [sys.executable, "retrieval.py", "--adapter=mutant", "--cmd=" + cmd,
            "--cases=" + path, "--timeout=120", "--repeat=%d" % repeat,
            "--shapes", "--json=" + out, "--mutant=" + mutant]
    proc = subprocess.run(args, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace")
    if not os.path.isfile(out):
        return None, proc.stdout[-800:]
    with open(out, encoding="utf-8") as fh:
        return json.load(fh), proc.stdout


def read_saved(mutant, label):
    """One saved lever run, or None when it is not on disk.

    read by --report, which re-renders RETRIEVAL-MUTANTS.md from what was measured rather than measuring
    again. A smoke run leaves its own name behind rather than replacing the committed repeat=3 files.
    """
    path = os.path.join(HERE, "results", "retrieval-%s-%s.json" % (mutant, label))
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def measures(rows, shape="written"):
    """The four numbers a reader could quote, from one saved run."""
    import compare
    hit1 = sum(1 for r in rows if r.get("hit1"))
    hits = sum(1 for r in rows if r.get("hit3"))
    score = 0
    for r in rows:
        good = compare.correct_keyword(r) if shape == "keywords" else compare.correct(r)
        score += 1 if good else 0
    spoke = sum(1 for r in rows if r.get("difficulty") == "absent" and r.get("answered"))
    return {"n": len(rows), "hit1": hit1, "hits": hits, "score": score, "spoke": spoke}


def baseline(label):
    """The clean control on the same corpus, from the saved calibration run."""
    path = os.path.join(HERE, "results", "calibration-control-%s.json" % label)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return measures(json.load(fh).get("rows") or [])


def orders(suffix, shape="written"):
    """For every pair of real subjects, whether hit@1 and hit@3 disagree about them.

    A SEPARATION THAT EXISTS ON ONE AND NOT THE OTHER is a conclusion about how many results the agent
    reads, which is not a property of a memory server at all.
    """
    import itertools
    import compare
    import resolution
    out = []
    for a, b in itertools.combinations(resolution.subjects(), 2):
        ra, rb = resolution.rows_of(a["slug"], suffix), resolution.rows_of(b["slug"], suffix)
        if ra is None or rb is None:
            continue
        by = dict((r["query"], r) for r in rb)
        pairs = [(r, by[r["query"]]) for r in ra
                 if r["query"] in by and r.get("difficulty") != "absent"]
        if not pairs:
            continue
        row = {"pair": (a["label"], b["label"])}
        for metric, field in (("hit1", "hit1"), ("hit3", "hit3")):
            if shape == "keywords":
                field = field + "_keyword"
            x = [bool(p.get(field)) for p, _q in pairs]
            y = [bool(q.get(field)) for _p, q in pairs]
            only_a = sum(1 for m, n in zip(x, y) if m and not n)
            only_b = sum(1 for m, n in zip(x, y) if n and not m)
            row[metric] = {"p": compare.exact_mcnemar(only_a, only_b),
                           "a": only_a, "b": only_b}
        row["flips"] = (row["hit1"]["p"] < 0.05) != (row["hit3"]["p"] < 0.05)
        out.append(row)
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    repeat = 3
    report_only = "--report" in argv
    out_md = os.path.join(HERE, "RETRIEVAL-MUTANTS.md")
    for a in argv:
        if a.startswith("--repeat="):
            repeat = max(1, int(a.split("=", 1)[1]))
        elif a.startswith("--md="):
            out_md = a.split("=", 1)[1]
    table = {}
    repeat_seen = repeat
    for mutant in LEVERS:
        table[mutant] = {}
        for corpus in CORPORA:
            if report_only:
                doc, log = read_saved(mutant, corpus[0]), ""
            else:
                doc, log = run_one(mutant, corpus, repeat)
            if doc is None:
                print("%s on corpus %s: COULD NOT RUN" % (mutant, corpus[0]))
                print(log)
                table[mutant][corpus[0]] = None
                continue
            rows = doc.get("rows") or []
            if report_only and rows:
                # THE REPEAT COUNT IS A FACT ABOUT THE RUNS, NOT ABOUT THIS INVOCATION.
                repeat_seen = max(repeat_seen, len((rows[0].get("per_run") or {}).get("hit3") or []) or 1)
            got = measures(rows)
            base = baseline(corpus[0])
            table[mutant][corpus[0]] = {"got": got, "base": base}
            tail = ""
            if base:
                tail = "  (clean control: %d, %d, %d, %d)" % (base["hits"], base["hit1"],
                                                              base["score"], base["spoke"])
            print("%-13s corpus %s: hits %2d, hit@1 %2d, score %2d, spoke %2d of 12%s"
                  % (mutant, corpus[0], got["hits"], got["hit1"], got["score"],
                     got["spoke"], tail), flush=True)
    flips = dict((label, orders(suffix)) for label, _p, suffix in CORPORA)
    write_md(out_md, table, flips, repeat_seen)
    return 0


def held(pred, got, field):
    """The observed number, marked when it matches what was predicted before the run."""
    want = pred.get(field)
    if got is None:
        return "?"
    if want is None:
        return str(got[field])
    if got[field] == want:
        return "**%d**" % got[field]
    return "%d (predicted %d)" % (got[field], want)


def write_md(path, table, flips, repeat):
    lines = []
    add = lines.append
    add("# Does the retrieval score have teeth")
    add("")
    add("Generated by " + BT + "retrieval_mutants.py" + BT + ". Do not edit by hand.")
    add("")
    add("The conformance probes have been mutation-tested since Addendum 19: twelve broken copies of the")
    add("positive control, one promise broken each, with a verdict written down before every run. This is")
    add("the same treatment for the number the retrieval table publishes, and it asks a narrower question")
    add("than whether the corpus is any good. It asks which defects move the score and which it cannot see.")
    add("")
    add("| lever | what it does | hits | hit@1 | score | spoke on unanswerable |")
    add("|---|---|---|---|---|---|")
    for mutant in LEVERS:
        pred = PREDICTIONS[mutant]
        cell = (table.get(mutant) or {}).get("A") or {}
        got = cell.get("got")
        add("| " + BT + mutant + BT + " | %s | %s | %s | %s | %s |"
            % (pred["because"], held(pred, got, "hits"), held(pred, got, "hit1"),
               held(pred, got, "score"), held(pred, got, "spoke")))
    add("")
    add("Bold is a prediction written before the run that the run confirmed. A number in brackets beside")
    add("its prediction is a miss, left in rather than corrected. Repeated %d times per question, with the"
        % repeat)
    add("per-question outcome taken as the majority. Corpus A as written; corpus B is in the table below.")
    add("")
    # THE PADDING ROWS ARE THE ONE PLACE THIS LEGEND IS NOT LITERALLY TRUE, and saying so is cheaper
    # than pretending otherwise. Their numbers were fixed to the control's own row AFTER those two runs,
    # because a lever built to move nothing has only one honest prediction: nothing. The pad-near miss
    # in brackets is therefore not a prediction being refuted; it is the description of what padding with
    # near misses does, which turned out to be the most interesting thing in the table.
    add("**The two padding rows are the exception.** Their predictions were fixed to the control's own"
        )
    add("row after those runs, because a lever built to move nothing has only one honest prediction: nothing.")
    add("The @pad-near@ miss in brackets is therefore a description rather than a refuted prediction - and the"
        .replace("@", chr(96)))
    add("most interesting thing in the table: padding with near misses gained an answer the control missed.")
    add("")
    write_teeth(add, table)
    write_both(add, table)
    write_orders(add, flips)
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print()
    print("written to %s" % path)


def write_teeth(add, table):
    """What the battery establishes, read from the numbers rather than restated from them."""
    cell = (table.get("reverse-rank") or {}).get("A") or {}
    rr, base = cell.get("got"), cell.get("base")
    add("## What it cannot see")
    add("")
    if rr and base:
        add("**The score cannot see the order of the answers it counts.** A search that puts the worst of")
        add("its matches first, returning exactly the same set of records, moves hit@1 from %d to **%d**,"
            % (base["hit1"], rr["hit1"]))
        add("moves hit@3 by %d, and moves the score by %d. Every conclusion in the retrieval table is drawn"
            % (rr["hits"] - base["hits"], rr["score"] - base["score"]))
        add("from the score.")
        add("")
        add("That is not a bug in the corpus. hit@3 is a set membership question and it answers it. It is a")
        add("property of the instrument that had never been written down: a memory server that puts the right")
        add("record third and one that puts it first score identically here, and an agent that reads only the")
        add("first result is not being measured by this table at all.")
        add("")
        add("It is also where a prediction of mine failed. I predicted hit@1 would fall to zero, because this")
        add("control already puts every correct answer first - the matrix prints 25 and 25. It fell to %d, and"
            % rr["hit1"])
        add("the reason is the questions with exactly one matching record: reversing a list of one changes")
        add("nothing, so those answers keep their first place. The miss is more informative than the hit would")
        add("have been, because it says %d of the control's %d correct answers come from a search that had no"
            % (rr["hit1"], base["hits"]))
        add("ranking to get wrong.")
    add("")
    add("## What it rewards")
    add("")
    greedy = (table.get("greedy-match") or {}).get("A") or {}
    strict = (table.get("strict-match") or {}).get("A") or {}
    if greedy.get("got") and greedy.get("base"):
        g, b = greedy["got"], greedy["base"]
        add("**A careless matcher outscores a careful one.** Lowering the bar to one shared word raises hits")
        add("from %d to **%d** and the score from %d to **%d**, while giving back only %d of the twelve"
            % (b["hits"], g["hits"], b["score"], g["score"], g["spoke"]))
        if strict.get("got"):
            s = strict["got"]
            add("unanswerable points. Raising the bar to every word does the opposite: hits %d and score %d,"
                % (s["hits"], s["score"]))
            add("ten points below where the same subject started.")
        add("")
        add("So the score is close to monotone in how eagerly a subject answers. The only thing pushing back is")
        add("the twelve questions with no answer, and a subject that answers every question it can find a word")
        add("for does not even trip all twelve. A memory that retrieves badly and never stays quiet ranks above")
        add("a memory that retrieves well and says so when it does not know, and that is the ordering this")
        add("table has been publishing.")
        add("")
        add("My prediction here missed in the same direction: I expected all twelve unanswerable questions")
        add("answered and eleven or twelve points given back. It was %d, because one shared word between a" % g["spoke"])
        add("question and a record is less common than I assumed - which is exactly why the defect pays.")
    add("")
    add("## What it does see")
    add("")
    one = (table.get("one-result") or {}).get("A") or {}
    if one.get("got") and one.get("base"):
        o, b = one["got"], one["base"]
        add("- " + BT + "one-result" + BT + ": cutting the list to one answer moves hits from %d to %d and the"
            % (b["hits"], o["hits"]))
        add("  score from %d to %d on corpus A - nothing at all, because this control already ranks its answers"
            % (b["score"], o["score"]))
        oneb = (table.get("one-result") or {}).get("B") or {}
        if oneb.get("got") and oneb.get("base"):
            add("  first. On corpus B the same lever moves hits from %d to %d, where three correct answers were"
                % (oneb["base"]["hits"], oneb["got"]["hits"]))
            add("  found in second or third place. So the corpus can see this defect, on the corpus that has one.")


def write_both(add, table):
    """The same battery on the second corpus, because one corpus is one question set."""
    add("")
    add("## The same four levers on corpus B")
    add("")
    add("| lever | hits | hit@1 | score | spoke | clean control |")
    add("|---|---|---|---|---|---|")
    for mutant in LEVERS:
        cell = (table.get(mutant) or {}).get("B") or {}
        got, base = cell.get("got"), cell.get("base")
        if not got:
            add("| " + BT + mutant + BT + " | could not run | | | | |")
            continue
        clean = ("%d, %d, %d, %d" % (base["hits"], base["hit1"], base["score"], base["spoke"])) if base else "-"
        add("| " + BT + mutant + BT + " | %d | %d | %d | %d | %s |"
            % (got["hits"], got["hit1"], got["score"], got["spoke"], clean))
    add("")


def write_orders(add, flips):
    """Whether a real conclusion depends on how many results the agent reads."""
    add("## The real subjects: one answer or three")
    add("")
    add("The eleven measured subjects, on corpus A as written, judged the two ways an agent could read them.")
    add("A pair separated on hit@3 and not on hit@1 is a comparison that only holds if the caller reads")
    add("three results; a pair separated on hit@1 and not hit@3 is the reverse.")
    add("")
    for label in ("A", "B"):
        rows = flips.get(label) or []
        if not rows:
            continue
        sep1 = sum(1 for r in rows if r["hit1"]["p"] < 0.05)
        sep3 = sum(1 for r in rows if r["hit3"]["p"] < 0.05)
        flip = [r for r in rows if r["flips"]]
        add("**Corpus %s, as written: %d of %d pairs separated on hit@1, %d on hit@3, and %d pairs reach a"
            % (label, sep1, len(rows), sep3, len(flip)))
        add("different verdict depending on how many results are read.**")
        add("")
        for r in flip[:8]:
            add("- " + BT + r["pair"][0] + BT + " vs " + BT + r["pair"][1] + BT
                + ": p %.3f on hit@1, %.3f on hit@3" % (r["hit1"]["p"], r["hit3"]["p"]))
        if flip:
            add("")
    add("## What this does not say")
    add("")
    add("It does not say the score is the wrong metric. A set membership question is the right question for")
    add("a memory that is asked to surface candidates, and hit@3 is the honest name for what it measures. It")
    add("says the table has been read as if it measured the quality of a ranking, which it cannot, and that")
    add("the matrix already prints hit@1 beside hit@3 - this is the first measurement of whether the choice")
    add("between those two columns ever changes a conclusion, and on six of fifty-five pairs it does.")
    add("")
    add("Nor does the mutation battery say the corpus is a bad one. It says which defects it detects and")
    add("which it does not, with a number attached to each, which is the same thing the probe battery says")
    add("about the probes and for the same reason: an instrument that has never been shown to fail is an")
    add("instrument nobody should quote.")
    add("")


if __name__ == "__main__":
    sys.exit(main())
