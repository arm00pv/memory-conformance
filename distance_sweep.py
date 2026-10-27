#!/usr/bin/env python3
"""distance_sweep.py - how much paraphrase does a memory survive.

THE FOUR CORPORA DISAGREE AND THE DISAGREEMENT IS ONE NUMBER. On the authored corpora server-memory
answers nothing; on real text it answers 33 of 48. On the authored corpora memory-mcp-1file leads; on real
text it is fifth. Nothing about the subjects moved. The questions did: the authored corpora paraphrase and
the real corpus asks with the record's own words.

So the difference is not four question sets, it is one axis - the distance between a question and the text
that answers it - and every corpus so far has sat at a single point on it. This measures the axis.

FIVE DISTANCES, ONE SET OF RECORDS. From the real package descriptions, a graduated ladder that keeps a
declared fraction of each record's long words:

  d0  every word                          1.00 of them
  d1  every third long word removed       about 0.67
  d2  every second long word removed      about 0.50
  d3  every third long word kept          about 0.33
  d4  the first two long words kept, in a question-shaped sentence

The ladder is applied by rule to real text, so no question is written by anybody and the only thing
varying between bands is how much of the answer survives into the question. The share actually achieved is
computed and reported rather than assumed.

  python distance_sweep.py --build     # writes retrieval_corpus_distance.json
  python distance_sweep.py --measure   # runs every subject over it
  python distance_sweep.py --report    # writes DISTANCE.md
"""
import json
import os
import subprocess
import sys

import questions

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
SOURCE = "retrieval_corpus_real.json"
# NOT NAMED retrieval_corpus*.json, because it is not one. The corpus validator globs that pattern and
# applies the authored corpora's band rules to it - easy, hard, adversarial, absent - and this is a ladder
# of distances with different rules of its own. A file name is not a type, but it is what the tool reads.
OUT = "distance_corpus.json"
RECORDS = 72
PER_BAND = 24
SUFFIX = "-dist"
BANDS = ("d0", "d1", "d2", "d3", "d4")
LONG4 = __import__("re").compile(r"[A-Za-z]{4,}")


def long_words(text):
    return [w.lower() for w in LONG4.findall(text)]


def keep_every(text, k, drop=False):
    """Keep every k-th long word, or drop every k-th, leaving the short words in place."""
    out, n = [], 0
    for word in text.split():
        if LONG4.match(word):
            n += 1
            if (n % k == 0) if drop else (n % k != 0):
                continue
        out.append(word)
    return " ".join(out)


def first_words(text, n):
    out, taken = [], 0
    for word in text.split():
        if LONG4.match(word):
            taken += 1
            if taken > n:
                break
        out.append(word)
    return " ".join(out)


def forms(desc):
    """The five question forms for one record, from furthest to nearest to its own text."""
    return {
        "d0": desc,
        "d1": keep_every(desc, 3, drop=True),
        "d2": keep_every(desc, 2, drop=True),
        "d3": keep_every(desc, 3),
        "d4": "tell me about " + first_words(desc, 2),
    }


