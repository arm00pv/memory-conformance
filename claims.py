#!/usr/bin/env python3
"""claims.py - what does this suite actually know, and on how many corpora?

SIXTEEN ADDENDA LATER, THE FINDINGS ARE A CHAIN OF CORRECTIONS. Every phase sharpened the instrument and
retracted something the previous phase had said; a reader arriving now has to read eighty thousand words
to discover that "memory-mcp-1file finds the most" is true, "memory-mcp-1file is better than zenbrain" is
true only when the question is put as keywords, and "the servers most people use cannot answer anything"
is true as written and false when the words are stripped.

So the claims are evaluated instead of remembered. Each one is a sentence this repository has published,
checked against the committed results on every corpus and both phrasings. A claim that holds on one corpus
and not the other is not a fact about a server; a claim that holds only when the question is asked one way
is not a fact either.

  python claims.py            # evaluate every claim and write CLAIMS.md

The statuses are deliberately blunt:

  HOLDS        true in every setting measured
  ONE CORPUS   true on one corpus and false on the other
  ONE PHRASING true as written and false as keywords, or the reverse
  MIXED        neither of the above
  FAILS        false in every setting measured
  UNMEASURED   the results needed are not on disk

TWO MEASUREMENTS ARE KEPT APART HERE, because confusing them is how a claim about retrieval gets made
about silence. A subject's SCORE is what compare.py pairs on: the right record in the top three, plus a
credit for declining a question that has no answer. A subject's HITS are only the questions that have an
answer and were answered correctly. "It answers nothing" is a claim about hits. "It is not better than
another server" is a claim about the score, because silence is part of being better.

This tool is not a gate. A failing claim is a result, not a defect; what would be a defect is publishing
it without the word "fails" next to it.
"""
import json
import os
import sys

import compare
import matrix

HERE = os.path.dirname(os.path.abspath(__file__))
CORPORA = {"A": ("retrieval_corpus.json", ""), "B": ("retrieval_corpus_b.json", "-b")}
LEADER = "memory-mcp-1file 0.9.2"
RUNNER = "zenbrain 0.3.0"
CONTROL = "control 1.0.0"
TICK, CROSS, BLANK = "yes", "no", "-"
OUT = []
CONTEXT = {"subjects": [], "labels": []}


def say(line=""):
    print(line, flush=True)
    OUT.append(line)


def entry_of(label):
    for entry in CONTEXT["subjects"]:
        if "%s %s" % (entry["name"], entry["version"]) == label:
            return entry
    raise KeyError(label)


def rows(label, corpus):
    path = os.path.join("results", matrix.slug_of(entry_of(label)) + "-retrieval"
                        + CORPORA[corpus][1] + ".json")
    return matrix.load_rows(path, CORPORA[corpus][0])


def probes(label):
    path = os.path.join("results", matrix.slug_of(entry_of(label)) + ".json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return {r["probe"]: r for r in json.load(fh).get("probes") or []}


def calibration(mutant, corpus):
    """One saved control run, or None when it answers a corpus that is no longer on disk.

    THE SAME STALENESS GUARD THE RETRIEVAL ROWS GET, for the same reason: a calibration file that was
    measured against sixty questions nobody asks any more would go on quietly certifying a scale it no
    longer describes.
    """
    path = os.path.join("results", "calibration-%s-%s.json" % (mutant, corpus))
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    corpus_path = CORPORA[corpus][0]
    if os.path.isfile(corpus_path):
        want = matrix.corpus_queries(corpus_path)
        got = [(r.get("query"), r.get("expect"), r.get("difficulty"))
               for r in doc.get("rows") or []]
        if got != want:
            return None
    return doc


def cost(label):
    path = os.path.join("results", matrix.slug_of(entry_of(label)) + "-cost.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ok(row, shape):
    """compare.py's definition of correct, read from the phrasing being scored."""
    if shape == "written":
        return compare.correct(row)
    return compare.correct({"difficulty": row["difficulty"],
                             "answered": bool(row.get("answered_keyword")),
                             "hit3": bool(row.get("hit3_keyword"))})


def score(label, corpus, shape="written"):
    """Correct answers and declines, the number the paired test pairs on."""
    rs = rows(label, corpus)
    return sum(1 for r in rs if ok(r, shape)) if rs else None


def hits(label, corpus, shape="written"):
    """Only the questions that have an answer, answered correctly."""
    rs = rows(label, corpus)
    if not rs:
        return None
    key = "hit3" if shape == "written" else "hit3_keyword"
    return sum(1 for r in rs if r.get(key))


def band(label, corpus, which, shape="written"):
    rs = rows(label, corpus)
    if not rs:
        return None
    sel = [r for r in rs if r.get("difficulty") == which]
    if which == "absent":
        key = "answered" if shape == "written" else "answered_keyword"
        return sum(1 for r in sel if r.get(key))
    key = "hit3" if shape == "written" else "hit3_keyword"
    return sum(1 for r in sel if r.get(key))


def paired(a, b, corpus, shape="written"):
    """(p, how many a answered that b did not, and the reverse) - direction is half a claim."""
    ra, rb = rows(a, corpus), rows(b, corpus)
    if not ra or not rb:
        return None
    x = [ok(r, shape) for r in ra]
    y = [ok(r, shape) for r in rb]
    only_a = sum(1 for p, q in zip(x, y) if p and not q)
    only_b = sum(1 for p, q in zip(x, y) if q and not p)
    return compare.exact_mcnemar(only_a, only_b), only_a, only_b


def leads(label, corpus, key, shape="written"):
    """Where a subject sits in one ordering, and whether it is alone at the top."""
    scored = []
    for other in CONTEXT["labels"]:
        v = key(other, corpus, shape)
        if v is not None:
            scored.append((v, other))
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[1]))
    mine = [v for v, n in scored if n == label]
    if not mine:
        return None
    best = scored[0][0]
    tied = [n for v, n in scored if v == best and n != label]
    return {"value": mine[0], "best": best, "strict": mine[0] == best and not tied,
            "tied_with": tied, "n": len(scored)}


