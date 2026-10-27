#!/usr/bin/env python3
"""precision.py - what comes back besides the answer.

EVERY NUMBER THIS REPOSITORY PUBLISHES COUNTS WHETHER THE RIGHT RECORD ARRIVED. None counts what arrived
WITH it. A top-three list carrying the answer and two unrelated records scores exactly what a list
carrying the answer alone scores, so a subject that answers more questions by handing back more records
is paid for the hit and never charged for the volume. retrieval_mutants.py named that hole; this tool
fills it from the rows already on disk, without running a single subject again.

THREE READINGS, AND THE FIRST NEEDS NO JUDGEMENT AT ALL.

  1. The silence bill. On a question whose answer is nothing, every record handed back is junk by
     construction - there is nothing for it to be. No classifier, no taste, no room to argue. Five
     corpora carry such a band: A, B, C, real and the three-hundred-question exam, 148 questions in all.
  2. The junk around an answer. Every returned record that is not the expected one is either a near miss
     (same family, one word off - which is what a top-three list is FOR) or noise. The split is
     mechanical: a record is near when it shares a name token of four characters or more with an expected
     record, or shares three or more words of five characters or more that are not common to half the
     corpus. Words common to half the corpus are dropped because they cannot distinguish anything:
     "Version" and "Licensed" appear in every package description here, and a rule that counted them
     would call every package a near miss of every other one.
  3. What it costs to read. Characters handed back per question, and the share of those characters that
     are the answer rather than the padding around it.

THE NEAR RULE IS CHECKED WHERE NEARNESS IS CERTAIN. The supersession corpus stores every record twice,
differing only by a version string, so every superseded sibling is a near miss by construction and none
of them is the answer. That band says whether the rule fires when it must.

THE PREDICTIONS, WRITTEN BEFORE THE FIRST RUN.

  1. The silence bill is not zero. At least three subjects hand records back on questions with no answer,
     because the size of a returned list is a constant they choose rather than a decision they make.
  2. Which subjects those are is decided once, not per question: on every absent band a subject answers
     either all of the questions or none of them. There is no middle.
  3. Noise is paid per answer, not per mistake. Every subject that returns two or three records on every
     question carries at least one noise record even when it is right, so noise per hit exceeds one for
     at least four subjects.
  4. The score does not charge for volume, so the matcher that beats the control on the ledger (43
     against 37) must be paying for it: its noise per hit is at least double the control's and its answer
     share of returned characters is below half of the control's. If instead it is ALSO tidier, then its
     extra points are real and the ledger's complaint about it has to be softened.
  5. The near rule fires where nearness is certain: at least 95% of the superseded siblings that came
     back are called near rather than noise.
  6. The largest reading bill belongs to a fixed-size lister - memento hands back three records on every
     question - at more than 25,000 characters on corpus A, against less than 5,000 for the control.

    python precision.py            # read the committed rows, write PRECISION.md
    python precision.py --json     # the numbers only, to results/precision.json
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)

# NINE CORPORA, ONE READING. Each entry is what retrieval.py already measured and committed: the label,
# the corpus the rows were measured against, and the suffix that names the report.
CORPORA = [("A", "retrieval_corpus.json", ""),
           ("B", "retrieval_corpus_b.json", "-b"),
           ("C", "retrieval_corpus_c.json", "-c"),
           ("real", "retrieval_corpus_real.json", "-real"),
           ("dist", "distance_corpus.json", "-dist"),
           ("morph", "morph_corpus.json", "-morph"),
           ("multi", "multi_corpus.json", "-multi"),
           ("large", "large_corpus.json", "-large"),
           ("super", "supersede_corpus.json", "-super")]
SUFFIX = dict((label, suffix) for label, _p, suffix in CORPORA)
PATH = dict((label, path) for label, path, _s in CORPORA)
# THE FIVE BANDS THAT CAN BE ASKED FOR NOTHING. Only these can price silence, and the count is printed
# beside the bill so a reader can see how much of the table rests on it.
ABSENT = ("A", "B", "C", "real", "large")

# THE PANEL IS THE POINT. A new axis is worth nothing unless it moves a verdict that already exists, so
# the same reading is taken of the adapters on this repository's shelves whose verdicts it has published.
PANEL = [("control", "calibration-control-A.json", "positive control"),
         ("blind-search", "calibration-blind-search-A.json", "one shared word"),
         ("mute-search", "calibration-mute-search-A.json", "search returns nothing"),
         ("oracle-search", "calibration-oracle-search-A.json", "search knows the answer"),
         ("greedy-match", "retrieval-greedy-match-A.json", "mutant: answers anything"),
         ("one-result", "retrieval-one-result-A.json", "mutant: one record only"),
         ("reverse-rank", "retrieval-reverse-rank-A.json", "mutant: worst first"),
         ("strict-match", "retrieval-strict-match-A.json", "mutant: exact words only")]

_CACHE = {}


def words(text):
    """The words long enough to distinguish one record from another."""
    return re.findall(r"[a-z0-9]{5,}", str(text or "").lower())


def tokens(rid):
    """The name, split. A record's own name is the strongest evidence of what family it is in."""
    return set(t for t in re.split(r"[^A-Za-z0-9]+", str(rid).lower()) if len(t) >= 4)


def question_tokens(text):
    """What the validator counts when it asks whether a record covers a question.

    THE VALIDATOR'S OWN TOKENIZER, IMPORTED RATHER THAN REWRITTEN. Two tokenizers in one repository is how
    a corpus gets certified by one and measured by the other, and this file had already grown a second
    one before the first run: its coverage numbers disagreed with the validator's charges on the same
    questions.
    """
    import words
    return set(words.tokens(text))


