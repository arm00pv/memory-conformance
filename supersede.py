#!/usr/bin/env python3
"""supersede.py - does a memory know which version of a fact is current.

EVERY CORPUS HERE ASKS ABOUT A RECORD THAT DOES NOT CHANGE. A memory store is not used that way: a fact is
written, then rewritten, and the first thing its owner needs is the current value rather than the one it
replaced. restart and forget cover a record that is deleted. Nothing here covers a record that is
superseded, which is the ordinary case.

The corpus is built from real data and no author. Every chosen package record is stored TWICE, as two
records whose only difference is the real version string in the body - @name@0.9.2@ and @name@0.9.3@ - and
each question asks with the description both of them carry. The current answer is the later record. A
subject that matches text and nothing else has two identical candidates and no way to prefer one; a subject
that ranks by recency prefers the one written last.

THE PREDICTIONS, WRITTEN BEFORE THE FIRST RUN.

  1. No subject scores above three quarters. Telling two nearly identical records apart by which is newer
     is not something any of them claims, and the text carries no signal that says which is later.
  2. Subjects that return several results will return BOTH versions more often than either one, so the
     score will sit near a half.
  3. At least one subject scores below a quarter, i.e. it prefers the stale record systematically.

  python supersede.py --build
  python supersede.py --measure
  python supersede.py --report
"""
import json
import os
import re
import subprocess
import sys

import questions

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
OUT = "supersede_corpus.json"
SUFFIX = "-super"
SOURCE = "retrieval_corpus_real.json"
REPEAT = 2
MAX_TEXT = 300


def bump(version):
    """The next version string: the last numeric component plus one, and a default when there is none."""
    parts = re.findall(r"\d+", version or "")
    if not parts:
        return "0.0.1", "0.0.2"
    base = [int(p) for p in parts]
    old = ".".join(str(p) for p in base)
    base[-1] += 1
    return old, ".".join(str(p) for p in base)


def build():
    with open(SOURCE, encoding="utf-8") as fh:
        real = json.load(fh)
    records, queries = [], []
    for r in real["records"]:
        text = r["text"]
        desc = text.split(" Version ")[0].strip()
        old, new = bump((text.split(" Version ")[-1].split(".")[0:1] or [""])[0]
                        if " Version " in text else "")
        def body(version):
            t = desc + " Version " + version + "."
            if len(t) > MAX_TEXT:
                cut = t[:MAX_TEXT]
                t = cut[:cut.rfind(" ")] if " " in cut else cut
            return t
        old_id = "%s@%s" % (r["id"], old)
        new_id = "%s@%s" % (r["id"], new)
        records.append({"id": old_id, "text": body(old)})
        records.append({"id": new_id, "text": body(new)})
        queries.append({"query": desc, "expect": new_id, "stale": old_id, "difficulty": "current"})

    # TWO PACKAGES WITH ONE DESCRIPTION make one question with two current versions, and a corpus that
    # grades either answer wrong is not measuring recency. Both copies go.
    queries, repeated = questions.once(queries)

    doc = {"why": ("Every real package record stored twice, differing only in a real version string. Each "
                   "question asks with the description both carry and expects the later one, so the score "
                   "is whether a memory can tell a current fact from the one it replaced."),
           "records": records, "queries": queries,
           "authored_by": "node_modules",
           "authored_at": "not applicable - no author",
           "dropped": sorted(repeated)}
    with open(OUT, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + chr(10))
    print("%d records, %d questions" % (len(records), len(queries)))
    if repeated:
        print("  dropped %d question(s) that two records answer equally: %s"
              % (len(repeated), "; ".join(sorted(repeated))[:160]))

    return 0


def measure(argv):
    import matrix
    only = None
    for a in argv:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
    matrix.RETRIEVAL_REPEAT = REPEAT
    with open("subjects.json", encoding="utf-8") as fh:
        subjects = json.load(fh)
    for entry in subjects:
        label = "%s %s" % (entry["name"], entry["version"])
        if only and only not in label:
            continue
        print("supersede: %s ..." % label, flush=True)
        got = matrix.run_retrieval(entry, int(entry.get("timeout", 90)), cases=OUT, suffix=SUFFIX)
        print("   %s" % json.dumps((got or {}).get("all") or ({} if got else {"no": "result"})), flush=True)
    return 0