def fmt_lead(r, of="16"):
    """The number, and whether it is alone at the top - a tie is not a lead."""
    head = "%d/%s" % (r["value"], of)
    if r["strict"]:
        return "%s, alone at the top of %d subjects" % (head, r["n"])
    if r["value"] == r["best"]:
        return "%s, tied with %s" % (head, ", ".join(r["tied_with"]))
    return "%s, best is %d" % (head, r["best"])


# --- the claims ------------------------------------------------------------

def c_most_hits(ctx, corpus, shape):
    r = leads(LEADER, corpus, lambda n, c, s: hits(n, c, s), shape)
    return (r["strict"], fmt_lead(r, of="48")) if r else None


def c_leads_runner(ctx, corpus, shape):
    p = paired(LEADER, RUNNER, corpus, shape)
    if not p:
        return None
    pv, a, b = p
    return pv < 0.05 and a > b, "p = %.4f on %d-%d discordant questions" % (pv, a, b)


def c_beats_control(ctx, corpus, shape):
    p = paired(RUNNER, CONTROL, corpus, shape)
    if not p:
        return None
    pv, a, b = p
    return pv < 0.05 and a > b, "p = %.4f on %d-%d discordant questions" % (pv, a, b)


def c_reference_silent(ctx, corpus, shape):
    v = hits("server-memory 1.0.0", corpus, shape)
    return (v == 0, "%d of 48 answerable questions answered" % v) if v is not None else None


def c_small_servers_silent(ctx, corpus, shape):
    names = [n for n in CONTEXT["labels"]
             if n.split()[0] in ("server-memory", "mcp-knowledge-graph", "statecore-mcp")]
    vals = {n: hits(n, corpus, shape) for n in names}
    if any(v is None for v in vals.values()):
        return None
    return (all(v == 0 for v in vals.values()),
            ", ".join("%s %d" % (n.split()[0] + " " + n.split()[1], v) for n, v in sorted(vals.items())))


def c_memento_speaks(ctx, corpus, shape):
    v = band("memento 0.7.0", corpus, "absent", shape)
    return (v == 12, "%d of 12 unanswerable questions answered" % v) if v is not None else None


def item_analysis(corpus, shape):
    """items.py's per-question table for one corpus in one phrasing."""
    import items
    path, suffix = CORPORA[corpus]
    got = items.analyse(corpus, path, suffix, shape)
    return got[0] if got else None


def _subject_total(label, corpus, shape):
    """One subject's score, the same number the paired tests pair on."""
    rs = rows(label, corpus)
    if not rs:
        return None, 0
    return sum(1 for r in rs if ok(r, shape)), len(rs)


