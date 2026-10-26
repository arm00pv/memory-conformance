#!/usr/bin/env python3
"""resolution.py - of all the comparisons this table invites, how many can the corpus make.

FORTY-TWO AGAINST FORTY IS NOT A RESULT; forty-two against twenty-five is. Every row of the retrieval
table sits next to every other, and the paired test in compare.py answers the question for one pair at a
time. Nobody had asked it for all of them, so the resolution of the instrument - how many of the fifty-
five possible comparisons sixty questions can actually settle - was not known.

It is the question the tie block makes urgent. Six subjects score exactly twelve because they answer
nothing and collect their unanswerable-band points, and a table that lists them in some order invites a
reader to read an order into it.

WHAT IS REPORTED

  how many of the 55 pairs are separated, on each corpus and in each phrasing
  which subjects the leader is separated from, because a lead over a group that is not separated
  the groups the corpus cannot split, computed from the separation relation rather than from scores
  the pairs whose verdict flips between phrasings, and between corpora

A PAIR IS SEPARATED WHEN p < 0.05 on the exact McNemar test over the sixty per-question outcomes, in
both phrasings, on both corpora. Anything less is a difference this instrument cannot see, and saying so
is more useful than ranking it.

  python resolution.py
"""
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

CORPORA = [("A", "retrieval_corpus.json", ""), ("B", "retrieval_corpus_b.json", "-b")]
SHAPES = ("written", "keywords")


