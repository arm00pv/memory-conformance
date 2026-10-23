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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