def _control_total(mutant, corpus, shape):
    doc = calibration(mutant, corpus)
    if not doc:
        return None, None
    rows = doc.get("rows") or []
    n = len(rows)
    if shape == "keywords":
        got = sum(1 for r in rows if compare.correct_keyword(r))
    else:
        got = sum(1 for r in rows if compare.correct(r))
    return got, n


def c_scale_ceiling(ctx, corpus, shape):
    """The retrieval score's maximum is reachable by something.

    A SCORE WHOSE CEILING NOBODY HAS MEASURED IS NOT A MEASUREMENT. Forty-two out of sixty describes a
    subject and says nothing about whether sixty was ever available - the questions might have made a
    perfect answer impossible. The oracle is the corpus's own answer key wired to a search tool, so if
    it does not score every question, the failure is in the corpus or in the scoring and not in any
    subject.
    """
    got, n = _control_total("oracle-search", corpus, shape)
    if got is None:
        return None
    return got == n, "an oracle returning the corpus's own answers scored %d of %d" % (got, n)


def c_floor_not_zero(ctx, corpus, shape):
    """A subject that answers no question at all still scores the unanswerable ones.

    THE FLOOR OF THE SCORE IS NOT ZERO, and every paired test is computed from this score. Twelve
    questions out of sixty have no answer, and returning nothing on them is correct, so a memory that
    does nothing collects twelve points. That is right - declining is correct behaviour - but a reader
    comparing 43 with 12 is comparing a subject with a scale, not with another subject, and the ledger
    should say so.
    """
    got, n = _control_total("mute-search", corpus, shape)
    if got is None:
        return None
    doc = calibration("mute-search", corpus)
    absent = sum(1 for r in doc.get("rows") or [] if r.get("difficulty") == "absent")
    return got > 0, ("a subject that never answers scored %d of %d, the %d questions with no answer"
                     % (got, n, absent))


def statistics_median(values):
    import statistics
    vals = [v for v in values if v]
    return statistics.median(vals) if vals else None


def _separated(corpus, shape, metric, a, b):
    """The paired verdict for two subjects, on one metric, from the saved retrieval rows."""
    import resolution
    by = dict((s["label"], s["slug"]) for s in resolution.subjects())
    if a not in by or b not in by:
        return None
    suffix = CORPORA[corpus][1]
    ra, rb = resolution.rows_of(by[a], suffix), resolution.rows_of(by[b], suffix)
    if ra is None or rb is None:
        return None
    return resolution.compare_pair(ra, rb, shape, metric)


def c_search_flat(ctx, corpus, shape):
    """A search costs the same whether the store holds ten records or two thousand.

    THE COST TABLE MEASURES SEARCH AT SEVENTY-TWO RECORDS. Every subject is quoted at a search latency
    taken on a store the size of the retrieval corpus, and used by agents that store thousands. If a
    search walks the store, that latency is a number about a corpus and not about a memory, and the
    difference is the one number in this repository an agent runtime would actually budget against.
    """
    import growth
    runs = growth.load_runs()
    grew = []
    for label in sorted(runs):
        rs = runs[label]
        depths = sorted(set(int(d) for r in rs for d in r["searches"]))
        if len(depths) < 2:
            continue
        first = statistics_median([r["searches"].get(str(depths[0])) for r in rs])
        last = statistics_median([r["searches"].get(str(depths[-1])) for r in rs])
        if first and last and last / first >= 1.5:
            grew.append("%s x%.0f" % (label.split()[0], last / first))
    return (not grew, ("%d subject(s) cost more to search at %d records than at %d (%s)"
                       % (len(grew), 3000, 5, ", ".join(grew) or "none")))


def c_metrics_agree(ctx, corpus, shape):
    """The score and the answerable-only count rank the top of the table the same way.

    THEY DO NOT, AND THE DISAGREEMENT IS THE INTERESTING PART. items.py showed the score carries a
    twelve-point switch for a habit that is uncorrelated with ability on one corpus and anti-correlated
    on the other, so a pair whose real difference is in retrieval can be cancelled by it. The test here
    is whether that changes any conclusion at the top of the table - if the two metrics agreed
    everywhere, the switch would be a curiosity.
    """
    pairs = [("memory-mcp-1file 0.9.2", "control 1.0.0"),
             ("zenbrain 0.3.0", "control 1.0.0")]
    disagree = []
    for a, b in pairs:
        s = _separated(corpus, shape, "score", a, b)
        h = _separated(corpus, shape, "hits", a, b)
        if s is None or h is None:
            continue
        if s["separated"] != h["separated"]:
            disagree.append("%s vs %s (score %s, hits %s)"
                            % (a.split()[0], b.split()[0],
                               "separated" if s["separated"] else "tied",
                               "separated" if h["separated"] else "tied"))
    return (not disagree,
            "%d of %d top-of-table pairs get different verdicts from the two metrics%s"
            % (len(disagree), len(pairs),
               (": " + "; ".join(disagree)) if disagree else ""))


