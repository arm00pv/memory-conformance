#!/usr/bin/env python3
"""morph_sweep.py - the second coordinate, which the distance ladder cannot move.

THE LADDER MEASURED HOW MUCH OF A RECORD SURVIVES INTO A QUESTION, and it is stuck at 1.00 on the other
axis: every question it builds uses only the record's own words. A person does not ask that way. They ask
"how do I parse those" of a record that says "a parser for", and the word they typed is not in the record
- it is the same word wearing a different ending.

That is the second coordinate, and it can be moved mechanically. Every record description is asked four
times, with a growing share of its long words turned into their plural:
  
  m0  the record's own words                     0% of the question is new vocabulary
  m1  every fourth long word pluralised          about 25%
  m2  every second long word pluralised          about 50%
  m3  every long word pluralised                 100%

No synonym list, no thesaurus, no network. The transformation is a pluraliser with three rules, applied by
position, so the words the question uses are words the record does not contain - which is what a person
types and what every question set in this repository has so far been unable to ask.

  python morph_sweep.py --build
  python morph_sweep.py --measure
  python morph_sweep.py --report
"""
import json
import os
import re
import sys

import questions

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
SOURCE = "retrieval_corpus_real.json"
OUT = "morph_corpus.json"
SUFFIX = "-morph"
BANDS = ("m0", "m1", "m2", "m3")
STRIDE = {"m0": 0, "m1": 4, "m2": 2, "m3": 1}
PER_BAND = 24
LONG4 = re.compile(r"[A-Za-z]{4,}")


def long_words(text):
    return [w.lower() for w in LONG4.findall(text)]


