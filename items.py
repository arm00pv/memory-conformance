#!/usr/bin/env python3
"""items.py - the question set is part of the instrument, so analyse it like one.

EVERY QUESTION IN THIS CORPUS HAS BEEN ASSUMED TO MEASURE SOMETHING. Nothing has checked. A question
every subject answers and a question no subject answers carry exactly the same information about the
differences between subjects: none. Both are wasted, and a corpus can be made of nothing else while
reporting a perfectly respectable spread of scores.

So this is the analysis a test gets before anyone trusts it: for every question, how many subjects got
it right, and how well it separates the subjects that scored well from the ones that did not. Then the
two questions a corpus owner actually needs answering:

  how many questions measure nothing, because everybody answered them the same way
  whether the validator's warning - a one-word adversarial trap is "the weakest kind" - is about
  anything, measured rather than assumed.

DIFFICULTY IS p, THE SHARE OF SUBJECTS THAT GOT IT RIGHT. A score of 0 or 1 is a question with no
discriminating power in this field, whatever it measures in principle.

DISCRIMINATION IS D, the difference in proportion right between the top half of subjects by total score
and the bottom half. That is the classical index and it is deliberately crude: with ten subjects a
point-biserial correlation is a number with a false air of precision, while "the good subjects get this
and the weak ones do not" is what the question is for.

  python items.py              # both corpora, written
  python items.py --shape=keywords
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

CORPORA = [("A", "retrieval_corpus.json", ""), ("B", "retrieval_corpus_b.json", "-b")]
BANDS = ("easy", "hard", "adversarial", "absent")


def right(row, shape):
    """compare.py's definition of a correct answer, read from the phrasing being analysed."""
    import compare
    if shape == "keywords":
        return compare.correct_keyword(row)
    return compare.correct(row)


def subjects(shape):
    """Every subject with saved rows, split by whether its own verdicts are publishable.

    A SUBJECT THAT LEAKS STATE IS EXCLUDED, and that is the same rule the matrix applies when it
    brackets every cell but isolation: its per-question answers describe leaked state, so including it
    in an analysis of what the questions measure would let a leak decide which questions work.
    """
    import matrix
    with open("subjects.json", encoding="utf-8") as fh:
        entries = json.load(fh)
    usable, excluded = [], []
    for entry in entries:
        path = os.path.join("results", matrix.slug_of(entry) + ".json")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
        verdicts = {p["probe"]: p["verdict"] for p in report.get("probes") or []}
        label = "%s %s" % (entry["name"], entry["version"])
        (usable if verdicts.get("isolation") == "PASS" else excluded).append(label)
    return usable, excluded