def c_absent_band_flat(ctx, corpus, shape):
    """The unanswerable questions give the stronger subjects no advantage.

    A SIGN, NOT A SIZE, because a size would have to be chosen after looking. Every subject here either
    declines all twelve unanswerable questions or declines none of them - there is no gradient - so
    the band is worth 12 of the 60 points the score counts, handed to whoever declines. Measured by
    discrimination rather than guessed at: if the top half of subjects by total score does better on
    these questions than the bottom half, the band is rewarding ability; if it does not, it is
    rewarding a habit.
    """
    blocks = item_analysis(corpus, shape)
    if not blocks:
        return None
    sel = [i for i in blocks if i["difficulty_band"] == "absent"]
    if not sel:
        return None
    d = sum(i["d"] for i in sel) / len(sel)
    return d <= 0.0, ("the unanswerable band's discrimination is %+.2f, on %d questions worth %d of"
                      " the score's %d points" % (d, len(sel), len(sel), len(blocks)))


def c_silence_scores_better(ctx, corpus, shape):
    """At least one subject scores worse than a memory that answers nothing at all.

    THE SCORE IS RIGHT AND ITS FLOOR IS A TRAP. Returning nothing on a question with no answer is
    correct behaviour, so a subject that never answers collects all twelve of them - and a subject that
    answers them all wrongly collects none. Answering is only rewarded when the answer is right;
    silence is never punished. That is defensible as a metric, and it means a real subject can finish
    below a program that does nothing, which is worth a claim rather than a footnote.
    """
    floor, _n = _control_total("mute-search", corpus, shape)
    if floor is None:
        return None
    worse = []
    for label in ctx["labels"]:
        got, _total = _subject_total(label, corpus, shape)
        if got is None:
            continue
        if got < floor:
            worse.append("%s %d" % (label.split()[0], got))
    return bool(worse), ("%d subject(s) below the %d that answering nothing scores%s"
                         % (len(worse), floor,
                            (" (" + ", ".join(worse) + ")") if worse else ""))


def c_verbatim(ctx, corpus, shape):
    """Every subject returns a record exactly as it was written.

    THE NARROWEST PROMISE HERE, AND THE ONLY ONE THAT NEEDS NO JUDGEMENT ABOUT WHAT "THE SAME" MEANS.
    Nine strings - 2, 3 and 4-byte UTF-8, a combining pair next to its precomposed twin, right-to-left
    text, JSON escapes, a zero-width space, and a newline inside the body of a newline-delimited
    transport - are written as one record and compared byte for byte on a process that never saw the
    write. Either the bytes match or they do not.
    """
    altered, unknown = [], []
    for label in ctx["labels"]:
        r = (probes(label).get("verbatim") or {})
        if not r:
            continue
        if r.get("verdict") == "FAIL":
            altered.append(label)
        elif r.get("verdict") == "UNKNOWN":
            unknown.append(label)
    return (not altered and not unknown,
            "%d altered it (%s); %d could not be compared (%s)"
            % (len(altered), ", ".join(n.split()[0] for n in altered) or "none",
               len(unknown), ", ".join(n.split()[0] for n in unknown) or "none"))


def c_leaks_state(ctx, corpus, shape):
    p = probes(LEADER)
    if not p:
        return None
    verdict = (p.get("isolation") or {}).get("verdict")
    return verdict == "FAIL", "isolation %s" % verdict


def c_can_forget(ctx, corpus, shape):
    """Every subject can be asked to forget, and does.

    THE TWO FAILURES ARE DIFFERENT AND BOTH MATTER. A subject that publishes no way to be asked cannot
    be tested - that is a capability gap - and a subject that was asked and kept the record has broken
    the promise. The claim is the conjunction, and the detail names which is which.
    """
    blocked, failed = [], []
    for label in CONTEXT["labels"]:
        r = (probes(label).get("forget") or {})
        if not r:
            continue
        if r.get("verdict") == "FAIL":
            failed.append(label)
        elif r.get("verdict") == "UNKNOWN":
            blocked.append(label)
    return (not blocked and not failed,
            "%d cannot be asked (%s); %d were asked and did not forget (%s)"
            % (len(blocked), ", ".join(n.split()[0] for n in blocked) or "none",
               len(failed), ", ".join(n.split()[0] for n in failed) or "none"))


