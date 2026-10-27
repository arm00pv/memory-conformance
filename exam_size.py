#!/usr/bin/env python3
"""exam_size.py - the same store, five times as many questions.

THE POWER ANALYSIS HAS BEEN A CLAIM ABOUT THE FUTURE. band.py puts a price on a near-tie - 371 questions
for the leader against the control on corpus A, 679 against zenbrain, 11,825 on corpus B - and none of
those prices has ever been paid, so the arithmetic has never been checked against an experiment.

This pays one of them at a fifth of the size. The store is IDENTICAL to the sixty-question authorless
corpus: the same 72 real package records, already ingested by every subject. Only the question count
changes - each record asked verbatim, with a third of its words gone, and with half of them gone, plus a
drawn absent band, to reach three hundred.

A LARGER STORE WAS TRIED FIRST AND ABANDONED. At 282 records the control alone needed about nine minutes
for 300 questions, because it reads the whole store on every search, and eleven subjects would not have
finished inside a session. Holding the store fixed removes that cost and removes a confound with it:
nothing changes between the two exams except how many questions are asked.

WHAT THAT COSTS IN HONESTY: three questions about one record are not three independent draws, so this exam
carries less than three hundred questions worth of information. The direction of the bias is stated in the
report - correlated questions make separation harder, so a tie broken here is real evidence and a tie that
survives here is weaker evidence than the count suggests.

THE PREDICTIONS, WRITTEN BEFORE THE FIRST RUN.

  1. The leader is control 1.0.0, as on the sixty-question authorless corpus (60 of 60 there).
  2. control against memory-lean does NOT separate. The small-corpus margin is one question in sixty
     (1-0, p = 1.00), and one question per record cannot turn that into a convincing one-way split.
  3. The separated-pair count rises and stays below all 55.

  python exam_size.py --build
  python exam_size.py --measure
  python exam_size.py --report
"""
import itertools
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
OUT = "large_corpus.json"
SUFFIX = "-large"
SOURCE = "retrieval_corpus_real.json"
REPEAT = 1
TARGET = 300
LONG4 = re.compile(r"[A-Za-z]{4,}")


def long_words(text):
    return [w.lower() for w in LONG4.findall(text)]


def thin(text, k):
    """Drop every k-th long word, leaving the short ones and the order alone."""
    out, n = [], 0
    for word in text.split():
        if LONG4.match(word):
            n += 1
            if n % k == 0:
                continue
        out.append(word)
    return " ".join(out)