def rows_for(label, suffix):
    path = os.path.join("results", matrix_slug(label) + "-retrieval" + suffix + ".json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("rows") or []


def matrix_slug(label):
    import matrix
    name, version = label.rsplit(" ", 1)
    return matrix.slug_of({"name": name, "version": version})


def analyse(corpus_label, corpus_path, suffix, shape):
    """Per-question difficulty and discrimination over every in-scope subject."""
    usable, excluded = subjects(shape)
    per_subject = {}
    for label in usable:
        rows = rows_for(label, suffix)
        if not rows:
            continue
        per_subject[label] = {"rows": {r["query"]: r for r in rows},
                              "total": sum(1 for r in rows if right(r, shape))}
    if len(per_subject) < 4:
        return None, excluded, usable
    ordered = sorted(per_subject, key=lambda s: -per_subject[s]["total"])
    half = max(1, len(ordered) // 2)
    top, bottom = ordered[:half], ordered[len(ordered) - half:]
    with open(corpus_path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    items = []
    for q in corpus.get("queries") or []:
        query = q["query"]
        got = {}
        for label in per_subject:
            row = per_subject[label]["rows"].get(query)
            if row is not None:
                got[label] = bool(right(row, shape))
        n = len(got)
        if not n:
            continue
        p = sum(1 for v in got.values() if v) / float(n)
        p_top = sum(1 for s in top if got.get(s)) / float(len(top))
        p_bottom = sum(1 for s in bottom if got.get(s)) / float(len(bottom))
        items.append({"query": query, "difficulty_band": q.get("difficulty"),
                      "expect": q.get("expect"), "n": n, "p": p,
                      "d": p_top - p_bottom,
                      "flat": p == 0.0 or p == 1.0})
    return items, excluded, usable


def trap_table(corpus_path, items):
    """Pair each adversarial item with how strongly another record competes for the same words."""
    import validate_corpus
    with open(corpus_path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    texts = {r["id"]: r["text"] for r in corpus.get("records") or []}
    competitors = validate_corpus.rivals_of(texts, corpus.get("queries") or [])
    out = []
    for item in items:
        if item["difficulty_band"] != "adversarial":
            continue
        got = competitors.get(item["query"])
        if got is None:
            continue
        _core, rivals = got
        strength = max([len(s) for _r, s in rivals] or [0])
        out.append(dict(item, trap=strength))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    shape = "written"
    for a in argv:
        if a.startswith("--shape="):
            shape = a.split("=", 1)[1]
    md = os.path.join(HERE, "ITEMS.md")

    report = []
    for label, path, suffix in CORPORA:
        items, excluded, usable = analyse(label, path, suffix, shape)
        if items is None:
            print("corpus %s: not enough subjects with saved rows" % label)
            continue
        flat = [i for i in items if i["flat"]]
        print("corpus %s, %d questions, %d subjects (%s excluded: %s)"
              % (label, len(items), items[0]["n"], len(excluded), ", ".join(excluded) or "none"))
        for band in BANDS:
            sel = [i for i in items if i["difficulty_band"] == band]
            if not sel:
                continue
            print("  %-12s %2d questions, %2d answered by everybody or by nobody, "
                  "mean p %.2f, mean D %+.2f"
                  % (band, len(sel), sum(1 for i in sel if i["flat"]),
                     sum(i["p"] for i in sel) / len(sel), sum(i["d"] for i in sel) / len(sel)))
        print("  %d of %d questions separate nobody at all" % (len(flat), len(items)))
        # THE TRAP TABLE HAS TO REACH THE CONSOLE, not only the markdown: CI greps what this prints,
        # and a number that lives only in a generated file is a number nobody checks.
        traps = trap_table(path, items)
        narrow = [t for t in traps if t["trap"] < 2]
        wide = [t for t in traps if t["trap"] >= 2]
        if traps:
            print("  adversarial: %d one-word traps, mean D %s; %d wider, mean D %s"
                  % (len(narrow),
                     ("%+.2f" % (sum(t["d"] for t in narrow) / len(narrow))) if narrow else "-",
                     len(wide),
                     ("%+.2f" % (sum(t["d"] for t in wide) / len(wide))) if wide else "-"))
        report.append({"label": label, "items": items, "excluded": excluded, "traps": traps})
    if not report:
        return 1
    write_md(md, report, shape)
    return 0


def write_md(path, report, shape):
    lines = []
    add = lines.append
    add("# Does every question measure something?")
    add("")
    add("Generated by `items.py`. Do not edit by hand. Analysed in the **%s** phrasing." % shape)
    add("")
    add("A question every subject answers and a question no subject answers carry the same information")
    add("about the differences between subjects: none. This is the item analysis a test gets before")
    add("anyone trusts it - difficulty `p` (the share of subjects that got it right) and discrimination")
    add("`D` (the gap between the top half of subjects by total score and the bottom half).")
    add("")
    for block in report:
        items = block["items"]
        add("## Corpus %s" % block["label"])
        add("")
        add("%d questions, %d subjects. Excluded for leaking state: %s."
            % (len(items), items[0]["n"], ", ".join(block["excluded"]) or "none"))
        add("")
        add("| band | questions | nobody can tell apart | mean p | mean D |")
        add("|---|---|---|---|---|")
        for band in BANDS:
            sel = [i for i in items if i["difficulty_band"] == band]
            if not sel:
                continue
            add("| %s | %d | %d | %.2f | %+.2f |"
                % (band, len(sel), sum(1 for i in sel if i["flat"]),
                   sum(i["p"] for i in sel) / len(sel), sum(i["d"] for i in sel) / len(sel)))
        add("")
        flat = [i for i in items if i["flat"]]
        zero = [i for i in flat if i["p"] == 0.0]
        one = [i for i in flat if i["p"] == 1.0]
        add("**%d of %d questions separate nobody.** %d are answered correctly by every subject and %d"
            % (len(flat), len(items), len(one), len(zero)))
        add("by none of them.")
        add("")
        if one:
            add("Answered by everybody:")
            add("")
            for i in one[:12]:
                add("- `%s`" % i["query"])
            add("")
        if zero:
            add("Answered by nobody:")
            add("")
            for i in zero[:12]:
                add("- `%s`" % i["query"])
            add("")
        traps = block["traps"]
        if traps:
            add("### Is a one-word trap the weakest kind?")
            add("")
            add("The validator warns about adversarial questions whose competitor shares only one word.")
            add("Measured instead of assumed, over %d adversarial items:" % len(traps))
            add("")
            add("| trap width | questions | mean p | mean D |")
            add("|---|---|---|---|")
            for width in sorted(set(t["trap"] for t in traps)):
                sel = [t for t in traps if t["trap"] == width]
                add("| %d word%s | %d | %.2f | %+.2f |"
                    % (width, "" if width == 1 else "s", len(sel),
                       sum(t["p"] for t in sel) / len(sel),
                       sum(t["d"] for t in sel) / len(sel)))
            add("")
            wide = [t for t in traps if t["trap"] >= 2]
            narrow = [t for t in traps if t["trap"] < 2]
            if wide and narrow:
                add("Mean D is %+.2f for %d narrow items and %+.2f for %d wider ones. Two groups of this"
                    % (sum(t["d"] for t in narrow) / len(narrow), len(narrow),
                       sum(t["d"] for t in wide) / len(wide), len(wide)))
                add("size over ten subjects cannot settle the question; what they can do is stop the")
                add("warning from being either ignored or obeyed without a number attached.")
                add("")
    add("## Reading this")
    add("")
    add("A low `p` is not a defect: a question the weaker subjects miss is doing its job. A `p` of 0 or 1")
    add("is, because nothing about the subjects can be learned from it - including the leader, whose")
    add("score those items inflate for everyone equally.")
    add("")
    add("`D` is crude on purpose. With ten subjects a point-biserial correlation wears a false air of")
    add('precision; "the strong subjects get this and the weak ones do not" is what a question is for.')
    add("")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print()
    print("written to %s" % path)


if __name__ == "__main__":
    sys.exit(main())