def c_leanest(ctx, corpus, shape):
    best = None
    for label in CONTEXT["labels"]:
        h = hits(label, corpus)
        c = cost(label)
        if not h or not c or not c.get("resp_bytes_p50"):
            continue
        if best is None or c["resp_bytes_p50"] < best[0]:
            best = (c["resp_bytes_p50"], label)
    if best is None:
        return None
    note = "%d bytes per question for %s" % (best[0], best[1])
    if best[1] != "memory-lean 1.5.0":
        lean = cost("memory-lean 1.5.0")
        if lean and lean.get("resp_bytes_p50") and not hits("memory-lean 1.5.0", corpus):
            note += " - memory-lean is cheaper at %d but answers nothing on this corpus, so it does"                     " not qualify" % lean["resp_bytes_p50"]
    return best[1] == "memory-lean 1.5.0", note


def c_best_hard(ctx, corpus, shape):
    r = leads(LEADER, corpus, lambda n, c, s: band(n, c, "hard", s), shape)
    return (r["strict"], fmt_lead(r)) if r else None


def c_best_adversarial(ctx, corpus, shape):
    r = leads(RUNNER, corpus, lambda n, c, s: band(n, c, "adversarial", s), shape)
    return (r["strict"], fmt_lead(r)) if r else None


def c_phrasing_matters(ctx, corpus, shape):
    worst = None
    for label in CONTEXT["labels"]:
        w, k = hits(label, corpus, "written"), hits(label, corpus, "keywords")
        if w is None or k is None:
            continue
        if worst is None or abs(k - w) > abs(worst[1] - worst[0]):
            worst = (w, k, label)
    if worst is None:
        return None
    return abs(worst[1] - worst[0]) >= 10, "%s: %d as written, %d as keywords" % (worst[2], worst[0],
                                                                                worst[1])


CLAIMS = [
    ("most-hits", "memory-mcp-1file answers more answerable questions than any other subject here.",
     c_most_hits, True),
    ("leads-runner", "memory-mcp-1file is better than zenbrain by the paired test.",
     c_leads_runner, True),
    ("beats-control", "zenbrain is better than the positive control by the paired test.",
     c_beats_control, True),
    ("reference-silent", "@modelcontextprotocol/server-memory answers no answerable question at all.",
     c_reference_silent, True),
    ("small-servers-silent", "the smallest servers here find nothing at all.",
     c_small_servers_silent, True),
    ("memento-speaks", "memento answers every unanswerable question.",
     c_memento_speaks, True),
    ("can-forget", "every subject can be asked to forget a record, and forgets it.",
     c_can_forget, False),
    ("verbatim-all", "every subject returns a record exactly as it was written.",
     c_verbatim, False),
    ("scale-ceiling", "the retrieval score's maximum is reachable by something.",
     c_scale_ceiling, True),
    ("floor-not-zero", "a subject that answers nothing still scores the unanswerable questions.",
     c_floor_not_zero, True),
    ("silence-scores-better", "at least one subject scores worse than a memory that answers nothing.",
     c_silence_scores_better, True),
    ("absent-band-flat", "the unanswerable questions give the stronger subjects no advantage.",
     c_absent_band_flat, True),
    ("metrics-agree", "the score and the answerable-only count rank the top of the table the same way.",
     c_metrics_agree, True),
    ("search-is-flat", "a search costs the same on a small store and a large one.",
     c_search_flat, False),
    ("leaks-state", "memory-mcp-1file leaks state between stores and is out of scope.",
     c_leaks_state, False),
    ("leanest", "memory-lean returns fewer bytes per question than any subject that answers anything.",
     c_leanest, False),
    ("best-hard", "memory-mcp-1file leads the hard band.",
     c_best_hard, True),
    ("best-adversarial", "zenbrain leads the adversarial band.",
     c_best_adversarial, True),
    ("phrasing-matters", "one subject's answer count moves by ten or more on phrasing alone.",
     c_phrasing_matters, False),
]