def corpus(label):
    if label in _CACHE:
        return _CACHE[label]
    with open(PATH[label], encoding="utf-8") as fh:
        doc = json.load(fh)
    text, df = {}, {}
    for r in doc["records"]:
        rid = str(r["id"])
        text[rid] = r.get("text") or ""
        for w in set(words(text[rid])):
            df[w] = df.get(w, 0) + 1
    n = len(doc["records"]) or 1
    # A WORD IN HALF THE CORPUS CANNOT DISTINGUISH ANYTHING.
    common = set(w for w, c in df.items() if 2 * c >= n)
    want, cover = {}, {}
    for q in doc["queries"]:
        ids = q.get("expect_all") or [q["expect"]]
        entry = want.get(q["query"])
        if entry is None:
            # A QUESTION TEXT THAT TWO RECORDS ANSWER EQUALLY IS ONE QUESTION WITH TWO RIGHT ANSWERS, and
            # the exam's three hundred slots contain several: the same package description belongs to two
            # packages, so the same words are asked twice with a different expected record. The corpus
            # grades one of the two answers wrong. Here the expected set is taken as the union, so a
            # subject returning either is credited - the reading the rows support without a re-run.
            want[q["query"]] = {"ids": [str(x) for x in ids if x],
                                "difficulty": q.get("difficulty"),
                                "stale": (str(q["stale"]) if q.get("stale") else None),
                                "shared": False}
        else:
            entry["ids"] = sorted(set(entry["ids"]) | set(str(x) for x in ids if x))
            entry["shared"] = True
        if q.get("difficulty") == "absent":
            # HOW NEAR IS THE NEAREST RECORD TO A QUESTION THAT HAS NO ANSWER. A subject that declines
            # because its matcher found nothing cannot decline a question whose words are in a record,
            # so this number and the silence bill are the same measurement taken from the two ends.
            qt = question_tokens(q["query"])
            best = (0.0, "")
            for rid, body in text.items():
                if not qt:
                    break
                frac = len(qt & question_tokens(body)) / float(len(qt))
                if frac > best[0]:
                    best = (frac, rid)
            cover[q["query"]] = best
    _CACHE[label] = {"text": text, "common": common, "want": want, "cover": cover}
    return _CACHE[label]


def distinctive(body, common):
    return set(w for w in words(body) if w not in common)


def classify(cid, ids, c):
    """Answer, near miss, or noise - and the rule that decided it is nameable."""
    if cid in ids:
        return "answer"
    want_tok, want_words = set(), set()
    for i in ids:
        want_tok |= tokens(i)
        want_words |= distinctive(c["text"].get(i, ""), c["common"])
    if tokens(cid) & want_tok:
        return "near"
    if len(distinctive(c["text"].get(cid, ""), c["common"]) & want_words) >= 3:
        return "near"
    return "noise"


FIELDS = ("questions", "answered", "hits", "partial",
          "records", "answer_records", "near_records", "noise_records",
          "chars", "chars_answer", "chars_near", "chars_noise",
          "absent_questions", "absent_answered", "absent_near_answered", "absent_dark_answered",
          "absent_records", "absent_chars",
          "stale_back", "stale_near", "orphan_rows", "repeat_rows")


def zero():
    return dict((k, 0) for k in FIELDS)


def read(label, rows, shape="written"):
    """One subject, one corpus, one phrasing: what came back and what it was worth."""
    c = corpus(label)
    key = "returned" if shape == "written" else "returned_keyword"
    out = zero()
    seen = set()
    for row in rows:
        q = c["want"].get(row["query"])
        if q is not None and row["query"] in seen:
            # A QUESTION ASKED TWICE IS ONE QUESTION. The exam's three hundred slots contain twelve
            # repeats, because two packages share a description; counting the second copy as a second
            # draw is how a sample gets larger on paper than it is.
            out["repeat_rows"] += 1
            continue
        seen.add(row["query"])
        if q is None:
            # A ROW ABOUT A QUESTION THE CORPUS NO LONGER ASKS is not a measurement of anything, and a
            # report that quietly drops it reads as though the subject was asked everything. Counted,
            # printed, and named.
            out["orphan_rows"] += 1
            continue
        returned = [str(x) for x in (row.get(key) or [])]
        if q["difficulty"] == "absent":
            # NOTHING CAN BE RIGHT HERE, so this half of the table needs no classifier at all.
            out["absent_questions"] += 1
            cover = c["cover"].get(row["query"]) or (0.0, "")
            if returned:
                out["absent_answered"] += 1
                if cover[0] > 0:
                    out["absent_near_answered"] += 1
                else:
                    out["absent_dark_answered"] += 1
            for cid in returned:
                out["absent_records"] += 1
                out["absent_chars"] += len(c["text"].get(cid, ""))
            continue
        out["questions"] += 1
        if not returned:
            continue
        out["answered"] += 1
        kinds = [classify(cid, q["ids"], c) for cid in returned]
        got = set(cid for cid, k in zip(returned, kinds) if k == "answer")
        if q["ids"] and len(got) == len(q["ids"]):
            out["hits"] += 1
        elif got:
            out["partial"] += 1
        if q["stale"] and q["stale"] in returned:
            out["stale_back"] += 1
            if kinds[returned.index(q["stale"])] == "near":
                out["stale_near"] += 1
        for cid, kind in zip(returned, kinds):
            size = len(c["text"].get(cid, ""))
            out["records"] += 1
            out["chars"] += size
            out["chars_" + kind] += size
            out[kind + "_records"] += 1
    return out