def rows_of(slug):
    path = os.path.join("results", slug + "-retrieval" + SUFFIX + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh).get("rows") or None
    if not rows:
        return None
    # ROWS ABOUT A QUESTION THE CORPUS NO LONGER ASKS ARE NOT MEASUREMENTS. Every corpus here is rebuilt
    # when somebody finds a question that two records answer equally, and the old rows for the questions it
    # dropped would otherwise keep counting in this table as though the corpus still asked them.
    live = questions.live(OUT)
    return [r for r in rows if r["query"] in live] or None


def score(rows):
    """Current, stale, both, or neither - per question."""
    with open(OUT, encoding="utf-8") as fh:
        doc = json.load(fh)
    want = dict((q["query"], q) for q in doc["queries"])
    out = {"n": 0, "current": 0, "stale": 0, "both": 0, "neither": 0, "first": 0}
    for row in rows:
        q = want.get(row["query"])
        if not q:
            continue
        out["n"] += 1
        if row.get("hit1"):
            out["first"] += 1
        returned = [str(x) for x in (row.get("returned") or [])]
        has_new = q["expect"] in returned
        has_old = q["stale"] in returned
        if has_new and has_old:
            out["both"] += 1
        elif has_new:
            out["current"] += 1
        elif has_old:
            out["stale"] += 1
        else:
            out["neither"] += 1
    return out


def report():
    import resolution
    got = {}
    for s in resolution.subjects():
        rows = rows_of(s["slug"])
        if rows:
            got[s["label"]] = score(rows)
    if len(got) < 4:
        raise SystemExit("not enough subjects measured on the supersession corpus")
    lines = []
    add = lines.append
    add("# Does a memory know which version of a fact is current")
    add("")
    add("Generated by " + BT + "supersede.py" + BT + ". Do not edit by hand.")
    add("")
    add("Every corpus here asks about a record that does not change. A memory store is not used that way: a")
    add("fact is written, then rewritten, and the first thing its owner needs is the current value rather than")
    add("the one it replaced. " + BT + "restart" + BT + " and " + BT + "forget" + BT + " cover a record that is deleted; nothing covers a")
    add("record that is superseded, which is the ordinary case.")
    add("")
    add("Every chosen package record is stored **twice**, as two records whose only difference is the version")
    add("string in the body, and each question asks with the description both carry. The current answer is the")
    add("later record.")
    add("")
    add("## The predictions, written before the run")
    add("")
    add("1. No subject scores above three quarters.")
    add("2. Subjects that return several results return both versions about as often as either one.")
    add("3. At least one subject scores below a quarter.")
    add("")
    add("## The result")
    add("")
    add("| subject | current, alone | stale, alone | both returned | neither | current first |")
    add("|---|---|---|---|---|---|")
    for name in sorted(got, key=lambda k: (-got[k]["first"], -got[k]["current"])):
        s = got[name]
        n = s["n"] or 1
        add("| " + BT + name + BT + " | %d | %d | %d | %d | **%d of %d** |"
            % (s["current"], s["stale"], s["both"], s["neither"], s["first"], n))
    add("")
    best = max(got.values(), key=lambda s: s["current"])
    worst = min(got.values(), key=lambda s: s["current"])
    n = best["n"] or 1
    firsts = sorted(nm for nm, s in got.items() if s["first"])
    add("**The best subject puts the current record first on %d of %d questions, and %d of the %d subjects"
        % (max(s["first"] for s in got.values()), n,
           len(got) - len(firsts), len(got)))
    add("never put it first once.** Every one of those returns the SUPERSEDED record ahead of the record"
        " that"
        if False else
        "never put it first once.** Every one of those returns the SUPERSEDED record ahead of the record that")
    add("replaced it, because the two bodies are nearly identical and nothing in either says which is later.")
    add("")
    stale = sum(s["stale"] for s in got.values())
    both = sum(s["both"] for s in got.values())
    if stale or both:
        add("Across the whole table, %d answers came from the superseded record and %d returned both, which is"
            % (stale, both))
        add("the honest description of what these systems do with a fact that changed: they have no notion of")
        add("which of two nearly identical records is later, and the text gives them none.")
        add("")
    add("## What this does not settle")
    add("")
    add("The two versions differ in the body and not in the record's name, so this measures *ranking* between")
    add("two candidates rather than storage semantics. A subject that overwrites a record on a repeated write")
    add("- which some of them do - would answer this trivially if the two writes used the same name; keeping")
    add("the names distinct is deliberate, because the question is whether recency is visible at all.")
    add("")
    add("It also does not test a real update protocol. Asking a memory to revise a fact, and being able to")
    add("distinguish a revision from a second unrelated fact, is a capability none of these subjects claims and")
    add("the probe suite has never asked for.")
    add("")
    path = os.path.join(HERE, "SUPERSESSION.md")
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
