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
  python compare.py --shape=written zenbrain memdb     # one phrasing only
  python compare.py --shape=keywords zenbrain memdb

BOTH PHRASINGS BY DEFAULT, and their verdicts printed together. That is not a decoration: the same
pair of subjects is "not separated" when the questions are asked as written and "separated" when the
same questions are asked as keywords, and a claim that quotes one of those without the other is
quoting whichever one it liked. The exit code is not the verdict - this tool reports, it does not gate.


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


def correct_keyword(row):
    """Correct when the same question is put as a keyword string, from the same saved report."""
    return correct({"difficulty": row["difficulty"],
                    "answered": bool(row.get("answered_keyword")),
                    "hit3": bool(row.get("hit3_keyword"))})


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
    shape = "both"
    for a in argv:
        if a.startswith("--band="):
            band_value = a.split("=", 1)[1]
        elif a.startswith("--shape="):
            shape = a.split("=", 1)[1]
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
    pairs = [(x, y) for x, y in zip(ra, rb)
             if band is None or x["difficulty"] == band]
    if not pairs:
        print("no questions in band %r" % band)
        return 2

    shapes = [shape] if shape in ("written", "keywords") else ["written", "keywords"]
    if "keywords" in shapes and not all("hit3_keyword" in r for r in ra + rb):
        raise SystemExit("these reports were measured without the shape axis; re-run them with"
                         " retrieval.py --shapes (matrix.py does this by default)")

    print("%-30s vs %-30s  (%s)" % (da.get("_path", "?"), db.get("_path", "?"),
                                   band or "all bands"))
    verdicts = {}
    for which in shapes:
        fn = correct if which == "written" else correct_keyword
        a_ok = [fn(x) for x, _y in pairs]
        b_ok = [fn(y) for _x, y in pairs]
        both = sum(1 for p, q in zip(a_ok, b_ok) if p and q)
        neither = sum(1 for p, q in zip(a_ok, b_ok) if not p and not q)
        only_a = sum(1 for p, q in zip(a_ok, b_ok) if p and not q)
        only_b = sum(1 for p, q in zip(b_ok, a_ok) if p and not q)
        pv = exact_mcnemar(only_a, only_b)
        separated = pv < 0.05
        verdicts[which] = separated
        print()
        print("  as %s" % ("written" if which == "written" else "keywords"))
        print("    questions               %d" % len(pairs))
        print("    correct for both        %d" % both)
        print("    correct for neither     %d" % neither)
        print("    only %-18s %d" % (args[0] + " correct", only_a))
        print("    only %-18s %d" % (args[1] + " correct", only_b))
        print("    exact McNemar p = %.4f  -> %s"
              % (pv, "separated" if separated else
                 ("not separated by this corpus" if only_a or only_b else "identical")))
        if len(shapes) == 1 and (only_a or only_b):
            print()
            print("    the questions that flipped:")
            for x, y in pairs:
                cx, cy = fn(x), fn(y)
                if cx != cy:
                    who = args[0] if cx else args[1]
                    print("      %-8s %-48s %s" % (x["difficulty"], x["query"][:48], who))
    if len(shapes) == 2:
        print()
        if verdicts["written"] == verdicts["keywords"]:
            print("  the two phrasings reach the same verdict: %s"
                  % ("separated" if verdicts["written"] else "not separated"))
        else:
            print("  THE PHRASING DECIDES THIS ONE: separated as %s, not separated as %s."
                  % ("keywords" if verdicts["keywords"] else "written",
                     "written" if verdicts["keywords"] else "keywords"))
            print("  Neither number is the answer on its own. Report the pair.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