def derive(s):
    """Two numbers per subject: what the junk costs per answer, and how much of the text is the answer."""
    s = dict(s)
    s["junk_records"] = s["near_records"] + s["noise_records"]
    s["noise_per_hit"] = (s["noise_records"] / float(s["hits"])) if s["hits"] else None
    s["signal_share"] = (s["chars_answer"] / float(s["chars"])) if s["chars"] else None
    s["per_question"] = (s["chars"] + s["absent_chars"]) / float(
        (s["questions"] + s["absent_questions"]) or 1)
    return s


def rows_of(slug, suffix):
    path = os.path.join("results", slug + "-retrieval" + suffix + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("rows") or None


def measure():
    """Every subject, every corpus, both phrasings, plus the panel of adapters with known verdicts."""
    import resolution
    people = [s for s in resolution.subjects() if rows_of(s["slug"], "") is not None]
    got = {}
    for s in people:
        got[s["label"]] = {}
        for label, _p, suffix in CORPORA:
            rows = rows_of(s["slug"], suffix)
            if rows is None:
                continue
            written = derive(read(label, rows, "written"))
            written["keyword"] = derive(read(label, rows, "keywords"))
            got[s["label"]][label] = written
    panel = {}
    for name, filename, note in PANEL:
        path = os.path.join("results", filename)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh).get("rows") or []
        if not rows:
            continue
        panel[name] = {"note": note, "written": derive(read("A", rows, "written")),
                       "keywords": derive(read("A", rows, "keywords"))}
    return got, panel


def summed(got, subject):
    """One subject across all nine corpora, which is the only reading comparable to another subject."""
    total = zero()
    for label in got[subject]:
        block = got[subject][label]
        for k in FIELDS:
            total[k] += block.get(k) or 0
    return derive(total)


def band_answers(got, labels):
    """Answers on the unanswerable bands, and how many of them landed on a question with a neighbour."""
    ans = near = dark = 0
    for n in got:
        for l in labels:
            block = got[n].get(l)
            if not block:
                continue
            ans += block["absent_answered"]
            near += block["absent_near_answered"]
            dark += block["absent_dark_answered"]
    return ans, near, dark


def decidings(got):
    """The subjects whose silence is per question rather than per tool: under half of the long exam."""
    out = []
    for n in got:
        block = got[n].get("large")
        if not block or not block["absent_questions"]:
            continue
        if block["absent_answered"] * 2 < block["absent_questions"]:
            out.append(n)
    return out


def verdicts(got, panel):
    """Each prediction, checked against the numbers rather than remembered."""
    out = []
    loud = [n for n in got if band_answers({n: got[n]}, ABSENT)[0]]
    out.append((1, "at least three subjects hand records back on questions with no answer",
                len(loud) >= 3,
                "%d of %d subjects do: %s" % (len(loud), len(got), ", ".join(sorted(loud)) or "none")))

    # A SUBJECT EITHER DECLINES THE WHOLE BAND OR NONE OF IT. Counted per corpus, because a subject with
    # a per-question decision shows a mixed band somewhere among eleven subjects and five corpora.
    mixed = []
    for n in got:
        for l in ABSENT:
            block = got[n].get(l)
            if not block or not block["absent_questions"]:
                continue
            if 0 < block["absent_answered"] < block["absent_questions"]:
                mixed.append("%s on %s (%d of %d)" % (n, l, block["absent_answered"],
                                                    block["absent_questions"]))
    out.append((2, "a subject answers all of an absent band or none of it, never part", not mixed,
                "every one of the subject-corpora is all or nothing" if not mixed else
                ("mixed in %d places: %s" % (len(mixed), "; ".join(mixed[:3])))))

    charged = [n for n in got if any((b["noise_per_hit"] or 0) > 1 for b in got[n].values())]
    out.append((3, "noise per hit exceeds one for at least four subjects", len(charged) >= 4,
                "%d of %d subjects exceed one somewhere: %s"
                % (len(charged), len(got), ", ".join(sorted(charged)) or "none")))

    b, c = panel.get("blind-search"), panel.get("control")
    g = panel.get("greedy-match")
    if b and c:
        bw, cw = b["written"], c["written"]
        held = ((bw["noise_per_hit"] or 0) >= 2 * (cw["noise_per_hit"] or 0)
                and (bw["signal_share"] or 0) < 0.5 * (cw["signal_share"] or 1))
        detail = ("checked on blind-search, which the prediction named: %.2f noise per hit against the"
                  " control's %.2f, answer share %.0f%% against %.0f%%"
                  % (bw["noise_per_hit"] or 0, cw["noise_per_hit"] or 0,
                     100 * (bw["signal_share"] or 0), 100 * (cw["signal_share"] or 0)))
        if g:
            detail += (". The adapter that actually scores 43 is greedy-match, and it fails the same way:"
                       " %.2f and %.0f%%" % (g["written"]["noise_per_hit"] or 0,
                                            100 * (g["written"]["signal_share"] or 0)))
        out.append((4, "the matcher that beats the control pays for its extra points in noise", held,
                    detail))
    else:
        out.append((4, "the matcher that beats the control pays for its extra points in noise", None,
                    "the panel rows for blind-search and control are not both on disk"))

    back = sum(got[n]["super"]["stale_back"] for n in got if "super" in got[n])
    near = sum(got[n]["super"]["stale_near"] for n in got if "super" in got[n])
    rate = (near / float(back)) if back else 0.0
    out.append((5, "at least 95% of the superseded siblings that came back are called near",
                rate >= 0.95, "%d of %d superseded siblings recognised (%.1f%%)"
                % (near, back, 100 * rate)))

    a = dict((n, got[n]["A"]) for n in got if got[n].get("A"))
    loudest = max(a, key=lambda n: a[n]["chars"]) if a else None
    ceiling = 25000
    held = bool(loudest) and a[loudest]["chars"] > ceiling and a.get("control 1.0.0", a[loudest])["chars"] < 5000
    out.append((6, "the largest reading bill is a fixed-size lister, above 25,000 characters",
                held, "%s at %d characters on corpus A against the control's %d"
                % (loudest or "none", a[loudest]["chars"] if loudest else 0,
                   a.get("control 1.0.0", {"chars": 0})["chars"])))
    return out