def plural(word):
    """One pluraliser, three rules, stated here so the transformation can be argued with."""
    low = word.lower()
    if low.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    if low.endswith("y") and len(low) > 1 and low[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def inflect(text, stride):
    """Pluralise every stride-th long word, leaving the short ones and the order alone."""
    if not stride:
        return text
    out, n = [], 0
    for word in text.split():
        if LONG4.match(word):
            n += 1
            if n % stride == 0:
                out.append(plural(word))
                continue
        out.append(word)
    return " ".join(out)


def build():
    with open(SOURCE, encoding="utf-8") as fh:
        real = json.load(fh)
    records = real["records"]
    descs = []
    for r in records:
        desc = r["text"].split(" Version ")[0].strip()
        if len(long_words(desc)) >= 5:
            descs.append((r["id"], desc))
    if len(descs) < PER_BAND:
        raise SystemExit("only %d usable descriptions" % len(descs))
    step = max(1, len(descs) // PER_BAND)
    picked = descs[::step][:PER_BAND]

    drafts = []
    for name, desc in picked:
        for band in BANDS:
            text = inflect(desc, STRIDE[band])
            if long_words(text):
                drafts.append({"query": text, "expect": name, "difficulty": band})
    # THE SAME RULE AS EVERY OTHER CORPUS: a question two records answer equally is not a question. Two
    # packages with one description collide at every band, pluralised or not.
    queries, repeated = questions.once(drafts)
    desc_of = dict(picked)
    overlap = dict((b, []) for b in BANDS)
    for q in queries:
        want = set(long_words(q["query"]))
        have = set(long_words(desc_of[q["expect"]]))
        # THE COORDINATE BEING MOVED: the share of the question's long words that the record does not
        # contain. At m0 it should be zero; at m3 it should be everything the pluraliser could change.
        overlap[q["difficulty"]].append(1.0 - len(want & have) / float(len(want)))

    doc = {"why": ("The real package descriptions asked with a growing share of their long words "
                   "pluralised. The transformation is a three-rule pluraliser applied by position, so the "
                   "question uses words the record does not contain - the one thing the distance ladder "
                   "cannot produce."),
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
        s = overlap[band]
        if s:
            print("  %s: %d questions, median %.2f of the question is vocabulary the record lacks"
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
        print("morphology: %s ..." % label, flush=True)
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


def curve(rows):
    out = {}
    for band in BANDS:
        sel = [r for r in rows if r.get("difficulty") == band]
        if sel:
            out[band] = {"n": len(sel),
                         "hit3": sum(1 for r in sel if r.get("hit3")),
                         "hit1": sum(1 for r in sel if r.get("hit1"))}
    return out


def curves():
    import resolution
    out = {}
    for s in resolution.subjects():
        rows = rows_of(s["slug"])
        if rows:
            out[s["label"]] = curve(rows)
    return out


def report():
    got = curves()
    if len(got) < 4:
        raise SystemExit("not enough subjects measured on the morphology sweep")
    lines = []
    add = lines.append
    add("# Does a memory survive a plural")
    add("")
    add("Generated by " + BT + "morph_sweep.py" + BT + ". Do not edit by hand.")
    add("")
    add("The distance ladder moves one coordinate: how much of a record survives into a question. Its other")
    add("coordinate is fixed at 1.00, because a question built by deleting words uses only the record's own")
    add("words - and a person does not ask that way. This moves the other one. Every description is asked")
    add("four times with a growing share of its long words pluralised, so the question contains words the")
    add("record does not:")
    add("")
    with open(OUT, encoding="utf-8") as fh:
        doc = json.load(fh)
    by_id = dict((r["id"], r["text"].split(" Version ")[0]) for r in doc["records"])
    shares = dict((b, []) for b in BANDS)
    for q in doc["queries"]:
        have = set(long_words(by_id.get(q["expect"], "")))
        want = set(long_words(q["query"]))
        if want:
            shares[q["difficulty"]].append(1.0 - len(want & have) / float(len(want)))
    add("| band | the question | vocabulary the record lacks, measured |")
    add("|---|---|---|")
    names = {"m0": "the record's own words", "m1": "every fourth long word pluralised",
             "m2": "every second long word pluralised", "m3": "every long word pluralised"}
    for band in BANDS:
        s = shares[band]
        add("| %s | %s | %.2f |" % (band, names[band], sorted(s)[len(s) // 2] if s else 0))
    add("")
    add("## The curves")
    add("")
    add("hit@3 out of the questions in each band. A subject that stems, or that indexes meaning rather than")
    add("characters, should hold. A subject that matches substrings should fall away immediately.")
    add("")
    add("| subject | " + " | ".join(BANDS) + " | first drop |")
    add("|" + "---|" * (len(BANDS) + 2))
    order = sorted(got, key=lambda k: -((got[k].get("m0") or {}).get("hit3") or 0))
    for name in order:
        c = got[name]
        base = (c.get("m0") or {}).get("hit3") or 0
        cells, first_drop = [], "-"
        for band in BANDS:
            cell = c.get(band)
            cells.append("%d/%d" % (cell["hit3"], cell["n"]) if cell else "-")
            if first_drop == "-" and cell and base:
                if cell["hit3"] * 2 < base:
                    first_drop = band
        add("| " + BT + name + BT + " | " + " | ".join(cells) + " | " + first_drop + " |")
    add("")
    add("## The two coordinates together")
    add("")
    add("A question can lose the record's words in two independent ways: by asking about less of it, and by")
    add("asking in vocabulary it does not contain. Both are measured now, on the same records.")
    add("")
    add("| sweep | of the record, in the question | of the question, in the record |")
    add("|---|---|---|")
    add("| distance, d0 to d4 | 1.00 down to 0.29 | **1.00 at every band** |")
    m0 = sorted(shares["m0"])[len(shares["m0"]) // 2] if shares["m0"] else 0
    m3 = sorted(shares["m3"])[len(shares["m3"]) // 2] if shares["m3"] else 0
    add("| morphology, m0 to m3 | **1.00 at every band** | %.2f down to %.2f |" % (1.0 - m0, 1.0 - m3))
    add("")
    add("Neither sweep alone is what a person writes. A real question changes both at once, and the two")
    add("failure modes they isolate are different ones: losing the record's words is a recall problem, and")
    add("using its own words is a normalisation problem.")
    add("")
    add("## What this does not settle")
    add("")
    add("Pluralisation is one morphological operation and the easiest one there is: the stem is intact and")
    add("two letters have changed. A subject that fails here fails the cheapest case of new vocabulary, which")
    add("makes this a floor rather than a measure of understanding - the same role the hard band of the real")
    add("corpus plays. What it does establish is that the second coordinate can be moved at all without a")
    add("writer, a thesaurus or a network connection.")
    add("")
    path = os.path.join(HERE, "MORPHOLOGY.md")
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
