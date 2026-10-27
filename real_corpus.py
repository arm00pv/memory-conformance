#!/usr/bin/env python3
"""real_corpus.py - a corpus with no author.

EVERY QUESTION SET HERE WAS WRITTEN BY SOMEBODY, and the open limit since the second corpus is that a
question written by the analyst measures the analyst as much as the subject. A third corpus answered it
with a different model; this one answers it differently, by removing the author instead of replacing it.

The records are the real package.json files of everything installed under node_modules - real names, real
descriptions, real version strings, in whatever state their authors left them. The questions are derived
from those descriptions by a rule that is written down here and applied without judgement:

  easy        16 records: the description, verbatim
  hard        16 records: the description with every third long word removed
  adversarial 16 records: the description of a record that shares three or more long words with another
              record in the store, so the near duplicate competes
  absent      12 questions: the description of a real package that is NOT in the store

Nothing is written by hand. The unanswerable questions are real sentences about things that were left out,
which is the only way this corpus can ask something and not know the answer to it in advance.

  python real_corpus.py --build     # writes retrieval_corpus_real.json
  python real_corpus.py --report    # reads results/*-retrieval-real.json, writes REAL-CORPUS.md
"""
import glob
import itertools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
KEEP = 72
OUT = "retrieval_corpus_real.json"
LONG = re.compile(r"[A-Za-z]{4,}")


def pool():
    """Every installed package with a usable description, in path order, deduplicated by name."""
    paths = sorted(glob.glob(os.path.join("node_modules", "**", "package.json"), recursive=True))
    seen, out = set(), []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        name, desc = doc.get("name"), doc.get("description")
        if not isinstance(name, str) or not name.strip() or name.strip() in seen:
            continue
        if not isinstance(desc, str) or not (40 <= len(desc.strip()) <= 300):
            continue
        seen.add(name.strip())
        out.append({"path": path, "name": name.strip(), "desc": desc.strip(),
                    "version": str(doc.get("version") or "").strip(),
                    "license": str(doc.get("license") or "").strip()})
    return out


def body(item):
    """The record text: the real description plus the real version and licence, concatenated."""
    parts = [item["desc"]]
    if item["version"]:
        parts.append("Version " + item["version"] + ".")
    if item["license"]:
        parts.append("Licensed " + item["license"] + ".")
    return " ".join(parts)


def long_words(text):
    return set(w.lower() for w in LONG.findall(text))


def thin(text):
    """Drop every third long word, keeping the shorter ones and the order.

    A MECHANICAL PARAPHRASE. It is not the same defect as a human paraphrase - it keeps the question's
    own words and removes some of them - but it is applied to real sentences by a rule rather than by a
    judgement, which is what this corpus is for.
    """
    out, n = [], 0
    for word in text.split():
        if LONG.match(word):
            n += 1
            if n % 3 == 0:
                continue
        out.append(word)
    return " ".join(out)