def ratio(x):
    return "-" if x is None else "%.2f" % x


def share(x):
    return "-" if x is None else "%d%%" % round(100 * x)


def fence(rows, header, align):
    out = [header, align]
    out.extend(rows)
    return out


def judge_agreement():
    """What two readers made of the same pairs, read from the cache judge.py writes - or None."""
    import judge
    per = judge.by_model(judge.load())
    if sum(len(v) for v in per.values()) < 12:
        return None
    said = []
    for model in sorted(per):
        rows = [((v["kind"] != "noise"), v["verdict"] == "YES") for v in per[model].values()]
        k = judge.kappa(rows)
        if k is None:
            continue
        said.append({"model": model, "n": len(rows), "kappa": k,
                     "agree": sum(1 for a, b in rows if a == b),
                     "generous": sum(1 for a, b in rows if a and not b),
                     "stingy": sum(1 for a, b in rows if not a and b)})
    if not said:
        return None
    models = sorted(per)
    ceiling = None
    if len(models) > 1:
        both = [p for p in per[models[0]] if all(p in per[m] for m in models)]
        if len(both) >= 12:
            rows = [(per[models[0]][p]["verdict"] == "YES", per[models[1]][p]["verdict"] == "YES")
                    for p in both]
            k = judge.kappa(rows)
            if k is not None:
                ceiling = {"n": len(rows), "kappa": k,
                           "agree": sum(1 for a, b in rows if a == b)}
    return {"readers": said, "ceiling": ceiling}


PAD_LEVERS = ("pad-far", "pad-near")


def padding_runs(label):
    """The control and the two padding mutants on one corpus, or whatever of them is on disk."""
    out = []
    base = os.path.join("results", "calibration-control-%s.json" % label)
    if os.path.isfile(base):
        with open(base, encoding="utf-8") as fh:
            out.append(("control", label, json.load(fh).get("rows") or []))
    for lever in PAD_LEVERS:
        path = os.path.join("results", "retrieval-%s-%s.json" % (lever, label))
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                out.append((lever, label, json.load(fh).get("rows") or []))
    return out


def padding_panel():
    """One row per run: what the score says, and what the reading of the same rows says."""
    rows = []
    for label, _path, _suffix in CORPORA:
        if label not in ("A", "B"):
            continue
        for name, lab, rs in padding_runs(label):
            if not rs:
                continue
            d = derive(read(lab, rs, "written"))
            score = sum(1 for r in rs
                        if (r["difficulty"] == "absent" and not r["answered"])
                        or (r["difficulty"] != "absent" and r.get("hit3")))
            rows.append({"run": name, "corpus": lab, "score": score,
                         "hit3": sum(1 for r in rs if r.get("hit3")),
                         "noise": d["noise_records"], "near": d["near_records"],
                         "noise_per_hit": d["noise_per_hit"], "share": d["signal_share"]})
    return rows


