#!/usr/bin/env python3
"""figures.py - does the prose still agree with the results it was written from.

EVERY GENERATED PAGE IS RE-RUN BEFORE A BUILD MAY PASS, so a table cannot drift unnoticed. The prose
is a different thing. The README and the hand-written pages under docs/ quote figures inside
sentences - from 37 to 43, the exam is 276 questions, Spearman 0.78 against corpus A - and nothing
re-derives them. This repository has already been bitten by exactly that: "5 of the 11 claims" sat in
the README for a whole phase after the ledger had twelve, because the sentence and the measurement had
no connection either a machine or a person would notice breaking.

So a sentence can be a pin. Each entry in PINS names a file and a regular expression that must match
it exactly once; the numbers the expression captures are compared with the same figures recomputed
from the committed results. THE DOCUMENT IS THE PIN: there is no second copy of the number to keep in
step, and rewording the sentence is a build failure until the pin is restated, which is the point - a
sentence nobody can check is a sentence nobody has checked.

    python figures.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

_CACHE = {}


def _modules():
    import precision
    return precision


def _slug_label():
    """Slug to label, because result files are named by slug and subjects by label."""
    import resolution
    return dict((s["slug"], s["label"]) for s in resolution.subjects())


def _measure():
    if "measure" not in _CACHE:
        precision = _modules()
        _CACHE["measure"], _CACHE["panel"] = precision.measure()
    return _CACHE["measure"]


def _totals(slug):
    """One subject across every corpus, the way the precision tables report it."""
    precision = _modules()
    label = _slug_label().get(slug)
    got = _measure()
    if label not in got:
        return None
    return precision.summed(got, label)


def _rows(path, label):
    precision = _modules()
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh).get("rows") or []
    rows = precision.live_rows(label, rows)
    return {"score": precision.score(rows),
            "hits": precision.derive(precision.read(label, rows, "written"))["hits"]}


def _one(label, slug, suffix=""):
    precision = _modules()
    return _rows(os.path.join("results", slug + "-retrieval" + suffix + ".json"), label)


def _mutant(label, name):
    return _rows(os.path.join("results", "retrieval-%s-%s.json" % (name, label)), label)


def _corpus(label):
    """Questions the corpus still asks, and how many of them have no answer.

    questions.live() answers the question the whole repository asks about a corpus - which questions
    are still asked - and it returns the query strings, not the records. The difficulty of each one
    lives in the corpus reader that already grades them, so it is looked up there rather than
    re-parsed here.
    """
    precision = _modules()
    import questions
    live = questions.live(precision._corpus_path(label))
    want = precision.corpus(label)["want"]
    absent = sum(1 for q in live if (want.get(q) or {}).get("difficulty") == "absent")
    return {"questions": len(live), "absent": absent, "answerable": len(live) - absent}


def _absent_band():
    """The silence bill: how many corpora carry an unanswerable band, and how many questions it is."""
    precision = _modules()
    corpora = 0
    total = 0
    for label, _path, _suffix in precision.CORPORA:
        block = _corpus(label)
        if block["absent"]:
            corpora += 1
            total += block["absent"]
    return {"corpora": corpora, "questions": total}


def _bands():
    """The silence bill the way the page states it: pooled answers over pooled opportunities.

    The first version of that sentence said "36 of 99 on the long exam", which reads as one subject
    against one band - and 99 was the exam band before 24 duplicate slots were dropped, while 36 is
    a count over seven subjects. Both halves were wrong in different ways and the sentence still
    looked like a measurement. Pooled over the subjects that decide per question, it is 36 of 686.
    """
    got = _measure()
    short = ("A", "B", "C", "real")
    deciding = []
    for name in got:
        block = got[name].get("large")
        if not block or not block["absent_questions"]:
            continue
        if block["absent_answered"] * 2 < block["absent_questions"]:
            deciding.append(name)
    out = {"short.answers": 0, "short.total": 0, "exam.answers": 0, "exam.total": 0}
    for name in deciding:
        for label in short:
            if label in got[name]:
                out["short.answers"] += got[name][label]["absent_answered"]
                out["short.total"] += got[name][label]["absent_questions"]
        out["exam.answers"] += got[name]["large"]["absent_answered"]
        out["exam.total"] += got[name]["large"]["absent_questions"]
    return out


def _best_hits(label):
    """The best hits any subject reached on a corpus, which is how the ceiling sentence reads."""
    got = _measure()
    best = 0
    for name in got:
        block = got[name].get(label)
        if block:
            best = max(best, block["hits"])
    return best


def _cost(slug):
    """One subject's timings, as committed. Cost is measured once and cached, so it is stable data."""
    path = os.path.join("results", slug + "-cost.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _costs():
    """Every timing file on disk, keyed by slug."""
    out = {}
    for name in sorted(os.listdir("results")):
        if name.endswith("-cost.json"):
            with open(os.path.join("results", name), encoding="utf-8") as fh:
                out[name[:-len("-cost.json")]] = json.load(fh)
    return out


def _row_scores(slugs, columns):
    """The score of one row of subjects on each corpus a table names, or None where unmeasured."""
    precision = _modules()
    suffixes = dict((label, suffix) for label, _path, suffix in precision.CORPORA)
    out = []
    for label in columns:
        vals = []
        for slug in slugs:
            rows = precision.rows_of(slug, suffixes[label])
            vals.append(None if not rows else precision.score(precision.live_rows(label, rows)))
        if any(v is None for v in vals):
            out.append(None)
        elif len(set(vals)) > 1:
            # A ROW THAT NAMES TWO SUBJECTS CANNOT CARRY ONE CELL FOR THEM unless they agree, and a table
            # that quietly averaged them would be reporting a number neither of them scored.
            out.append(None)
        else:
            out.append(vals[0])
    return out


def markdown_rows(text, header):
    """The body rows under a markdown table's header line, split into stripped cells."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == header:
            out = []
            for row in lines[i + 1:]:
                if not row.strip().startswith("|"):
                    break
                if set(row.strip()) <= set("|-: "):
                    continue
                out.append([c.strip() for c in row.strip().strip("|").split("|")])
            return out
    return None


# A TABLE IS A PIN TOO. docs/corpora.md carries a copy of the score every subject reaches on the four
# authored corpora - 40 cells, hand-copied from the same results the matrix prints. Every one of them was
# right except the one that mattered least to notice: memory-mcp-1file on real text, 47 where the rows say
# 48. No sentence pinned it, because it is a cell rather than a sentence.
TABLES = [{
    "path": "docs/corpora.md",
    "about": "every subject's score on the four authored corpora",
    "header": "| subject | corpus A | corpus B | corpus C | **real text** |",
    "columns": ["A", "B", "C", "real"],
    "rows": {
        "control": ["control-1.0.0"],
        "memory-lean": ["memory-lean-1.5.0"],
        "mcp-duckdb-memory-server": ["mcp-duckdb-memory-server-1.1.10"],
        "zenbrain": ["zenbrain-0.3.0"],
        "memory-mcp-1file": ["memory-mcp-1file-0.9.2"],
        "mcp-knowledge-graph": ["mcp-knowledge-graph-1.3.2"],
        "server-memory 1.0.0 and 2.0.0": ["server-memory-1.0.0", "server-memory-2.0.0"],
        "memento": ["memento-0.7.0"],
        "statecore-mcp": ["statecore-mcp-1.0.0"],
        "memdb": ["memdb-1.4.0"],
    },
}]


def check_tables():
    """Every cell of every pinned table against the results it was copied from."""
    out = []
    for spec in TABLES:
        row = {"path": spec["path"], "about": spec["about"], "why": None, "cells": []}
        if not os.path.isfile(spec["path"]):
            row["why"] = "the file is not on disk"
            out.append(row)
            continue
        with open(spec["path"], encoding="utf-8") as fh:
            text = fh.read().replace(chr(13) + chr(10), chr(10))
        rows = markdown_rows(text, spec["header"])
        if rows is None:
            row["why"] = "the table this pin names is not in the file"
            out.append(row)
            continue
        for cells in rows:
            name = cells[0].replace(chr(96), "").replace("*", "").strip()
            if name not in spec["rows"]:
                row["cells"].append({"row": name, "column": "-", "prose": "-",
                                     "results": None, "ok": False,
                                     "why": "this row is not in the pin, so nothing checks it"})
                continue
            want = _row_scores(spec["rows"][name], spec["columns"])
            for column, said, value in zip(spec["columns"], cells[1:], want):
                written = said.replace("*", "").replace(chr(96), "").strip()
                if not written or written in ("-", ""):
                    continue
                try:
                    number = float(written)
                except ValueError:
                    row["cells"].append({"row": name, "column": column, "prose": written,
                                         "results": value, "ok": False,
                                         "why": "not a number"})
                    continue
                ok = value is not None and abs(float(value) - number) < 1e-9
                row["cells"].append({"row": name, "column": column, "prose": written,
                                     "results": value, "ok": ok, "why": None})
        out.append(row)
    return out


def _spearman():
    """The rank correlation of the blind corpus, computed by the tool that owns that definition."""
    import third_corpus
    a, b, c = third_corpus.hits(""), third_corpus.hits("-b"), third_corpus.hits("-c")
    names = sorted(set(a) & set(c))
    both = sorted(set(a) & set(b) & set(c))
    return {"ac": third_corpus.spearman([a[n][0] for n in names], [c[n][0] for n in names]),
            "bc": (third_corpus.spearman([b[n][0] for n in both], [c[n][0] for n in both])
                   if len(both) >= 4 else 0.0)}


# EVERY READING COMES FROM THE MODULE THAT OWNS THE DEFINITION. Nothing here recomputes a score,
# counts a question or ranks a corpus with its own copy of the rule - a second copy is how the exam
# came to read 292 against 268 in a table whose subject was denominators.
READINGS = {
    "control.score.A": lambda: _one("A", "control-1.0.0")["score"],
    "control.hits.A": lambda: _one("A", "control-1.0.0")["hits"],
    "greedy.score.A": lambda: _mutant("A", "greedy-match")["score"],
    "greedy.hits.A": lambda: _mutant("A", "greedy-match")["hits"],
    "A.answerable": lambda: _corpus("A")["answerable"],
    "A.questions": lambda: _corpus("A")["questions"],
    "A.absent": lambda: _corpus("A")["absent"],
    "best.hits.A": lambda: _best_hits("A"),
    "exam.questions": lambda: _corpus("large")["questions"],
    "absent.questions": lambda: _absent_band()["questions"],
    "absent.corpora": lambda: _absent_band()["corpora"],
    "memento.hits.all": lambda: _totals("memento-0.7.0")["hits"],
    "memento.noise.all": lambda: _totals("memento-0.7.0")["noise_records"],
    "control.hits.all": lambda: _totals("control-1.0.0")["hits"],
    "control.noise.all": lambda: _totals("control-1.0.0")["noise_records"],
    "rho.ac": lambda: _spearman()["ac"],
    "rho.bc": lambda: _spearman()["bc"],
    "short.band.answers": lambda: _bands()["short.answers"],
    "short.band.total": lambda: _bands()["short.total"],
    "exam.band.answers": lambda: _bands()["exam.answers"],
    "exam.band.total": lambda: _bands()["exam.total"],
    "memdb.per_question": lambda: _totals("memdb-1.4.0")["per_question"],
    "control.per_question": lambda: _totals("control-1.0.0")["per_question"],
    # THE COST PAGE. Timings are taken once, cached and committed, so they are as checkable as any
    # count - and that page's table was a copy of a generated one, which is how it came to list nine
    # subjects while the results held eleven and to say two where the count is three.
    "cost.resp39": lambda: sum(1 for d in _costs().values() if d.get("resp_bytes_p50") == 39),
    "cost.lean.bytes": lambda: _cost("memory-lean-1.5.0")["resp_bytes_p50"],
    "cost.lean.amp": lambda: round(_cost("memory-lean-1.5.0")["amp"]),
    "cost.one.amp": lambda: round(_cost("memory-mcp-1file-0.9.2")["amp"]),
    "cost.memento.first.min": lambda: _cost("memento-0.7.0")["spread"]["first_write"]["min"],
    "cost.memento.first.max": lambda: _cost("memento-0.7.0")["spread"]["first_write"]["max"],
    # THE SENTENCE SAYS "ITS", and its antecedent is memento, not memdb: the store allocated once and
    # then holding anything is memento's 4.3 MB. The first version of this reading pointed at memdb,
    # whose floor is 0.75 MB, and the pin caught the mistake in the reading rather than in the page.
    "cost.memento.floor.mb": lambda: _cost("memento-0.7.0")["store_floor_bytes"] / 1000000.0,
}

PINS = [
    ("README.md",
     "lowering the bar to one shared word gains the score and the hits the sentence claims",
     r"from (\d+) to \*\*(\d+)\*\*, with hits from (\d+) to (\d+)",
     ("control.score.A", "greedy.score.A", "control.hits.A", "greedy.hits.A")),
    ("README.md",
     "the ceiling on corpus A and the best any subject reached",
     r"The ceiling is (\d+) hits and one subject is at (\d+) of them",
     ("A.answerable", "best.hits.A")),
    ("docs/precision.md",
     "what memento answers and what it hands back beside it, over every corpus",
     r"answers (\d+) questions correctly and hands back \*\*([\d,]+) records nobody",
     ("memento.hits.all", "memento.noise.all")),
    ("docs/precision.md",
     "the same two readings for the control",
     r"the control\s+answers (\d+) and hands back (\d+)",
     ("control.hits.all", "control.noise.all")),
    ("docs/precision.md",
     "how many questions the unanswerable bands hold",
     r"band, (\d+) questions in all",
     ("absent.questions",)),
    ("docs/precision.md",
     "the size of the examination once the duplicate slots are dropped",
     r"the exam is (\d+) questions",
     ("exam.questions",)),
    ("docs/corpora.md",
     "the rank correlation of the blind corpus against A and against B",
     r"Spearman ([\d.]+) against corpus A and ([\d.]+) against corpus B",
     ("rho.ac", "rho.bc")),
    ("docs/precision.md",
     "the silence bill read as a threshold, pooled over the subjects that decide per question",
     r"answer (\d+) of (\d+) on the four short\s+bands and \*\*(\d+) of (\d+) on the long exam\*\*",
     ("short.band.answers", "short.band.total", "exam.band.answers", "exam.band.total")),
    ("docs/precision.md",
     "the reading bill per question at its widest, and the control it is measured against",
     r"to \*\*(\d+)\*\* \(`memdb`\),\s+against a control at (\d+)",
     ("memdb.per_question", "control.per_question")),
    # THE COST PAGE. Its table is generated now, but the sentences around it still quote figures -
    # and one of them counted subjects, which is the kind of number no table row can contradict.
    ("docs/cost.md",
     "how many subjects cost 39 bytes per question, all of them silent",
     r"the (\d+) subjects that cost 39 bytes per question",
     ("cost.resp39",)),
    ("docs/cost.md",
     "memory-lean's response bill and its multiplier",
     r"genuinely lean . (\d+) bytes, (\d+)\u00d7",
     ("cost.lean.bytes", "cost.lean.amp")),
    ("docs/cost.md",
     "the multiplier on the subject that retrieves most",
     r"at (\d+)\u00d7 the size of the answer",
     ("cost.one.amp",)),
    ("docs/cost.md",
     "memento's first write at both ends of its own spread",
     r"first write ranged from ([\d.]+) s to ([\d.]+) s",
     ("cost.memento.first.min", "cost.memento.first.max")),
    ("docs/cost.md",
     "the store that subject allocates once",
     r"its ([\d.]+) MB store",
     ("cost.memento.floor.mb",)),
]


def _value(pid):
    try:
        return READINGS[pid]()
    except Exception as exc:
        return "could not be read: %s" % exc


def parse(text):
    """A number as the prose writes it: commas are thousands, and the decimals set the precision."""
    raw = text.replace(",", "")
    places = len(text.split(".")[1]) if "." in text else 0
    return float(raw), places


def check():
    out = []
    for path, about, pattern, ids in PINS:
        row = {"path": path, "about": about, "why": None, "numbers": []}
        if not os.path.isfile(path):
            row["why"] = "the file is not on disk"
            out.append(row)
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        found = list(re.finditer(pattern, text))
        if len(found) != 1:
            row["why"] = ("the sentence this pin names is not in the file" if not found
                          else "%d sentences in the file match this pin" % len(found))
            out.append(row)
            continue
        for pid, written in zip(ids, found[0].groups()):
            value = _value(pid)
            said, places = parse(written)
            ok = isinstance(value, (int, float)) and abs(round(float(value), places) - said) < 1e-9
            row["numbers"].append({"id": pid, "prose": written, "results": value, "ok": ok})
        out.append(row)
    return out


def main():
    rows = check()
    files = sorted(set(r["path"] for r in rows))
    numbers = sum(len(r["numbers"]) for r in rows)
    print("%d sentences in %d hand-written pages pin %d numbers to the results"
          % (len(rows), len(files), numbers))
    bad = 0
    for row in rows:
        if row["why"]:
            print("  %-20s %s" % (row["path"], row["why"]))
            bad += 1
            continue
        for n in row["numbers"]:
            shown = n["results"]
            if isinstance(shown, float):
                shown = "%.3f" % shown
            print("  %-20s %-18s prose %-8s results %-10s %s"
                  % (row["path"], n["id"], n["prose"], shown,
                     "ok" if n["ok"] else "DISAGREES"))
            if not n["ok"]:
                bad += 1
    tables = check_tables()
    cells = sum(len(t["cells"]) for t in tables)
    if tables:
        print("%d hand-copied table(s), %d cell(s)" % (len(tables), cells))
        for t in tables:
            if t["why"]:
                print("  %-20s %s" % (t["path"], t["why"]))
                bad += 1
                continue
            for c in t["cells"]:
                if c["ok"]:
                    continue
                shown = c["results"]
                if isinstance(shown, float):
                    shown = "%.3f" % shown
                print("  %-20s %-28s %-6s prose %-5s results %-6s %s"
                      % (t["path"], c["row"], c["column"], c["prose"], shown,
                         c["why"] or "DISAGREES"))
                bad += 1
    if bad:
        print("%d of those numbers no longer match the results they were written from" % bad)
        return 1
    print("every number a hand-written page quotes still matches the results behind it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
