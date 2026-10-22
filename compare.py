#!/usr/bin/env python3
"""compare.py - is one subject actually better than another on this corpus?

Comparing two fractions invites a statistical mistake: 22/30 and 13/30 look far apart and their
independent 95% intervals still overlap, because thirty questions is not many. But the SAME thirty
questions are asked of every subject, so the comparison is paired, and the right question is not
"are these proportions different" but "on the questions where they disagree, does one win more often
than the other".

That is McNemar, and it is exact here because the discordant counts are small. The output names the
questions that flipped, so the number can be argued with rather than only believed.

  python compare.py zenbrain memdb
  python compare.py --band=adversarial zenbrain memdb

It reads the reports already under results/, so it never re-runs a subject.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(arg):
    """Find a subject report by name or slug prefix, or by a path to one.

    A prefix is matched rather than a built name because the slug carries the version, and pinning
    "zenbrain" to "zenbrain-0.3.0" in the caller is how a comparison silently runs against the wrong
    version after an upgrade. Two matches is an error, not a coin flip.
    """
    if arg.endswith(".json"):
        path = arg
    else:
        import glob
        hits = sorted(glob.glob(os.path.join(HERE, "results", arg + "*-retrieval.json")))
        hits += sorted(glob.glob(os.path.join(HERE, "results", arg + "-retrieval.json")))
        hits = sorted(set(hits))
        if not hits:
            raise SystemExit("no retrieval report matching %r under results/" % arg)
        if len(hits) > 1:
            raise SystemExit("%r matches several reports, name one of them: %s"
                             % (arg, [os.path.basename(h) for h in hits]))
        path = hits[0]
    if not os.path.isfile(path):
        raise SystemExit("no retrieval report at %s" % path)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["_path"] = os.path.basename(path)
    return doc


def correct(row):
    """One boolean per question, so two subjects can be paired question by question."""
    if row["difficulty"] == "absent":
        # the correct behaviour on a question with no answer is to return nothing
        return not row["answered"]
    return bool(row["hit3"])


def exact_mcnemar(b, c):
    """Two-sided exact McNemar: how surprising is this split, if the two were equally good?"""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / float(2 ** n)
    return min(1.0, 2.0 * tail)


def main(argv):
    band = None
    args = []
    for a in argv:
        if a.startswith("--band="):
            band = a.split("=", 1)[1]
        else:
            args.append(a)
    if len(args) != 2:
        print(__doc__)
        return 2
    da, db = load(args[0]), load(args[1])
    ra, rb = da["rows"], db["rows"]
    if len(ra) != len(rb):
        raise SystemExit("the two reports answered different numbers of questions (%d vs %d)"
                         % (len(ra), len(rb)))
    for x, y in zip(ra, rb):
        if x["query"] != y["query"]:
            raise SystemExit("the reports are not the same corpus: %r vs %r" % (x["query"], y["query"]))
    pairs = [(x, y) for x, y in zip(ra, rb) if band is None or x["difficulty"] == band]
    if not pairs:
        print("no questions in band %r" % band)
        return 2
    a_ok = [correct(x) for x, _y in pairs]
    b_ok = [correct(y) for _x, y in pairs]
    both = sum(1 for p, q in zip(a_ok, b_ok) if p and q)
    neither = sum(1 for p, q in zip(a_ok, b_ok) if not p and not q)
    only_a = sum(1 for p, q in zip(a_ok, b_ok) if p and not q)
    only_b = sum(1 for p, q in zip(b_ok, a_ok) if p and not q)
    n = len(pairs)

    print("%-30s vs %-30s  (%s)" % (da.get("_path", "?"), db.get("_path", "?"),
                                       band or "all bands"))
    print()
    print("  questions                 %d" % n)
    print("  correct for both          %d" % both)
    print("  correct for neither       %d" % neither)
    print("  only %-20s %d" % (args[0] + " correct", only_a))
    print("  only %-20s %d" % (args[1] + " correct", only_b))
    print()
    p = exact_mcnemar(only_a, only_b)
    verdict = ("separated" if p < 0.05 else
               "not separated by this corpus" if only_a or only_b else "identical")
    print("  exact McNemar p = %.4f  -> %s" % (p, verdict))
    if only_a or only_b:
        print()
        print("  the questions that flipped:")
        for x, y in pairs:
            cx, cy = correct(x), correct(y)
            if cx != cy:
                who = args[0] if cx else args[1]
                print("    %-8s %-48s %s" % (x["difficulty"], x["query"][:48], who))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
