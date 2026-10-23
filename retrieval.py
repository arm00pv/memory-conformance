#!/usr/bin/env python3
"""retrieval.py - can the memory FIND what it kept?

Retention is not retrieval. A store that keeps every byte and cannot answer a question about them is
a backup, not a memory. This runs one corpus at the same server the conformance probes use and
reports hit@1 and hit@3 per band.

FOUR BANDS, AND THE LAST TWO ARE THE POINT.

  easy         the question contains words that appear in the answer, so a lexical match should do
  hard         a paraphrase that shares almost nothing with the wording of the answer
  adversarial  the answer is present and a near duplicate competes for the same words - does it pick
               the right one, or just a plausible one
  absent       nothing in the store answers the question, so the correct behaviour is to return
               nothing at all

WITHOUT THE ABSENT BAND, "RETURN EVERYTHING" SCORES LIKE A SEARCH. Recall at k is trivially good for a
system that answers every question with its whole store; only a question that has no answer can
distinguish a search from a listing, and only the adversarial band can distinguish a search from a
keyword filter. This is a score, not a verdict: "relevant" is a judgement, "returned" is a fact.

  python retrieval.py --adapter=retained --cmd="python /path/to/retained.py"
  python retrieval.py --cases=retrieval_cases.json ...      # the older twelve-question corpus
"""
import json
import os
import shutil
import sys
import tempfile

import harness


def _one_pass(ad, cases, k, shapes=False):
    """One complete experiment: build the store, restart, ask every question.

    WITH shapes ON, EVERY QUESTION IS ALSO ASKED AS A KEYWORD STRING - the same words with the words
    that carry no meaning removed. That second phrasing is derived mechanically from the question, so
    it is identical for every subject and contains no author's vocabulary, and the distance between the
    two answers is a property of the subject rather than of the corpus. It was added because corpus B
    showed that memory-lean scores 14/60 on keyword-shaped questions and 0/60 on question-shaped ones:
    a score computed from one phrasing only says as much about who wrote the questions as about the
    server.
    """
    if hasattr(ad, "reset"):
        ad.reset()
    d = tempfile.mkdtemp(prefix="memret_")
    try:
        srv = ad.server(d)
        try:
            for rec in cases["records"]:
                ad.write(srv, rec["id"], [rec["text"]])
        finally:
            srv.stop()
        # A COLD START: search has to work on a server that never saw the writes.
        srv = ad.server(d)
        rows = []
        try:
            for q in cases["queries"]:
                try:
                    ids = ad.search(srv, q["query"], k)
                except Exception as exc:
                    ids = []
                    q = dict(q, error=str(exc))
                want = q.get("expect")
                hit1 = bool(want) and ids[:1] == [want]
                hit3 = bool(want) and want in ids[:k]
                row = {"query": q["query"], "expect": want,
                       "difficulty": q["difficulty"], "returned": ids[:k],
                       "hit1": hit1, "hit3": hit3,
                       # an absent question was answered if anything came back at all
                       "answered": bool(ids),
                       "error": q.get("error")}
                if shapes:
                    row.update(_ask_keyword(ad, srv, q, want, k))
                rows.append(row)
        finally:
            srv.stop()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return rows


def _ask_keyword(ad, srv, q, want, k):
    """The same question as a keyword string, asked on the same running server.

    Asked inside the same pass rather than in a second experiment, so the two phrasings see one store,
    one restart and one binding: anything that differs between them is the phrasing and not the setup.
    """
    import words
    kw = words.keyword_form(q["query"])
    field = {"keyword": kw}
    try:
        ids = ad.search(srv, kw, k)
    except Exception as exc:
        field["keyword_error"] = str(exc)
        ids = []
    field["returned_keyword"] = ids[:k]
    field["hit1_keyword"] = bool(want) and ids[:1] == [want]
    field["hit3_keyword"] = bool(want) and want in ids[:k]
    field["answered_keyword"] = bool(ids)
    return field


def run(ad, k=3, cases_path=None, repeat=1, shapes=False):
    """Repeat the whole experiment and take each question's majority answer.

    THE INTERVAL WAS THE WRONG ERROR BAR ON ITS OWN. A Wilson interval says how much a different set
    of thirty questions might have moved the score; it says nothing about the same thirty questions
    asked twice. Both runs of the full matrix on one machine, one day, scored zenbrain 22/30 and then
    24/30 - a difference no interval on 30 questions accounts for. So the experiment is repeated, the
    per-question outcome is the majority, and the spread across runs is reported beside the total.
    Repeating also keeps the per-question pairing that compare.py needs.
    """
    cases_path = cases_path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "retrieval_corpus.json")
    with open(cases_path, encoding="utf-8") as fh:
        cases = json.load(fh)
    repeat = max(1, int(repeat))
    passes = [_one_pass(ad, cases, k, shapes) for _ in range(repeat)]
    if repeat == 1:
        return passes[0]
    rows = []
    for i, first in enumerate(passes[0]):
        same = [p[i] for p in passes]
        row = dict(first)
        # majority, with a tie resolving to the worse outcome - the same rule the probes use
        for key in ("hit1", "hit3", "answered", "hit1_keyword", "hit3_keyword",
                    "answered_keyword"):
            if not all(key in s for s in same):
                continue
            votes = [bool(s.get(key)) for s in same]
            row[key] = sum(votes) * 2 > len(votes)
        row["per_run"] = {"hit3": [bool(s.get("hit3")) for s in same],
                          "answered": [bool(s.get("answered")) for s in same]}
        rows.append(row)
    return rows