def build():
    import real_corpus
    with open(SOURCE, encoding="utf-8") as fh:
        real = json.load(fh)
    records = real["records"]
    store = [set(long_words(r["text"])) for r in records]
    names = set(r["id"] for r in records)

    queries = []
    for r in records:
        desc = r["text"].split(" Version ")[0].strip()
        if len(long_words(desc)) < 5:
            continue
        queries.append({"query": desc, "expect": r["id"], "difficulty": "d0"})
        for k in (3, 2):
            text = thin(desc, k)
            if len(text.split()) >= 4:
                queries.append({"query": text, "expect": r["id"], "difficulty": "d%d" % k})

    import real_corpus as rc
    pool = rc.pool()
    spare = [it for it in pool if it["name"] not in names]
    want_absent = max(0, TARGET - len(queries))
    step = max(1, len(spare) // (want_absent + 12))
    for it in spare[::step]:
        if sum(1 for q in queries if q["difficulty"] == "absent") >= want_absent:
            break
        want = set(long_words(it["desc"]))
        if not want:
            continue
        if max(len(want & w) for w in store) / float(len(want)) > 0.5:
            continue
        queries.append({"query": it["desc"], "expect": None, "difficulty": "absent"})

    doc = {"why": ("The sixty-question authorless corpus at five times the question count, on the SAME 72 "
                   "records: each record asked verbatim, with a third of its words gone and with half of "
                   "them gone, plus an absent band drawn to reach three hundred."),
           "records": records, "queries": queries,
           "authored_by": "node_modules",
           "authored_at": "not applicable - no author"}
    with open(OUT, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + chr(10))
    got = {}
    for q in queries:
        got[q["difficulty"]] = got.get(q["difficulty"], 0) + 1
    print("%d records, %d questions: %s"
          % (len(records), len(queries), ", ".join("%s %d" % (k, v) for k, v in sorted(got.items()))))
    return 0


def measure(argv):
    only = None
    for a in argv:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
    with open("subjects.json", encoding="utf-8") as fh:
        subjects = json.load(fh)
    for entry in subjects:
        label = "%s %s" % (entry["name"], entry["version"])
        if only and only not in label:
            continue
        slug = ("%s-%s" % (entry["name"], entry["version"])).replace("/", "_").replace("@", "")
        out = os.path.join("results", slug + "-retrieval" + SUFFIX + ".json")
        # THE COMMAND IS PASSED BARE. matrix.py builds "--cmd=" + entry["cmd"] with no quoting, and
        # wrapping it in quotes makes retrieval.py exec a single token containing spaces - which fails
        # for every subject and reports it as "no result".
        args = [sys.executable, "retrieval.py", "--cmd=" + entry["cmd"],
                "--timeout=%d" % int(entry.get("timeout", 90)),
                "--repeat=%d" % REPEAT, "--cases=" + OUT, "--json=" + out]
        if entry.get("manifest"):
            args.append("--manifest=" + entry["manifest"])
        else:
            args.append("--adapter=" + entry.get("adapter", "reference"))
        print("large: %s ..." % label, flush=True)
        subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if os.path.isfile(out):
            with open(out, encoding="utf-8") as fh:
                summary = json.load(fh).get("summary") or {}
            print("   %s" % json.dumps(summary.get("all") or {}), flush=True)
        else:
            print("   no result", flush=True)
    return 0


def rows_of(slug, suffix=SUFFIX):
    path = os.path.join("results", slug + "-retrieval" + suffix + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("rows") or None


def totals(suffix):
    import resolution
    out = []
    for s in resolution.subjects():
        rows = rows_of(s["slug"], suffix)
        if not rows:
            continue
        vals = [resolution.outcome(r, "written", "score") for r in rows]
        vals = [v for v in vals if v is not None]
        if vals:
            out.append((sum(1 for v in vals if v), len(vals), s["label"]))
    return sorted(out, key=lambda t: (-t[0], t[2]))


def separations(suffix):
    import resolution
    people = [(s["label"], s["slug"]) for s in resolution.subjects()]
    rows = dict((label, rows_of(slug, suffix)) for label, slug in people)
    rows = dict((k, v) for k, v in rows.items() if v)
    out = {}
    for a, b in itertools.combinations(sorted(rows), 2):
        out[(a, b)] = resolution.compare_pair(rows[a], rows[b], "written", "score")
    return out


def ambiguity():
    """How many of the exam's slots are not distinct questions, and how many have two right answers.

    TWO PACKAGES CAN SHARE A DESCRIPTION WORD FOR WORD - a fork and its original, a client and a server
    built from one template - and a corpus built from real data inherits that collision silently. The
    same words then appear twice with different expected records, so a subject that returns the other
    of the two is graded wrong for being right.
    """
    with open(OUT, encoding="utf-8") as fh:
        doc = json.load(fh)
    groups = {}
    for q in doc["queries"]:
        groups.setdefault(q["query"], []).append(q)
    repeats = sum(len(v) - 1 for v in groups.values())
    shared = {}
    for k, v in groups.items():
        expects = [x.get("expect") for x in v if x.get("expect")]
        if len(v) > 1 and len(set(expects)) > 1:
            shared[k] = sorted(set(expects))
    return {"slots": len(doc["queries"]), "distinct": len(groups), "repeats": repeats,
            "shared": shared}


def report():
    big_rows, small_rows = totals(SUFFIX), totals("-real")
    if not big_rows:
        raise SystemExit("nothing measured on the large exam yet")
    big = dict((label, got) for got, _n, label in big_rows)
    small = dict((label, got) for got, _n, label in small_rows)
    n_big, n_small = big_rows[0][1], small_rows[0][1]
    sep_big, sep_small = separations(SUFFIX), separations("-real")
    lines = []
    add = lines.append
    add("# The same store, five times as many questions")
    add("")
    add("Generated by " + BT + "exam_size.py" + BT + ". Do not edit by hand.")
    add("")
    add("The power analysis has been a claim about the future for three phases. " + BT + "band.py" + BT + " puts a")
    add("price on a near-tie - 371 questions for the leader against the control, 679 against zenbrain, 11,825")
    add("on corpus B - and none of those prices has ever been paid. This pays one of them at a fifth of the")
    add("size.")
    add("")
    add("**The store is identical to the sixty-question authorless corpus**: the same 72 real records, already")
    add("ingested by every subject. Only the question count changes - each record asked verbatim, with a third")
    add("of its words gone, and with half of them gone, plus a drawn absent band.")
    add("")
    add("## The predictions, written before the run")
    add("")
    add("1. The leader is " + BT + "control 1.0.0" + BT + ".")
    add("2. " + BT + "control" + BT + " against " + BT + "memory-lean" + BT + " does **not** separate.")
    add("3. The separated-pair count rises and stays below all 55.")
    add("")
    add("## The totals")
    add("")
    add("| subject | " + str(n_big) + " questions | " + str(n_small) + " questions |")
    add("|---|---|---|")
    for name in sorted(big, key=lambda k: -big[k]):
        add("| " + BT + name + BT + " | **%d of %d** | %s |"
            % (big[name], n_big, ("%d of %d" % (small[name], n_small)) if name in small else "-"))
    add("")
    add("## How much resolution five times the questions buys")
    add("")
    add("| exam | questions | pairs separated |")
    add("|---|---|---|")
    add("| small | %d | **%d of %d** |"
        % (n_small, sum(1 for v in sep_small.values() if v["separated"]), len(sep_small)))
    add("| large | %d | **%d of %d** |"
        % (n_big, sum(1 for v in sep_big.values() if v["separated"]), len(sep_big)))
    add("")
    flipped = sorted(k for k in set(sep_big) & set(sep_small)
                     if sep_big[k]["separated"] != sep_small[k]["separated"])
    add("%d pair(s) reach a different verdict on the larger exam:" % len(flipped))
    add("")
    for k in flipped[:10]:
        add("- " + BT + k[0] + BT + " vs " + BT + k[1] + BT + ": p %.3f at %d questions, %.3f at %d"
            % (sep_small[k]["p"], n_small, sep_big[k]["p"], n_big))
    if flipped:
        add("")
    add("## The prediction tested")
    add("")
    # THE PAIR IS TWO LABELS IN A TUPLE, so a substring test against the tuple never matches: this
    # searched for "memory-lean" among elements like "memory-lean 1.5.0", found nothing, and printed an
    # empty section under a heading that promised a verdict.
    pair = None
    for k in sep_big:
        if any("control 1.0.0" in x for x in k) and any("memory-lean" in x for x in k):
            pair = k
    if pair and pair in sep_small:
        b, sm = sep_big[pair], sep_small[pair]
        add(BT + pair[0] + BT + " vs " + BT + pair[1] + BT + ":")
        add("")
        add("| exam | split | exact p | separated |")
        add("|---|---|---|---|")
        add("| %d questions | %d-%d | %.4f | %s |"
            % (n_small, sm["only_a"], sm["only_b"], sm["p"], "yes" if sm["separated"] else "no"))
        add("| %d questions | %d-%d | %.4f | %s |"
            % (n_big, b["only_a"], b["only_b"], b["p"], "yes" if b["separated"] else "no"))
        add("")
        verdict = "held" if not b["separated"] else "failed"
        add("**The prediction " + verdict + ".** "
            + ("Five times the questions did not break the tie, which is what a price of a few hundred"
               " questions predicts: the exam grew and the margin did not."
               if not b["separated"] else
               "The pair separated once the exam was longer, so the deficit was not a fixed handicap and"
               " the price calculation was the thing that was wrong."))
        add("")
    add("## What the three hundred slots actually ask")
    add("")
    amb = ambiguity()
    add("**The exam is %d slots for %d distinct questions.** Two packages can share a description word"
        % (amb["slots"], amb["distinct"]))
    add("for word - a fork and its original, a client and a server built from one template - so the same")
    add("words are asked twice with a different expected record. %d question texts are of that kind and"
        % len(amb["shared"]))
    add("they occupy %d slots: a subject that returns the other one of the two records is graded wrong for"
        % (amb["repeats"]))
    add("being right. The totals above use the corpus's own expected record, so they understate any subject")
    add("that answers one of those questions with its sibling:")
    add("")
    for q, expects in list(amb["shared"].items())[:4]:
        add("- " + BT + q[:70] + BT + " is answered by " + " and ".join(BT + e + BT for e in expects))
    add("")
    add("Precision is the phase that found this, in the same reading that counts what comes back: "
        + BT + "precision.py" + BT + " credits either record, and the difference between the two readings is")
    add("an estimate of how much of this exam is a coin toss. Both charges are pinned in")
    add(BT + "corpus-known.json" + BT + ", so the next corpus that repeats a question fails the build instead of")
    add("quietly becoming the sample size.")
    add("")
    add("## What this does not settle")
    add("")
    add("**Three questions about one record are not three independent draws.** The store stayed at 72")
    add("records because a larger one was tried first and abandoned: at 282 records the control alone needed")
    add("about nine minutes for 300 questions, because it reads the whole store on every search. The price of")
    add("that choice is correlation, and the direction of the bias matters - correlated questions make")
    add("separation harder, so a tie broken here is real evidence and a tie that survives here is weaker")
    add("evidence than " + str(n_big) + " questions suggests.")
    add("")
    add("Nor does it settle the price for the other near-ties: band.py quotes 1,401 and 11,825 questions for")
    add("pairs on other corpora, and those are still unpayable.")
    add("")
    path = os.path.join(HERE, "EXAM-SIZE.md")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print("written to %s" % path)
    return 0


def main(argv):
    argv = list(argv)
    if "--build" in argv:
        return build()
    if "--measure" in argv:
        return measure(argv)
    return report()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))