def classify(cells):
    vals = [v for v, _d in cells.values() if v is not None]
    if not vals:
        return "UNMEASURED"
    if all(vals):
        return "HOLDS"
    if not any(vals):
        return "FAILS"
    names = list(cells)
    if len(vals) == 4:
        a = [cells[n][0] for n in names if n.startswith("A")]
        b = [cells[n][0] for n in names if n.startswith("B")]
        w = [cells[n][0] for n in names if n.endswith("written")]
        k = [cells[n][0] for n in names if n.endswith("keywords")]
        if len(set(a)) == 1 and len(set(b)) == 1 and a[0] != b[0]:
            return "ONE CORPUS"
        if len(set(w)) == 1 and len(set(k)) == 1 and w[0] != k[0]:
            return "ONE PHRASING"
    return "MIXED"


def sync_readme(headline):
    """Put this run's headline into README.md. True if the sentence was there, False if not."""
    import re
    try:
        with open("README.md", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    pattern = re.compile(r"\*\*\d+ of the \d+ claims hold in every setting measured\.\*\*")
    if not pattern.search(text):
        return False
    new = pattern.sub(headline, text)
    if new != text:
        with open("README.md", "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(new)
    return True


def main(argv):
    os.chdir(HERE)
    with open("subjects.json", encoding="utf-8") as fh:
        CONTEXT["subjects"] = json.load(fh)
    CONTEXT["labels"] = ["%s %s" % (e["name"], e["version"]) for e in CONTEXT["subjects"]]

    say("# What this suite knows")
    say()
    say("Every claim below is a sentence this repository has published, re-checked against the committed")
    say("results on both corpora and both phrasings. The point is not that they all hold - several do not,")
    say("and that is the finding. A claim that survives one corpus and not the other is a fact about a")
    say("question set; one that survives one phrasing and not the other is a fact about who is typing.")
    say()
    say("Two measurements are kept apart, because confusing them is how a claim about retrieval becomes a")
    say("claim about silence. A subject's SCORE is what the paired test pairs on - the right record in the")
    say("top three, plus a credit for declining a question with no answer. Its HITS are only the questions")
    say("that have an answer and were answered correctly. \"It answers nothing\" is a claim about hits.")
    say()

    rows_out = []
    for cid, text, fn, shapes in CLAIMS:
        cells = {}
        for corpus in ("A", "B"):
            for shape in (("written", "keywords") if shapes else ("written",)):
                label = "%s %s" % (corpus, shape)
                try:
                    got = fn(CONTEXT, corpus, shape)
                except Exception as exc:
                    got = (None, "could not evaluate: %s" % exc)
                cells[label] = got if got else (None, "no measurement")
        rows_out.append((cid, text, cells, classify(cells)))

    held = sum(1 for r in rows_out if r[3] == "HOLDS")
    say("**%d of the %d claims hold in every setting measured.** The rest are printed beside the setting"
        % (held, len(rows_out)))
    say("that breaks them, because that setting is the claim's real scope.")
    say()
    say("| claim | " + " | ".join(rows_out[0][2]) + " | status |")
    say("|" + "---|" * (len(rows_out[0][2]) + 2))
    for cid, _text, cells, status in rows_out:
        marks = [TICK if v else (CROSS if v is False else BLANK) for v, _d in cells.values()]
        say("| %s | %s | **%s** |" % (cid, " | ".join(marks), status))
    say()
    say("## Each claim, with what it rests on")
    for cid, text, cells, status in rows_out:
        say()
        say("**%s** - %s *%s*" % (cid, text, status))
        for c, (v, detail) in cells.items():
            say("  - %s: %s (%s)" % (c, "true" if v else ("false" if v is False else "unmeasured"), detail))

    with open("CLAIMS.md", "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(OUT) + chr(10))
    print()
    print("written to CLAIMS.md")

    # THE README STATES THIS COUNT IN PROSE, WHICH IS HOW IT WENT STALE. "5 of the 11 claims" sat in
    # the README for a whole phase after a twelfth claim was added, because the only thing that wrote
    # the number was this tool and the only thing that read it was a person. A number nothing
    # re-derives is a number that is already wrong; it is just still plausible. So the sentence is
    # rewritten from the ledger here, and the run fails if it cannot be.
    headline = "**%d of the %d claims hold in every setting measured.**" % (held, len(rows_out))
    synced = sync_readme(headline)
    if synced is None:
        print("README.md is not readable; the claim count in it is unverified")
        return 1
    if synced is False:
        print("README.md no longer states the claim count, so it cannot be kept in step")
        return 1
    print("README claim count: %s" % headline.strip("*"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