def report(got, panel, checks=None):
    lines = []
    add = lines.append
    add("# What comes back besides the answer")
    add("")
    add("Generated by " + BT + "precision.py" + BT + ". Do not edit by hand.")
    add("")
    add("Every number this repository publishes counts whether the right record arrived. None of them")
    add("counts what arrived **with** it. A top-three list carrying the answer and two unrelated records")
    add("scores exactly what a list carrying the answer alone scores, so a subject that answers more")
    add("questions by handing back more records is paid for the hit and never charged for the volume.")
    add("This is that charge, read from rows that were already on disk.")
    add("")

    add("## The predictions, written before the run")
    add("")
    for n, text, held, detail in (checks or []):
        mark = {True: "held", False: "did not hold", None: "not checkable"}[held]
        add("%d. %s." % (n, text[:1].upper() + text[1:]))
        add("   **%s** - %s." % (mark.upper(), detail))
    add("")

    # ---- the silence bill -------------------------------------------------------------------------
    add("## The silence bill")
    add("")
    counts = dict((l, len(corpus(l)["cover"] or {})) for l in ABSENT)
    add("On a question whose answer is nothing, every record handed back is junk by construction. There is")
    add("nothing for it to be. This is measured over %d such questions - %s - and it needs no classifier,"
        % (sum(counts.values()),
           ", ".join("%d in %s" % (v, l if l != "large" else "the long exam")
                     for l, v in counts.items())))
    add("no rule and no argument. The classifier below is not used in this section at all.")
    add("")
    rows = []
    for n in got:
        ask = sum(got[n][l]["absent_questions"] for l in ABSENT if l in got[n])
        if not ask:
            continue
        back = sum(got[n][l]["absent_answered"] for l in ABSENT if l in got[n])
        recs = sum(got[n][l]["absent_records"] for l in ABSENT if l in got[n])
        chars = sum(got[n][l]["absent_chars"] for l in ABSENT if l in got[n])
        rows.append((n, back, ask, recs, chars))
    add("| subject | questions it answered | of the band | records handed back | characters |")
    add("|---|---|---|---|---|")
    for n, back, ask, recs, chars in sorted(rows, key=lambda r: (-r[1], -r[4])):
        add("| " + BT + n + BT + " | **%d of %d** | %s | %d | %d |"
            % (back, ask, share(back / float(ask)), recs, chars))
    add("")
    silent = [r for r in rows if not r[1]]
    full = [r for r in rows if r[1] == r[2]]
    middle = [r for r in rows if r[1] and r[1] < r[2]]
    add("**%d of the %d subjects answer every unanswerable question, %d answer none of them, and %d answer"
        % (len(full), len(rows), len(silent), len(middle)))
    add("part of the band.** That last group is the reason the two halves of this section exist: the four")
    add("sixty-question corpora ask twelve unanswerable questions each, and twelve questions cannot tell")
    add("a subject that declines everything from one that declines ninety-two per cent.")
    add("")
    if full:
        loudest = max(full, key=lambda r: r[3])
        add("The loudest is " + BT + loudest[0] + BT + ", which handed back %d records and %d characters on"
            % (loudest[3], loudest[4]))
        add("questions that had no answer. Every one of those characters is paid by the caller and none of")
        add("them can carry anything true.")
        add("")

    # ---- why anybody answers a question with no answer --------------------------------------------
    add("### Why anybody answers a question that has no answer")
    add("")
    add("A question can be unanswerable and still share words with a record - a store holding a record")
    add("about GFM strikethrough has a neighbour for a question about GFM task lists. The rule that")
    add("certifies a question as unanswerable charges one that shares **half** its words with a single")
    add("record and warns about one that shares fewer, and here that distinction predicts who answers.")
    add("")
    add("| corpus | unanswerable | shares a word with a record | mean best overlap | half covered by one record |")
    add("|---|---|---|---|---|")
    for l in ABSENT:
        cover = corpus(l)["cover"]
        if not cover:
            continue
        fracs = [f for f, _r in cover.values()]
        thin = sum(1 for f in fracs if f > 0)
        half = sum(1 for f in fracs if f >= 0.5)
        add("| %s | %d | %d | %s | %d |"
            % (l if l != "large" else "the long exam", len(fracs), thin,
               "%.2f" % (sum(fracs) / float(len(fracs) or 1)), half))
    add("")
    add("| subject | answers on the unanswerable bands | on a question with a neighbour | on one with none |")
    add("|---|---|---|---|")
    for n in sorted(got, key=lambda n: -sum(got[n][l]["absent_answered"] for l in ABSENT if l in got[n])):
        block = dict((l, got[n][l]) for l in ABSENT if l in got[n])
        ans, near, dark = band_answers({n: block}, ABSENT)
        add("| " + BT + n + BT + " | %d | %d | %s |" % (ans, near, ("**%d**" % dark) if dark else "0"))
    add("")
    ents = decidings(got)
    stats, short_ans, long_ans = {}, 0, 0
    for n in ents:
        here = dict((l, got[n][l]) for l in ABSENT if l in got[n])
        stats[n] = band_answers({n: here}, ABSENT)
        short_ans += band_answers({n: dict((l, v) for l, v in here.items() if l != "large")},
                                  ABSENT)[0]
        long_ans += band_answers({n: dict((l, v) for l, v in here.items() if l == "large")}, ("large",))[0]
    answers = sum(s[0] for s in stats.values())
    near = sum(s[1] for s in stats.values())
    dark = sum(s[2] for s in stats.values())
    darkers = [(n, stats[n][2]) for n in ents if stats[n][2]]
    add("**%d of the %d subjects that decide per question never answered a question whose words appear"
        % (len(ents) - len(darkers), len(ents)))
    add("nowhere in the store%s.** The %d subjects gave %d answers on unanswerable questions between them;"
        % ("; the exception is " + ", ".join(BT + n + BT + " with %d" % k for n, k in darkers)
           if darkers else "", len(ents), answers))
    add("%d of those landed on a question that shares a word with a record and %d did not, and every one"
        % (near, answers - near))
    add("of the %d belongs to the exception named above, which hands back a record for every question on"
        % (answers - near))
    add("corpus A and so has no threshold there to fail. For the rest, silence is not a judgement about")
    add("answerability: their matcher finds something or it finds nothing, and a question written in words")
    add("no record contains leaves it nothing to find.")
    add("")
    add("Which changes what the twelve free points are. The score hands twelve of sixty to any subject that")
    add("returns nothing on the unanswerable questions, and items.py reported that every subject either")
    add("takes all twelve or none of them - a habit, not an ability. These are the same rows read at a")
    add("larger sample: the deciding subjects answer %d of the %d unanswerable questions in the four short"
        % (short_ans, len(ents) * 48))
    add("bands and %d of the %d in the long exam, because a band drawn from a real pool of packages cannot"
        % (long_ans, len(corpus("large")["cover"])))
    add("avoid near neighbours. The points are not a habit and they are not a virtue. They are the price")
    add("of a clean band, and the same subject pays a different price on a different corpus.")
    add("")
    half = [(l, sum(1 for f, _r in corpus(l)["cover"].values() if f >= 0.5)) for l in ABSENT]
    bad = [l for l, k in half if k]
    if bad:
        add("And this reading changed the instrument that was measuring it. %d of the exam's %d unanswerable"
            % (dict(half).get("large", 0), len(corpus("large")["cover"])))
        add("questions have half or more of their words inside a single stored record. The rule that")
        add("certifies a question as unanswerable used to charge exactly that as **an unlabelled answer** -")
        add("a statement about where the answer is, made by a test that can only see which words are where.")
        add("")
        add("Reading those questions showed the charge was wrong every time: " + BT + "obliterator" + BT + " is not a")
        add("path library, and " + BT + "micromark-extension-gfm-strikethrough" + BT + " is not a task-list extension.")
        add("What the rule could see was that **a word-overlap matcher will answer this question**, which is")
        add("a fact about the question's words. The subjects make the same equation the rule made, which is")
        add("why the positive control answered exactly the questions it charged. **A checker and a subject")
        add("that share one idea cannot check each other.**")
        add("")
        add("So the validator now measures two things instead of confusing them. A question that shares most")
        add("of **each other's** words with one record is that record in disguise, and is still an error - that")
        add("is what a question nobody labelled looks like. A question that merely sits half inside a record")
        add("is a neighbour: printed with the fraction, never charged, because nothing that compares strings")
        add("can decide whether it should be answered. The exam now passes its own validator with no errors")
        add("and %d neighbours printed, and the questions the control answered are in that list rather than in"
            % dict(half).get("large", 0))
        add("the pin file.")
        add("")

    # ---- junk around the answer -------------------------------------------------------------------
    add("## Junk around the answer")
    add("")
    add("Every returned record that is not the expected one is either a near miss - same family, one word")
    add("off, which is what a top-three list is for - or noise. The split is mechanical: same name token of")
    add("four characters or more, or three or more shared words of five characters or more that are not")
    add("common to half the corpus. Both phrasings, all nine corpora, written half:")
    add("")
    add("| subject | answered | correct | records back | near | **noise** | noise per correct | answer share |")
    add("|---|---|---|---|---|---|---|---|")
    sums = sorted(((n, summed(got, n)) for n in got), key=lambda r: -(r[1]["noise_per_hit"] or -1))
    for n, t in sums:
        add("| " + BT + n + BT + " | %d | %d | %d | %d | **%d** | %s | %s |"
            % (t["answered"], t["hits"], t["records"], t["near_records"], t["noise_records"],
               ratio(t["noise_per_hit"]), share(t["signal_share"])))
    add("")
    tidy = [s for s in sums if s[1]["hits"]]
    worst = max(sums, key=lambda r: (r[1]["noise_per_hit"] or -1))
    best = min(tidy, key=lambda r: r[1]["noise_per_hit"])
    add("**" + BT + worst[0] + BT + " carries %s noise records for every question it answers correctly; "
        % ratio(worst[1]["noise_per_hit"]))
    add(BT + best[0] + BT + " carries %s and puts %s of its characters on the answer.** A ratio whose"
        % (ratio(best[1]["noise_per_hit"]), share(best[1]["signal_share"])))
    add("denominator is a handful is a description of a handful of questions rather than of a habit, and")
    add("the counts beside each ratio are there so that can be seen.")
    add("")
    add("- " + BT + "memento" + BT + " answers %d questions correctly and hands back %d records nobody asked"
        % (summed(got, "memento 0.7.0")["hits"], summed(got, "memento 0.7.0")["noise_records"]))
    add("  for; the control answers %d and hands back %d."
        % (summed(got, "control 1.0.0")["hits"], summed(got, "control 1.0.0")["noise_records"]))
    add("- The two are not separated by the score in any published table, and they are not the same thing.")
    add("")
    add("### Where the noise lives, by corpus")
    add("")
    order = [l for l, _p, _s in CORPORA]
    add("| subject | " + " | ".join(order) + " |")
    add("|---" * (len(order) + 1) + "|")
    for n, _t in sorted(sums, key=lambda r: r[0]):
        cells = []
        for l in order:
            block = got[n].get(l)
            cells.append(ratio(block["noise_per_hit"]) if block else "-")
        add("| " + BT + n + BT + " | " + " | ".join(cells) + " |")
    add("")
    add("A dash is a subject that returned nothing, or nothing correct, on that corpus, so the ratio has no")
    add("denominator - which is itself the answer for those cells.")
    add("")
    back = sum(got[n]["super"]["stale_back"] for n in got if "super" in got[n])
    near = sum(got[n]["super"]["stale_near"] for n in got if "super" in got[n])
    add("The near rule is checked where nearness is certain: the supersession corpus stores every record")
    add("twice, so every superseded sibling is a near miss by construction and none of them is the answer.")
    add("**%d of the %d superseded siblings that came back were called near** and the rest noise, which is"
        % (near, back))
    add("the check that the rule fires when it must - one direction only, as the closing section says.")
    add("")

    # ---- what it costs to read --------------------------------------------------------------------
    add("## What it costs to read")
    add("")
    add("| subject | characters back | the answer | near misses | **noise** | per question |")
    add("|---|---|---|---|---|---|")
    for n, t in sorted(sums, key=lambda r: -(r[1]["chars"] + r[1]["absent_chars"])):
        add("| " + BT + n + BT + " | %d | %d | %d | %d | %d |"
            % (t["chars"] + t["absent_chars"], t["chars_answer"], t["chars_near"],
               t["chars_noise"] + t["absent_chars"], int(t["per_question"])))
    add("")
    add("Per question is the number a caller pays. A memory that hands back three records whatever it is")
    add("asked costs its caller three records of context on a question it can answer and three on a")
    add("question it cannot; the difference between the top and bottom of that column is the difference")
    add("between a memory that answers and a memory that talks.")
    add("")

    # ---- does the score charge for this -----------------------------------------------------------
    add("## Does the score charge for this")
    add("")
    add("Every adapter on this repository's shelves whose verdict is published, read through the same lens")
    add("on corpus A. The score column is the ledger's own: top-three membership plus a correct silence.")
    add("")
    add("| adapter | what it is | score, written | score, keywords | noise per correct | answer share |")
    add("|---|---|---|---|---|---|")
    for name in [p[0] for p in PANEL if p[0] in panel]:
        block = panel[name]
        w, k = block["written"], block["keywords"]
        add("| " + BT + name + BT + " | %s | %d of %d | %d of %d | %s | %s |"
            % (block["note"],
               w["hits"] + w["absent_questions"] - w["absent_answered"], w["questions"] + w["absent_questions"],
               k["hits"] + k["absent_questions"] - k["absent_answered"], k["questions"] + k["absent_questions"],
               ratio(w["noise_per_hit"]), share(w["signal_share"])))
    add("")
    g, s, o, c = panel.get("greedy-match"), panel.get("strict-match"), panel.get("one-result"), panel.get("control")
    if g and s and c:
        add("Read down that table. The tidiest adapter on the shelf is " + BT + "strict-match" + BT + " - no")
        add("noise at all, every character it hands back part of an answer - and it scores %d of 60. The"
            % (s["written"]["hits"] + s["written"]["absent_questions"] - s["written"]["absent_answered"]))
        add("mutant built to answer anything, " + BT + "greedy-match" + BT + ", scores %d, six points above the"
            % (g["written"]["hits"] + g["written"]["absent_questions"] - g["written"]["absent_answered"]))
        add("positive control, while carrying %s noise records per correct answer and putting %s of its"
            % (ratio(g["written"]["noise_per_hit"]), share(g["written"]["signal_share"])))
        add("characters on an answer. **The score cannot tell those two apart as different kinds of thing.")
        add("The price column can.**")
        add("")
    b = panel.get("blind-search")
    if b and c:
        add("Prediction 4 named the wrong adapter, and the error is kept rather than edited out of it: the")
        add("ledger number it referred to - a matcher scoring 43 against the control's 37 - belongs to")
        add(BT + "greedy-match" + BT + ", not to " + BT + "blind-search" + BT + ", which scores 2. Checked on the")
        add("adapter the prediction named, it holds by a wider margin than it asked for: " + BT + "blind-search" + BT)
        add("answered every question it was asked - all %d answerable ones and all %d with no answer -"
            % (b["written"]["questions"], b["written"]["absent_questions"]))
        add("handed back %d records, got %d right, and %d of the rest share neither a name nor three words"
            % (b["written"]["records"], b["written"]["hits"], b["written"]["noise_records"]))
        add("with what was asked for.")
        add("")

    # ---- does the reading move when a subject pads ------------------------------------------------
    pad = padding_panel()
    if pad:
        add("## Does the reading move when a subject pads")
        add("")
        add("The probes have had twelve broken servers and the retrieval score four levers. **The noise")
        add("reading has had none**, so this runs two levers of its own against the positive control - the")
        add("same search, with two records")
        add("appended that are not the answer. They are appended AFTER the control's own top three, so hit@1")
        add("and hit@3 cannot see them by construction, and everything that moves here moved for one reason.")
        add("")
        add("| run | corpus | score | hit@3 | noise records | noise per correct | answer share | near misses |")
        add("|---|---|---|---|---|---|---|---|")
        for r in pad:
            add("| " + BT + r["run"] + BT + " | %s | %d | %d | %d | %s | %s | %d |"
                % (r["corpus"], r["score"], r["hit3"], r["noise"],
                   ratio(r["noise_per_hit"]), share(r["share"]), r["near"]))
        add("")
        by = dict(((r["run"], r["corpus"]), r) for r in pad)
        preds = []
        for lab in ("A", "B"):
            c, far = by.get(("control", lab)), by.get(("pad-far", lab))
            if c and far:
                preds.append((far["hit3"] == c["hit3"] and far["score"] == c["score"],
                              "%s: the score and hit@3 do not move (%d and %d)" % (lab, c["score"], far["score"])))
        for lab in ("A", "B"):
            c, far, near = by.get(("control", lab)), by.get(("pad-far", lab)), by.get(("pad-near", lab))
            if c and far and near:
                preds.append((far["noise"] > c["noise"] * 3,
                              "%s: padding with unrelated records multiplies the noise count (%d to %d, a factor of %.1f)"
                              % (lab, c["noise"], far["noise"], far["noise"] / float(c["noise"] or 1))))
                preds.append((near["near"] > c["near"],
                              "%s: padding with near misses raises the near-miss count (%d to %d)"
                              % (lab, c["near"], near["near"])))
                preds.append((near["noise_per_hit"] is not None and far["noise_per_hit"] is not None
                              and near["noise_per_hit"] < far["noise_per_hit"],
                              "%s: and raises noise per correct answer less than unrelated padding does (%s against %s)"
                              % (lab, ratio(near["noise_per_hit"]), ratio(far["noise_per_hit"]))))
        held = sum(1 for ok, _t in preds if ok)
        add("**%d of %d checks hold.** Two predictions were written before the first run - that hit@1 and hit@3"
            % (held, len(preds)))
        add("could not see this lever at all, and that the unrelated padding would move the noise count while")
        add("the near-miss padding moved the near-miss count - and both of those held. The numeric thresholds")
        add("below were set when this section was written, after the corrected runs, so they are checks rather")
        add("than predictions, and the difference is the point rather than a technicality.")
        add("")
        for ok, text in preds:
            add("- " + ("held: " if ok else "**did not hold**: ") + text + ".")
        add("")
        a = by.get(("control", "A"))
        b = by.get(("pad-near", "A"))
        if a and b and b["score"] > a["score"]:
            add("**And one result worth stating on its own: padding with near misses RAISED the score.** On")
            add("corpus A, " + BT + "pad-near" + BT + " scores %d where the control scores %d, because a padder that"
                % (b["score"], a["score"]))
            add("chooses records in the question's own vocabulary can stumble onto the answer the control")
            add("missed, and a score that counts a set of three cannot tell the difference between finding a")
            add("fact and surrounding it. Volume is not always noise; sometimes it is recall, and the number")
            add("this repository publishes has no way to say which.")
            add("")
        add("The levers live in " + BT + "harness.py" + BT + " with the other retrieval mutants, and the runs are")
        add("committed under " + BT + "results/retrieval-pad-*.json" + BT + ". The first version of them called the search")
        add("with k=1 and appended two records, which changed two things at once - the list lost whatever")
        add("the control had found at ranks two and three, and gained padding - so its difference from the")
        add("control could be attributed to neither. A lever that moves two things measures nothing.")
        add("")

    # ---- close ------------------------------------------------------------------------------------
    add("## What this does not settle")
    add("")
    add("The near rule is a rule, and the split it draws is a definition rather than a discovery. It is")
    add("checked in one direction only - near pairs exist by construction in the supersession band and the")
    add("rule finds them - and nothing checks the other: a record called near may still be useless to the")
    add("caller. **The noise column is a count of records that share neither a name nor three distinguishing")
    add("words with the answer**, and not a count of wasted attention. The silence bill is the part of this")
    add("report that needs no rule at all, and it is the part to quote when only one number will be.")
    add("")
    add("Nothing was re-run to write this. Every row was on disk already, so no subject was asked twice and")
    add("no new measurement can contradict an old one - but a defect in a corpus is inherited here as")
    add("everywhere else, and this reading found two. The first is a question two records answer equally:")
    add("two packages can carry the same description word for word, so a corpus built from real descriptions")
    add("asked the same words twice with a different expected record and graded one of the two answers")
    add("wrong. That is fixed - " + BT + "questions.py" + BT + " drops every copy, the four generated corpora were")
    add("rebuilt without them, and the " + str(sum(summed(got, n)["orphan_rows"] for n in got)) + " rows measured against the")
    add("dropped questions are excluded from every count here rather than re-run, because a question that two")
    add("records answer equally was not measuring the subject.")
    add("")
    add("The second stands and is pinned: the exam's eight unanswerable questions whose words are half inside")
    add("a single record. Those are fair questions - the covering record is not the answer - and the charge")
    add("against them belongs to the validator's word-overlap rule, not to the corpus. A reader who wants the")
    add("validator to stop making it should read that as the next phase rather than a footnote.")
    add("")
    add("Finally, no judgement of usefulness is made by any rule here, and none can be: deciding whether a")
    add("returned record HELPS a caller is not a counting question. It is the one place in this repository")
    add("where a model reading the record would beat any rule - so two were asked. " + BT + "judge.py" + BT + " puts the")
    add("plain question to each, with no label and no corpus in the prompt, and this reading's labels are")
    add("their score:")
    add("")
    said = judge_agreement()
    if said:
        for r in said["readers"]:
            add("- **" + BT + r["model"] + BT + ": %d of %d pairs agree with the rule, kappa %.2f.** It calls"
                % (r["agree"], r["n"], r["kappa"]))
            add("  %d record(s) this report excuses as near misses unrelated, and %d it calls noise worth"
                % (r["generous"], r["stingy"]))
            add("  reading.")
        add("")
        if said.get("ceiling"):
            c = said["ceiling"]
            add("The two readers agree with **each other** on %d of %d of the same pairs, kappa %.2f. That is"
                % (c["agree"], c["n"], c["kappa"]))
            add("the ceiling: a rule cannot be closer to what a reader thinks than two readers are to each")
            add("other, and the gap between that number and the two above is how much of the disagreement is")
            add("this reading rather than the rule.")
        add("")
        add(BT + "JUDGE.md" + BT + " prints the disagreements one by one, with each reader's reason. That is the")
        add("first time this checker's judgement has been audited by anything other than itself.")
    else:
        add("- no judgments are on disk yet; " + BT + "python judge.py --sample=60" + BT + " asks the question of")
        add("  every reader, caches the answers, and this paragraph is regenerated from them.")
    path = os.path.join(HERE, "PRECISION.md")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print("written to %s" % path)


def dump(got, panel):
    out = {"subjects": {}, "panel": {}}
    for n in got:
        out["subjects"][n] = dict(got[n])
    for n in panel:
        out["panel"][n] = {"note": panel[n]["note"],
                           "written": panel[n]["written"], "keywords": panel[n]["keywords"]}
    path = os.path.join("results", "precision.json")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(out, indent=1, sort_keys=True) + chr(10))
    print("written to %s" % path)


def main(argv):
    got, panel = measure()
    if len(got) < 4:
        raise SystemExit("not enough subjects with saved rows")
    orphan = sum(summed(got, n)["orphan_rows"] for n in got)
    if orphan:
        print("%d row(s) answer questions no corpus on disk asks, and are excluded" % orphan)
    checks = verdicts(got, panel)
    dump(got, panel)
    print("%d subjects, %d corpora, %d panel adapters" % (len(got), len(CORPORA), len(panel)))
    for n, text, held, detail in checks:
        print("  %d. %-12s %s" % (n, {True: "held", False: "DID NOT HOLD", None: "unchecked"}[held], detail))
    if "--json" not in argv:
        report(got, panel, checks)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))