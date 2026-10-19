#!/usr/bin/env python3
"""retrieval.py - can the memory FIND what it kept?

Retention is not retrieval. A store that keeps every byte and cannot answer a question about them is
a backup, not a memory. This runs twelve memories and twelve questions at the same server the
conformance probes use, and reports hit@1 and hit@3, split into questions that share vocabulary with
the memory they want (easy) and questions that do not (hard), because the split is the whole story:
lexical systems pass the first and fail the second.

  python retrieval.py --adapter=retained --cmd="python /path/to/retained.py"
"""
import json
import os
import shutil
import sys
import tempfile

import harness


def run(ad, k=3, cases_path=None):
    cases_path = cases_path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "retrieval_cases.json")
    with open(cases_path, encoding="utf-8") as fh:
        cases = json.load(fh)
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
                rows.append({"query": q["query"], "expect": q["expect"],
                             "difficulty": q["difficulty"], "returned": ids[:k],
                             "hit1": bool(ids[:1] == [q["expect"]]),
                             "hit3": q["expect"] in ids[:k],
                             "error": q.get("error")})
        finally:
            srv.stop()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return rows


def summarise(rows, label):
    out = {}
    for band in ("easy", "hard", "all"):
        sel = [r for r in rows if band == "all" or r["difficulty"] == band]
        if not sel:
            continue
        out[band] = {"n": len(sel),
                     "hit1": sum(1 for r in sel if r["hit1"]),
                     "hit3": sum(1 for r in sel if r["hit3"])}
    print("%-12s %s" % (label, "  ".join(
        "%s %d/%d h1, %d/%d h3" % (b, v["hit1"], v["n"], v["hit3"], v["n"])
        for b, v in out.items())))
    for r in rows:
        if not r["hit3"]:
            print("   MISS  %-8s %-46s want %-12s got %s" % (
                r["difficulty"], r["query"][:46], r["expect"], r["returned"][:3] or "nothing"))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = None
    adapter_name = "reference"
    out_path = None
    for a in argv:
        if a.startswith("--cmd="):
            cmd = a.split("=", 1)[1]
        elif a.startswith("--adapter="):
            adapter_name = a.split("=", 1)[1]
        elif a.startswith("--json="):
            out_path = a.split("=", 1)[1]
    if not cmd:
        print(__doc__)
        return 2
    adapters = {"control": harness.ControlAdapter, "retained": harness.RetainedAdapter,
                "basic-memory": harness.BasicMemoryAdapter}
    ad = adapters.get(adapter_name, harness.ReferenceAdapter)(cmd)
    rows = run(ad)
    summary = summarise(rows, adapter_name)
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(json.dumps({"adapter": adapter_name, "summary": summary, "rows": rows},
                                indent=2) + chr(10))
    missed = sum(1 for r in rows if not r["hit3"])
    print("%d of %d question(s) missed at k=3" % (missed, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