def _spread(passes, key):
    return [sum(1 for r in p if r.get(key)) for p in passes]


def summarise(rows, label):
    out = {}
    for band in ("easy", "hard", "adversarial", "absent", "all"):
        sel = [r for r in rows if band == "all" or r["difficulty"] == band]
        if not sel:
            continue
        if band == "absent":
            # nothing here can be "hit"; the number that matters is how often it spoke anyway
            out[band] = {"n": len(sel), "answered": sum(1 for r in sel if r["answered"])}
        else:
            out[band] = {"n": len(sel),
                         "hit1": sum(1 for r in sel if r["hit1"]),
                         "hit3": sum(1 for r in sel if r["hit3"])}
    print("%-24s %s" % (label, "  ".join(
        ("%s %d/%d,%d/%d" % (b[:5], v["hit1"], v["n"], v["hit3"], v["n"])) if "hit1" in v
        else ("noans %d/%d" % (v["answered"], v["n"]))
        for b, v in out.items())))
    for r in rows:
        if r["difficulty"] == "absent":
            if r["answered"]:
                print("   SPOKE %-45s returned %s" % (r["query"][:45], r["returned"][:3]))
        elif not r["hit3"]:
            print("   MISS  %-8s %-45s want %-16s got %s" % (
                r["difficulty"], r["query"][:45], r["expect"], r["returned"][:3] or "nothing"))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = None
    adapter_name = "reference"
    out_path = None
    manifest_path = None
    cases_path = None
    repeat = 1
    shapes = False
    for a in argv:
        if a.startswith("--cmd="):
            cmd = a.split("=", 1)[1]
        elif a.startswith("--adapter="):
            adapter_name = a.split("=", 1)[1]
        elif a.startswith("--json="):
            out_path = a.split("=", 1)[1]
        elif a.startswith("--manifest="):
            manifest_path = a.split("=", 1)[1]
        elif a.startswith("--timeout="):
            harness.PROBE_TIMEOUT = float(a.split("=", 1)[1])
        elif a.startswith("--cases="):
            cases_path = a.split("=", 1)[1]
        elif a.startswith("--repeat="):
            repeat = max(1, int(a.split("=", 1)[1]))
        elif a == "--shapes":
            # ask every question again as a keyword string, in the same pass
            shapes = True
    if not cmd:
        print(__doc__)
        return 2
    adapters = {"control": harness.ControlAdapter, "retained": harness.RetainedAdapter,
                "basic-memory": harness.BasicMemoryAdapter, "memento": harness.MementoAdapter,
                "auto": harness.AutoAdapter}
    label = adapter_name
    if manifest_path:
        # THE SAME ADAPTER THE PROBES USE, so a retrieval number and a conformance verdict are about
        # the same binding of the same subject.
        import manifest as manifestmod
        mf = manifestmod.load(manifest_path)
        ad = harness.ManifestAdapter(cmd, mf)
        label = mf.subject
    else:
        ad = adapters.get(adapter_name, harness.ReferenceAdapter)(cmd)
    rows = run(ad, cases_path=cases_path, repeat=repeat, shapes=shapes)
    summary = summarise(rows, label)
    if repeat > 1:
        # the spread is per-run totals before any majority was taken, which is the only honest way to
        # show how far the same experiment moved when it was repeated
        for band in ("easy", "hard", "adversarial", "absent", "all"):
            sel = [r for r in rows if band == "all" or r["difficulty"] == band]
            if not sel or band not in summary:
                continue
            key = "answered" if band == "absent" else "hit3"
            totals = [sum(1 for r in sel if r["per_run"][key][i]) for i in range(repeat)]
            summary[band]["runs"] = totals
        allv = summary.get("all") or {}
        if "runs" in allv:
            print("%-24s spread over %d runs of the whole experiment: hit@3 %s"
                  % ("", repeat, " ".join(str(t) for t in allv["runs"])))
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(json.dumps({"adapter": adapter_name, "summary": summary, "rows": rows},
                                indent=2) + chr(10))
    missed = sum(1 for r in rows if r.get("expect") and not r["hit3"])
    spoke = sum(1 for r in rows if r["difficulty"] == "absent" and r["answered"])
    absent_n = sum(1 for r in rows if r["difficulty"] == "absent")
    print("%d question(s) with an answer were missed at k=3; %d of %d questions with no answer were "
          "answered anyway" % (missed, spoke, absent_n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