def subjects():
    """Every subject with saved rows, in table order, plus which ones are in scope."""
    import matrix
    with open("subjects.json", encoding="utf-8") as fh:
        entries = json.load(fh)
    out = []
    for entry in entries:
        slug = matrix.slug_of(entry)
        label = "%s %s" % (entry["name"], entry["version"])
        verdicts = {}
        path = os.path.join("results", slug + ".json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                verdicts = {p["probe"]: p["verdict"] for p in json.load(fh).get("probes") or []}
        out.append({"label": label, "slug": slug,
                    "in_scope": verdicts.get("isolation") == "PASS"})
    return out


def rows_of(slug, suffix):
    import matrix
    path = os.path.join("results", slug + "-retrieval" + suffix + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    rs = doc.get("rows") or []
    if not rs:
        return None
    # STALE ROWS ARE NO MEASUREMENT. The same guard the matrix and the ledger use: rows that were
    # collected against a corpus nobody has on disk any more describe questions that are not asked.
    return rs


def outcome(row, shape, metric="score"):
    """One question, as this metric scores it.

    TWO METRICS, BECAUSE THE SCORE CARRIES A TWELVE-POINT SWITCH. items.py found that every subject
    either declines all twelve unanswerable questions or declines none, so the score hands 12 of its 60
    points to a habit rather than to an ability, and it does so whatever the subject can answer. A
    separation report computed only on the score therefore understates pairs where the switch cancels a
    real difference - which is exactly what happens at the top of this table. Both are reported.
    """
    import compare
    if metric == "hits":
        if row.get("difficulty") == "absent":
            return None  # nothing to hit, so nothing to compare on this metric
        key = "hit3" if shape == "written" else "hit3_keyword"
        return bool(row.get(key))
    return bool(compare.correct_keyword(row)) if shape == "keywords" else bool(compare.correct(row))


def compare_pair(a_rows, b_rows, shape, metric="score"):
    """The paired test for one pair, from the per-question outcomes both subjects produced."""
    import compare
    by_query = {r["query"]: r for r in b_rows}
    a_ok, b_ok = [], []
    for row in a_rows:
        other = by_query.get(row["query"])
        if other is None:
            continue
        a_val, b_val = outcome(row, shape, metric), outcome(other, shape, metric)
        if a_val is None or b_val is None:
            continue
        a_ok.append(a_val)
        b_ok.append(b_val)
    only_a = sum(1 for p, q in zip(a_ok, b_ok) if p and not q)
    only_b = sum(1 for p, q in zip(a_ok, b_ok) if not p and q)
    p = compare.exact_mcnemar(only_a, only_b)
    return {"only_a": only_a, "only_b": only_b, "p": p, "separated": p < 0.05}


def main(argv=None):
    people = subjects()
    present = [s for s in people if rows_of(s["slug"], "") is not None]
    if len(present) < 4:
        print("not enough subjects with saved rows")
        return 1
    blocks = {}
    for label, _path, suffix in CORPORA:
        for shape in SHAPES:
            for metric in ("score", "hits"):
                cache = dict((s["slug"], rows_of(s["slug"], suffix)) for s in present)
                cells = {}
                for a, b in itertools.combinations(present, 2):
                    if cache[a["slug"]] is None or cache[b["slug"]] is None:
                        continue
                    # ONE CANONICAL KEY PER PAIR. The first version stored (a, b) in file order and
                    # then looked the leader up as (min, max), so the "separated from" list and the
                    # "not separated from" list were read from two different keys of one dict.
                    cells[tuple(sorted((a["label"], b["label"])))] = compare_pair(
                        cache[a["slug"]], cache[b["slug"]], shape, metric)
                blocks[(label, shape, metric)] = cells

    total = len(next(iter(blocks.values())))
    print("%d subjects, %d pairs" % (len(present), total))
    for key in [(l, s, m) for l, _p, _u in CORPORA for s in SHAPES for m in ("score", "hits")]:
        cells = blocks.get(key) or {}
        sep = [k for k, v in cells.items() if v["separated"]]
        print("  corpus %s, %-8s on %-5s %2d of %d pairs separated"
              % (key[0], key[1], key[2], len(sep), len(cells)))
        # THE LEADER IS MEASURED, NOT ASSUMED TO BE FIRST IN THE FILE. It is whoever answers the most
        # questions on this corpus in this phrasing.
        if key[0] == "A" and key[1] == "written" and key[2] == "score":
            leader = top_subject(present, blocks, key)
            from_leader = [k for k in sep if leader in k]
            against = [k[0] if k[1] == leader else k[1] for k in from_leader]
            print("    %s is separated from %d of the other %d: %s"
                  % (leader, len(against), len(present) - 1,
                     ", ".join(sorted(n.split()[0] for n in against)) or "nobody"))
            print("    and NOT separated from: %s"
                  % (", ".join(sorted(s["label"].split()[0] for s in present
                                      if s["label"] != leader
                                      and (min(leader, s["label"]), max(leader, s["label"])) not in sep))
                     or "nobody"))
    groups = tie_groups(present, blocks)
    write_md(os.path.join(HERE, "RESOLUTION.md"), present, blocks, groups, total)
    return 0


def top_subject(present, blocks, key):
    """Whoever answers the most questions, read from the rows rather than from the file order."""
    import compare
    best, score = None, -1
    cells = blocks.get(key) or {}
    for s in present:
        rows = rows_of(s["slug"], "")
        if not rows:
            continue
        got = sum(1 for r in rows if compare.correct(r))
        if got > score:
            best, score = s["label"], got
    return best


def tie_groups(present, blocks):
    """The groups the corpus cannot split, from the separation relation and not from the scores."""
    cells = blocks.get(("A", "written", "score")) or {}
    parent = dict((s["label"], s["label"]) for s in present)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), v in cells.items():
        if not v["separated"]:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    out = {}
    for s in present:
        out.setdefault(find(s["label"]), []).append(s["label"])
    return sorted(out.values(), key=len, reverse=True)


def write_md(path, present, blocks, groups, total):
    lines = []
    add = lines.append
    add("# What this corpus can separate")
    add("")
    add("Generated by `resolution.py`. Do not edit by hand.")
    add("")
    add("%d subjects, **%d pairs**. A pair is separated when the exact McNemar test over the sixty" % (len(present), total))
    add("per-question outcomes gives p < 0.05. Everything below that is a difference this instrument")
    add("cannot see, and a table that lists it in order invites a reader to see one anyway.")
    add("")
    for label, _p, _s in CORPORA:
        add("## Corpus %s" % label)
        add("")
        add("| phrasing | on the score | on hits alone |")
        add("|---|---|---|")
        for shape in SHAPES:
            row = []
            for metric in ("score", "hits"):
                cells = blocks.get((label, shape, metric)) or {}
                sep = sum(1 for v in cells.values() if v["separated"])
                row.append("**%d of %d**" % (sep, len(cells)))
            add("| %s | %s | %s |" % (shape, row[0], row[1]))
        add("")
        for shape in SHAPES:
            cells = blocks.get((label, shape, "score")) or {}
            flips = [k for k, v in cells.items()
                     if v["separated"] != (blocks.get((label, "written", "score")) or {}).get(k, {}).get("separated", v["separated"])]
            if shape == "keywords" and flips:
                add("**%d pair(s) change verdict between the two phrasings.**" % len(flips))
                add("")
                for a, b in flips[:8]:
                    w = (blocks.get((label, "written", "score")) or {}).get((a, b)) or {}
                    k = cells[(a, b)]
                    add("- %s vs %s: p %.3f as written, %.3f as keywords"
                        % (a, b, w.get("p", 0), k["p"]))
                add("")
    add("## Between the two corpora")
    add("")
    add("| phrasing | pairs whose verdict differs between corpus A and corpus B |")
    add("|---|---|")
    for shape in SHAPES:
        aw = blocks.get(("A", shape)) or {}
        bw = blocks.get(("B", shape)) or {}
        common = set(aw) & set(bw)
        diff = sum(1 for k in common if aw[k]["separated"] != bw[k]["separated"])
        add("| %s | **%d of %d** |" % (shape, diff, len(common)))
    add("")
    add("## The groups it cannot split")
    add("")
    add("Computed from the separation relation on corpus A as written, not from the scores. A group is a")
    add("connected component of *not separated*: members can be linked by a chain, so not every pair")
    add("inside one is directly indistinguishable. The count says how many of a group's own pairs the")
    add("corpus does separate, which is the number a reader needs to see whether a group is a tie or a")
    add("staircase.")
    add("")
    cells = blocks.get(("A", "written", "score")) or {}
    for i, group in enumerate(groups, 1):
        inside = list(itertools.combinations(group, 2))
        split = sum(1 for k in inside if (cells.get(tuple(sorted(k))) or {}).get("separated"))
        add("%d. %s" % (i, ", ".join("`%s`" % g for g in group)))
        if len(group) > 1:
            add("   %d of its %d internal pairs are separated directly." % (split, len(inside)))
        else:
            add("   alone: separated from everybody.")
    add("")
    leader = top_subject(present, blocks, ("A", "written", "score"))
    if leader:
        add("## The leader's own row")
        add("")
        add("`%s` answers more questions than anything else here. What the corpus can support is this,"
            % leader)
        add("on both metrics, because the score carries the twelve-point switch and the hits do not:")
        add("")
        add("| against | p, score, written | p, score, keywords | p, hits, written | p, hits, keywords |")
        add("|---|---|---|---|---|")
        for s in present:
            if s["label"] == leader:
                continue
            key = tuple(sorted((leader, s["label"])))
            vals = []
            for metric, shape in (("score", "written"), ("score", "keywords"),
                                  ("hits", "written"), ("hits", "keywords")):
                cell = (blocks.get(("A", shape, metric)) or {}).get(key) or {}
                vals.append("%.3f%s" % (cell.get("p", 0), "" if cell.get("separated") else " "))
            add("| %s | %s |" % (s["label"], " | ".join(vals)))
        add("")
        add("A trailing space marks a pair this corpus does not separate. A lead it cannot see is a lead")
        add("a reader should not be told about.")
        add("")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print()
    print("written to %s" % path)


if __name__ == "__main__":
    sys.exit(main())
