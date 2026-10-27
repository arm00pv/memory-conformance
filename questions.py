#!/usr/bin/env python3
"""questions.py - a question two records answer equally well is not a question.

CORPORA BUILT FROM REAL DATA INHERIT A COLLISION. Two packages can carry the same description word for
word - a fork and its original, a client and a server generated from one template - so a corpus that
derives one question per description asks the same words twice with a different expected record. A
subject that returns the other one of the two is graded wrong for being right, and nothing here noticed:
the exam's 300 slots were 288 distinct questions, the morphology sweep's 96 were 88, and the same
collision sits in two more corpora.

THE RULE IS BLUNT ON PURPOSE. If a question text appears more than once in a corpus, none of its copies
belongs in it. Merging the expectations instead - crediting either record - would keep the slot, but then
the slot cannot separate a subject that found the fact from one that found its sibling, and a question
that cannot separate anything is not worth the measurements it costs.

    python questions.py           # every corpus on disk must ask each question once
    python questions.py --list    # and print what is wrong, and where
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)


def unique(items, key):
    """Only the items whose key is shared with nothing else, plus the keys that were dropped.

    Written for question lists, where any item is a dict with a "query": but the item is passed through
    untouched so a builder can carry a parallel share or overlap alongside it and drop the two together.
    """
    counts = {}
    for it in items:
        k = key(it)
        counts[k] = counts.get(k, 0) + 1
    kept = [it for it in items if counts[key(it)] == 1]
    return kept, [k for k, n in counts.items() if n > 1]


def once(queries):
    """The same rule for a plain list of question dicts, which is what four builders hold."""
    return unique(queries, lambda q: q["query"])


def live(path):
    """The question texts a corpus on disk actually asks, for a reader to filter rows against."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return set(q["query"] for q in doc.get("queries") or [])


def corpora():
    """Every corpus file in the repository, authorless and authored, generated and hand-written."""
    out = []
    for pattern in ("*corpus*.json",):
        for path in sorted(glob.glob(pattern)):
            if path == "corpus-known.json":
                continue
            out.append(os.path.basename(path))
    return out


def check(argv):
    verbose = "--list" in argv
    bad = 0
    print("%d corpus file(s) on disk" % len(corpora()))
    for name in corpora():
        with open(name, encoding="utf-8") as fh:
            doc = json.load(fh)
        queries = doc.get("queries") or []
        kept, dropped = once(queries)
        if dropped:
            bad += 1
            print("  FAIL  %s asks %d question text(s) more than once (%d slot(s) that two records answer"
                  % (name, len(dropped), len(queries) - len(kept)))
            print("        equally, so a subject returning the other one is graded wrong)")
            if verbose:
                for text in dropped[:6]:
                    who = sorted(set(str(q.get("expect")) for q in queries if q["query"] == text))
                    print("        %r -> %s" % (text[:70], " and ".join(who)))
    if not bad:
        print("  ok    every corpus asks each question once")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(check(sys.argv[1:]))