def build():
    with open(SOURCE, encoding="utf-8") as fh:
        real = json.load(fh)
    records = real["records"][:RECORDS]
    by_id = dict((r["id"], r["text"]) for r in records)
    # THE QUESTION IS DERIVED FROM THE DESCRIPTION ONLY. The record text also carries the version and the
    # licence, which are not what a question about the package would ask - and a version string surviving
    # into a question would be a keyword match dressed as a paraphrase.
    descs = []
    for r in records:
        desc = r["text"].split(" Version ")[0].strip()
        if len(long_words(desc)) >= 6:
            descs.append((r["id"], desc))
    if len(descs) < PER_BAND:
        raise SystemExit("only %d descriptions with six long words" % len(descs))
    step = max(1, len(descs) // PER_BAND)
    picked = descs[::step][:PER_BAND]

    drafts = []
    for name, desc in picked:
        for band, text in forms(desc).items():
            if long_words(text):
                drafts.append({"query": text, "expect": name, "difficulty": band})
    # A QUESTION TWO RECORDS ANSWER EQUALLY IS NOT A QUESTION. At the far distances the forms collapse -
    # "tell me about AWS credential provider" is four packages at once - and questions.py drops every copy
    # rather than grading either answer wrong.
    queries, repeated = questions.once(drafts)
    desc_of = dict(picked)
    shares = dict((b, []) for b in BANDS)
    for q in queries:
        want = set(long_words(q["query"]))
        have = set(long_words(desc_of[q["expect"]]))
        # THE SHARE IS OF THE RECORD, NOT OF THE QUESTION. A question built by deleting words from a
        # record shares every one of its own words with that record by construction, so measuring the
        # other way round reports 1.00 at every distance and describes nothing.
        shares[q["difficulty"]].append(len(want & have) / float(len(have)))

    doc = {"why": ("The real package descriptions, asked at five graduated distances. Each form keeps a "
                   "declared fraction of the record's own long words, applied by rule, so the only thing "
                   "that varies between bands is how much of the answer survives into the question."),
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
    for band in BANDS:
        s = shares[band]
        if s:
            print("  %s: %d questions, median share of the record's long words %.2f"
                  % (band, len(s), sorted(s)[len(s) // 2]))
    return 0


def measure(argv):
    import matrix
    repeat = 2
    only = None
    for a in argv:
        if a.startswith("--repeat="):
            repeat = max(1, int(a.split("=", 1)[1]))
        elif a.startswith("--only="):
            only = a.split("=", 1)[1]
    matrix.RETRIEVAL_REPEAT = repeat
    with open("subjects.json", encoding="utf-8") as fh:
        subjects = json.load(fh)
    for entry in subjects:
        label = "%s %s" % (entry["name"], entry["version"])
        if only and only not in label:
            continue
        print("distance: %s ..." % label, flush=True)
        got = matrix.run_retrieval(entry, int(entry.get("timeout", 90)), cases=OUT, suffix=SUFFIX)
        if got:
            print("   %s" % json.dumps(got.get("all") or {}), flush=True)
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


def band_shares():
    """The share of the record that survives into each band's questions, measured from the built corpus."""
    with open(OUT, encoding="utf-8") as fh:
        doc = json.load(fh)
    by_id = dict((r["id"], r["text"].split(" Version ")[0]) for r in doc["records"])
    out = dict((b, []) for b in BANDS)
    for q in doc["queries"]:
        have = set(long_words(by_id.get(q["expect"], "")))
        want = set(long_words(q["query"]))
        if have:
            out[q["difficulty"]].append(len(want & have) / float(len(have)))
    return dict((b, (sorted(v)[len(v) // 2] if v else None)) for b, v in out.items())


def authored_shares():
    """Where each corpus sits on this axis, measured the same way as the ladder.

    THE FOUR CORPORA WERE NEVER DISAGREEING ABOUT SUBJECTS. They were sitting at different points on one
    axis, and this puts them on it: the share of the answering record's long words that a question
    actually contains.
    """
    out = {}
    for name, path in (("A", "retrieval_corpus.json"), ("B", "retrieval_corpus_b.json"),
                       ("C", "retrieval_corpus_c.json"), ("real", SOURCE)):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        by_id = dict((r["id"], r["text"]) for r in doc.get("records") or [])
        shares = []
        for q in doc.get("queries") or []:
            if not q.get("expect"):
                continue
            have = set(long_words(by_id.get(q["expect"], "")))
            want = set(long_words(q["query"]))
            if have:
                shares.append(len(want & have) / float(len(have)))
        grounded = []
        for q in doc.get("queries") or []:
            if not q.get("expect"):
                continue
            have = set(long_words(by_id.get(q["expect"], "")))
            want = set(long_words(q["query"]))
            if want:
                grounded.append(len(want & have) / float(len(want)))
        if shares:
            out[name] = (sorted(shares)[len(shares) // 2], len(shares),
                         sorted(grounded)[len(grounded) // 2] if grounded else None)
    return out


def curve(rows):
    """Hit@3 and hit@1 per distance band, for one subject."""
    out = {}
    for band in BANDS:
        sel = [r for r in rows if r.get("difficulty") == band]
        if not sel:
            continue
        out[band] = {"n": len(sel),
                     "hit3": sum(1 for r in sel if r.get("hit3")),
                     "hit1": sum(1 for r in sel if r.get("hit1"))}
    return out


def separations(bands=("d0", "d1", "d2", "d3", "d4")):
    """How many pairs the sweep separates at each distance, on the questions asked at that distance.

    THE ANSWER IS NOT THE OBVIOUS ONE. Asking a record's own words back at it is so easy that four
    subjects tie at the ceiling on the first band, so the nearest distance separates FEWER pairs than a
    middle one. A corpus placed at the near end is not a strict instrument; it is an instrument with no
    room at the top.
    """
    import itertools
    import compare
    import resolution
    people = [(s["label"], s["slug"]) for s in resolution.subjects()]
    rows = dict((label, rows_of(slug)) for label, slug in people)
    rows = dict((k, v) for k, v in rows.items() if v)
    out = {}
    for band in bands:
        sep = total = 0
        for a, b in itertools.combinations(sorted(rows), 2):
            by = dict((r["query"], r) for r in rows[b] if r.get("difficulty") == band)
            pairs = [(r, by[r["query"]]) for r in rows[a]
                     if r.get("difficulty") == band and r["query"] in by]
            if not pairs:
                continue
            x = [bool(p.get("hit3")) for p, _q in pairs]
            y = [bool(q.get("hit3")) for _p, q in pairs]
            only_a = sum(1 for m, n in zip(x, y) if m and not n)
            only_b = sum(1 for m, n in zip(x, y) if n and not m)
            total += 1
            if compare.exact_mcnemar(only_a, only_b) < 0.05:
                sep += 1
        out[band] = (sep, total)
    return out


def reach(curve_of):
    """The furthest distance at which a subject still answers half of what it answered verbatim."""
    base = (curve_of.get("d0") or {}).get("hit3")
    if not base:
        return None
    for band in reversed(BANDS):
        got = (curve_of.get(band) or {}).get("hit3") or 0
        if got * 2 >= base:
            return band
    return None


def report():
    import resolution
    people = resolution.subjects()
    curves = {}
    for s in people:
        rows = rows_of(s["slug"])
        if rows:
            curves[s["label"]] = curve(rows)
    if len(curves) < 4:
        raise SystemExit("not enough subjects measured on the distance sweep")
    lines = []
    add = lines.append
    add("# How much paraphrase does a memory survive")
    add("")
    add("Generated by " + BT + "distance_sweep.py" + BT + ". Do not edit by hand.")
    add("")
    add("The four corpora disagree, and the disagreement is one axis: how far the question sits from the text")
    add("that answers it. The authored corpora paraphrase; the real one asks with the record's own words. This")
    add("walks that distance in five steps, from a verbatim question to one that keeps two words of the answer,")
    add("using real package descriptions and a rule rather than a writer.")
    add("")
    shares = band_shares()
    add("| band | the question keeps | of the record's long words, measured |")
    add("|---|---|---|")
    add("| d0 | every word | %.2f |" % (shares.get("d0") or 0))
    add("| d1 | two of every three | %.2f |" % (shares.get("d1") or 0))
    add("| d2 | every second | %.2f |" % (shares.get("d2") or 0))
    add("| d3 | one in three | %.2f |" % (shares.get("d3") or 0))
    add("| d4 | the first two, in a question | %.2f |" % (shares.get("d4") or 0))
    add("")
    add("The ladder is measured rather than assumed: the last two steps are close together because a")
    add("description with seven long words leaves two of them to a question, which is a third of the record")
    add("and not a fifth. The curve is read with that compression in mind.")
    add("")
    where = authored_shares()
    if where:
        add("## Where the four corpora sit on this axis")
        add("")
        add("ONE NUMBER IS NOT ENOUGH TO PLACE A QUESTION, and this table needs two. How much of the")
        add("answering record survives into the question is the distance the sweep walks. How much of the")
        add("question is actually drawn from the record is a second coordinate, and the ladder cannot move it:")
        add("a question built by deleting words from a record uses only that record's words, so its second")
        add("coordinate is always 1.00.")
        add("")
        add("| corpus | of the record, in the question | of the question, in the record | answerable questions |")
        add("|---|---|---|---|")
        for name in ("A", "B", "C", "real"):
            if name in where:
                got = where[name]
                add("| %s | %.2f | %.2f | %d |"
                    % (name, got[0], got[2] if got[2] is not None else 0, got[1]))
        add("")
        add("The authored corpora sit low on both coordinates and the real one sits high on the first and at")
        add("1.00 on the second. That is the whole of the disagreement between them, and it also says the")
        add("ladder below is the easy half of the axis: every step of it is still a question made from the")
        add("record's own words, which is a thing no person has ever asked.")
        add("")
    add("## The curves")
    add("")
    add("hit@3 out of the questions in each band, and the band at which each subject stops answering half of")
    add("what it")
    add("it answered verbatim.")
    add("")
    head = "| subject | " + " | ".join("%s" % b for b in BANDS) + " | half at |"
    add(head)
    add("|" + "---|" * (len(BANDS) + 2))
    order = sorted(curves, key=lambda k: (-(curves[k].get("d0") or {}).get("hit3", 0)))
    for name in order:
        c = curves[name]
        cells = []
        for band in BANDS:
            cell = c.get(band)
            cells.append("%d/%d" % (cell["hit3"], cell["n"]) if cell else "-")
        add("| " + BT + name + BT + " | " + " | ".join(cells) + " | %s |" % (reach(c) or "-"))
    add("")
    add("## Where the ranking stops being the same ranking")
    add("")
    add("Every pair of subjects, compared on the same questions in each band: how many pairs this sweep")
    add("separates at the nearest distance, and how many at the furthest.")
    add("")
    for band, (sep, total) in separations().items():
        if total:
            add("- **%s**: %d of %d pairs separated, on %d questions each"
                % (band, sep, total, curves[order[0]].get(band, {"n": 0})["n"]))
    add("")
    add("The nearest distance separates fewer pairs than the middle one, because a question that quotes the")
    add("record is answered by everybody with a substring counter and the top of the table becomes a tie at")
    add("the ceiling. A corpus placed at the near end is not a stricter instrument; it is one with no room")
    add("at the top, which is exactly what the real corpus turned into.")
    add("")
    add("## What this does not settle")
    add("")
    add("A distance sweep is not a paraphrase. Removing words is not the same operation as saying the same")
    add("thing differently, and a subject that reads words will look worse here than one that reads meaning")
    add("only in the sense that its own words are being taken away. What the sweep does buy is a number per")
    add("subject instead of a contradiction between corpora: each of the four question sets is one point on")
    add("these curves, and the disagreement between them is the slope between those points.")
    add("")
    path = os.path.join(HERE, "DISTANCE.md")
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