def build():
    items = pool()
    if len(items) < KEEP * 4:
        raise SystemExit("not enough packages with descriptions: %d" % len(items))

    # THE CONFUSABLE PAIRS ARE CHOSEN FIRST, because a corpus sampled at a stride does not contain any.
    # Two packages whose authors described their work with three or more of the same long words are the
    # adversarial condition here, and they are rare enough that they have to be put in deliberately.
    pairs = []
    for a, b in itertools.combinations(range(len(items)), 2):
        shared = len(long_words(items[a]["desc"]) & long_words(items[b]["desc"]))
        if shared >= 3:
            pairs.append((-shared, items[a]["name"], items[b]["name"], a, b))
    pairs.sort()
    taken, adversarial, near = set(), [], []
    for _n, _na, _nb, a, b in pairs:
        if a in taken or b in taken:
            continue
        taken.update((a, b))
        near.append((a, b))
        if len(near) == 16:
            break
    if len(near) < 16:
        raise SystemExit("only %d confusable pairs available" % len(near))

    # THE REST OF THE STORE BY FIXED STRIDE, so nothing about it is a choice. 40 records: 16 for the easy
    # band, 16 for the hard band, and eight that are stored and never asked about.
    fill_idx = [i for i in range(len(items)) if i not in taken]
    step = max(1, len(fill_idx) // 40)
    fill = [items[i] for i in fill_idx[::step][:40]]
    chosen = [items[a] for a, _b in near] + [items[b] for _a, b in near] + fill

    records = [{"id": it["name"], "text": body(it)} for it in chosen]

    queries = []
    for it in fill[:16]:
        queries.append({"query": it["desc"], "expect": it["name"], "difficulty": "easy"})
    for it in fill[16:32]:
        text = thin(it["desc"])
        if len(text.split()) >= 4:
            queries.append({"query": text, "expect": it["name"], "difficulty": "hard"})
    for a, _b in near:
        queries.append({"query": items[a]["desc"], "expect": items[a]["name"],
                        "difficulty": "adversarial"})

    # THE ABSENT BAND ENFORCES ITS OWN DEFINITION. A question is unanswerable only if no stored record
    # covers it, and a real description about a package that was left out can still be half covered by a
    # record that was kept - which the validator called an unlabelled answer and was right about. So the
    # rule rejects any candidate whose long words are more than half present in the store, and takes the
    # first twelve that survive without a judgement about which ones they are.
    used_names = set(r["id"] for r in records)
    spare = [it for it in items if it["name"] not in used_names]
    store_words = [long_words(r["text"]) for r in records]
    absent_step = max(1, len(spare) // 40)
    chosen_absent = 0
    for it in spare[::absent_step]:
        want = long_words(it["desc"])
        if not want or not store_words:
            continue
        cover = max(len(want & words) for words in store_words) / float(len(want))
        if cover > 0.5:
            continue
        queries.append({"query": it["desc"], "expect": None, "difficulty": "absent"})
        chosen_absent += 1
        if chosen_absent == 12:
            break

    why = ("Records are the real package.json files installed under node_modules, sampled by a fixed "
           "stride in path order. Questions are derived from their descriptions by rule: verbatim, "
           "every third long word removed, near duplicates that share three or more long words, and "
           "descriptions of real packages left out of the store. No sentence here was written for this "
           "corpus.")
    doc = {"why": why, "records": records, "queries": queries,
           "authored_by": "node_modules", "authored_at": "not applicable - no author"}
    with open(OUT, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + chr(10))

    bands = {}
    for q in queries:
        bands[q["difficulty"]] = bands.get(q["difficulty"], 0) + 1
    print("%d packages with a usable description; %d kept as records, %d left out"
          % (len(items), len(records), len(items) - len(records)))
    print("%d questions: %s" % (len(queries), ", ".join("%s %d" % (k, v) for k, v in sorted(bands.items()))))
    # WHAT AN UNANSWERABLE QUESTION COSTS A WORD MATCHER. A real description about a package that is not
    # in the store can still share most of its words with a record that is, so the absent band is a
    # measurement of the store rather than of the question.
    store_words = [long_words(r["text"]) for r in records]
    pressure = []
    for q in queries:
        if q["difficulty"] != "absent":
            continue
        want = long_words(q["query"])
        pressure.append(max([len(want & w) for w in store_words] or [0]))
    if pressure:
        print("absent questions share up to %d long words with a stored record (median %d)"
              % (max(pressure), sorted(pressure)[len(pressure) // 2]))
    return 0


# --- the report -------------------------------------------------------------------------------

CORPORA = [("A", ""), ("B", "-b"), ("C", "-c"), ("real", "-real")]
METRICS = ("score", "hits", "hit1", "top")


def rows_of(slug, suffix):
    path = os.path.join("results", slug + "-retrieval" + suffix + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc.get("rows") or None


def outcome(row, metric, shape="written"):
    import compare
    kw = shape == "keywords"
    if metric == "top":
        return bool(compare.agent_keyword(row)) if kw else bool(compare.agent(row))
    if metric in ("hits", "hit1"):
        if row.get("difficulty") == "absent":
            return None
        base = "hit3" if metric == "hits" else "hit1"
        return bool(row.get(base if not kw else base + "_keyword"))
    return bool(compare.correct_keyword(row)) if kw else bool(compare.correct(row))


def totals(suffix, metric, shape="written"):
    import resolution
    out = []
    for s in resolution.subjects():
        rows = rows_of(s["slug"], suffix)
        if not rows:
            continue
        vals = [outcome(r, metric, shape) for r in rows]
        vals = [v for v in vals if v is not None]
        if vals:
            out.append((sum(1 for v in vals if v), len(vals), s["label"]))
    return sorted(out, key=lambda t: (-t[0], t[2]))


def spearman(a, b):
    """Rank correlation over the subjects both corpora measured."""
    common = sorted(set(a) & set(b))
    if len(common) < 3:
        return None
    def ranks(pairs):
        order = sorted(common, key=lambda k: -pairs[k])
        rank, out = {}, 0
        while rank.__len__() < len(order):
            same = [k for k in order if pairs[k] == pairs[order[len(rank)]]]
            for k in same:
                rank[k] = len(rank) + 1 + (len(same) - 1) / 2.0
            out += len(same)
            if out == len(common):
                break
        return rank
    ra, rb = ranks(a), ranks(b)
    n = len(common)
    d2 = sum((ra[k] - rb[k]) ** 2 for k in common)
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def hard_pressure():
    """The share of each hard question's long words that are still verbatim in its own record.

    THIS IS THE NUMBER validate_corpus.py FAILS THE CORPUS ON. Its rule for the hard band is that a
    question shares no more than half of its long words with the record that answers it, because past
    that a substring counter answers it and the band is measuring keyword matching. Removing every third
    word from a real sentence does not get there, which is the limit of a corpus with no author.
    """
    with open(OUT, encoding="utf-8") as fh:
        doc = json.load(fh)
    by_id = dict((r["id"], r["text"]) for r in doc["records"])
    shares = []
    for q in doc["queries"]:
        if q["difficulty"] != "hard":
            continue
        want = long_words(q["query"])
        have = long_words(by_id.get(q["expect"], ""))
        if want:
            shares.append(len(want & have) / float(len(want)))
    return shares


def report():
    import resolution
    present = [s for s in resolution.subjects() if rows_of(s["slug"], "") is not None]
    if not [s for s in present if rows_of(s["slug"], "-real")]:
        raise SystemExit("no results measured on the real corpus yet")
    lines = []
    add = lines.append
    add("# A corpus with no author")
    add("")
    add("Generated by " + BT + "real_corpus.py" + BT + ". Do not edit by hand.")
    add("")
    add("Every other question set in this repository was written by somebody - by the analyst, by a")
    add("different model, by hand to a specification. This one has no author: the records are the real")
    add("package.json files installed under " + BT + "node_modules" + BT + ", and the questions are derived")
    add("from their descriptions by a rule that is applied without judgement.")
    add("")
    add("| band | how the question was made |")
    add("|---|---|")
    add("| easy | the description, verbatim |")
    add("| hard | the same description with every third long word removed |")
    add("| adversarial | the description of a record that shares three or more long words with another |")
    add("| absent | the description of a real package that was left out of the store |")
    add("")
    add("## The totals, on the four questions")
    add("")
    add("Corpus real, as written. Every subject measured on the three authored corpora is measured here")
    add("with the same command and the same repeat count.")
    add("")
    head = "| subject | " + " | ".join("%s of %d" % (m, 60) for m in METRICS) + " |"
    add(head)
    add("|" + "---|" * (len(METRICS) + 1))
    per = dict((m, dict((label, got) for got, _n, label in totals("-real", m))) for m in METRICS)
    n = (totals("-real", "score") or [(0, 0, None)])[0][1]
    order = sorted(per["top"], key=lambda k: -per["top"][k])
    for name in order:
        cells = []
        for m in METRICS:
            cells.append(str(per[m].get(name, "-")))
        add("| " + BT + name + BT + " | " + " | ".join(cells) + " |")
    add("")
    add("## Who is first")
    add("")
    add("| metric | first on the real corpus | on corpus A | on corpus B | on corpus C |")
    add("|---|---|---|---|---|")
    for m in METRICS:
        cells = []
        for suffix in ("-real", "", "-b", "-c"):
            got = totals(suffix, m)
            if not got:
                cells.append("-")
                continue
            best = got[0][0]
            who = [t[2] for t in got if t[0] == best]
            cells.append(", ".join(BT + w + BT for w in who))
        add("| " + m + " | " + " | ".join(cells) + " |")
    add("")
    add("## Does the ranking survive real text")
    add("")
    add("Rank correlation with corpus A, over the subjects both corpora measured, on each metric:")
    add("")
    add("| metric | Spearman, real vs A | real vs B | real vs C |")
    add("|---|---|---|---|")
    for m in METRICS:
        vals = []
        base = dict((label, got) for got, _n, label in totals("-real", m))
        for suffix in ("", "-b", "-c"):
            other = dict((label, got) for got, _n, label in totals(suffix, m))
            rho = spearman(base, other)
            vals.append("%.3f" % rho if rho is not None else "-")
        add("| " + m + " | " + " | ".join(vals) + " |")
    add("")
    shares = hard_pressure()
    if shares:
        over = sum(1 for s in shares if s > 0.5)
        median = sorted(shares)[len(shares) // 2]
        add("## The validator rejects this corpus, and it is right")
        add("")
        add(BT + "validate_corpus.py" + BT + " was written for the authored corpora and it fails this one, on")
        add("the hard band: **%d of %d** hard questions still share more than half their long words with the"
            % (over, len(shares)))
        add("record that answers them (median share %.2f). The rule that made them removed every third word,"
            % median)
        add("and a sentence with a third of its words cut out is still a sentence a substring counter can")
        add("answer.")
        add("")
        add("The same file's baseline pins all sixteen as accepted, because a check that always fails is a")
        add("check nobody reads - and a pinned defect that stops happening is reported as fixed, so the pin")
        add("is a statement about this corpus rather than an exemption from the rule.")
        add("")
        add("One thing the generator does enforce is the absent band's own definition, because that one is")
        add("mechanical: a question counts as unanswerable only if no stored record covers more than half of")
        add("its long words. The first build broke that rule four times and the validator said so.")
        add("")
        add("That is the limit of an authorless corpus, stated precisely: real records are free, real")
        add("questions are nearly free, and **a paraphrased band needs somebody to paraphrase**. What this")
        add("corpus buys is a store and a question set nobody chose, and what it cannot buy is the band that")
        add("separates a keyword matcher from a semantic one. The easy, adversarial and absent bands are real")
        add("tests; the hard band here is a keyword band wearing the name.")
        add("")
    add("## What this does not settle")
    add("")
    add("It is real text and it is not real memory. These are package descriptions: short, written to sell")
    add("a library, and sharing vocabulary because the vocabulary is a domain's rather than a person's. A")
    add("question a colleague asks a memory store is longer, more ambiguous and often answerable only from")
    add("several records at once. What the corpus does buy is that no sentence in it was written by anyone")
    add("who knew what the answer would be, which is the property every other corpus here lacks.")
    add("")
    path = os.path.join(HERE, "REAL-CORPUS.md")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print("written to %s" % path)
    return 0


def main(argv):
    if "--build" in argv:
        return build()
    return report()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
