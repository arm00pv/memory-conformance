#!/usr/bin/env python3
"""cost.py - what does it cost to keep a memory, and to ask it a question?

A memory that is right and unusably slow is not a memory, and one that answers a twenty-byte
question with four hundred kilobytes is not token-lean however it is described. Retention and
retrieval are measured elsewhere; this measures the bill.

  startup       seconds from spawn to `initialize` answered, cold
  first write   seconds for the first acknowledged write into a fresh store - some subjects pay
                their whole index cost here, and an agent runtime that caps a tool call at 10-30 s
                feels this one first
  write p50     seconds per acknowledged write, steady state (the first is excluded; it is above)
  search p50    seconds per search on a server that never saw the writes
  resp bytes    median bytes the server actually sends back for one question
  amp           those bytes divided by the size of the correct record, so "answers by returning the
                whole store" shows up as a multiplier instead of a shrug
  store B/rec   marginal on-disk bytes per record, or null when the subject has no declared store

FOUR RULES, BECAUSE A NUMBER WITHOUT THEM IS A NUMBER ABOUT THE MACHINE:
  1. every timing is a distribution - p50 is reported with the max beside it
  2. the call ceiling is a parameter and is recorded in the output
  3. a metric that cannot be measured is null, never zero
  4. the machine was busy or it was not; the spread is the only thing that says which

  python cost.py --manifest=manifests/memdb.json --cmd="node node_modules/@j0hanz/memdb/dist/index.js"
"""
import json
import os
import shutil
import statistics
import sys
import tempfile
import time

import harness

HERE = os.path.dirname(os.path.abspath(__file__))


def _dir_bytes(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


# The four columns that are measurements rather than counts. A count is exact and repeating it
# wastes an afternoon; a timing is an observation of the machine and is worth repeating.
TIMED = ("startup_p50", "first_write", "write_p50", "restart", "search_p50")


def measure(ad, writes=15, searches=8, repeat_start=3, repeat=1):
    """Run the whole cost experiment N times and report each timing as a median with its range.

    A SINGLE PASS CANNOT TELL THE SUBJECT FROM THE MOMENT. The retrieval table learned this the hard
    way and then found it had nothing to learn; the cost table had not been asked at all. The two are
    not symmetric: retrieval turned out to be perfectly repeatable, and a timing never is, because
    the machine underneath it is not.
    """
    repeat = max(1, int(repeat))
    runs = [_measure_once(ad, writes, searches, repeat_start) for _ in range(repeat)]
    if repeat == 1:
        return runs[0]
    out = dict(runs[0])
    out["repeat"] = repeat
    spread = {}
    for key in TIMED:
        vals = [r[key] for r in runs]
        med = statistics.median(vals)
        out[key] = round(med, 4)
        spread[key] = {"min": round(min(vals), 4), "median": round(med, 4),
                       "max": round(max(vals), 4)}
    # BYTES VARY TOO, AND ARE NOT "EXACT" IN THE WAY THEY LOOK. A byte count is exact for one
    # response; the response itself is the subject's choice, and memory-mcp-1file returned 4,838
    # bytes on one pass and 2,414 on another for the same thirty questions. Reporting run 0 would
    # have published whichever number the coin landed on.
    for key in ("resp_bytes_p50", "resp_bytes_max"):
        vals = [r[key] for r in runs]
        out[key] = int(statistics.median(vals))
        spread[key] = {"min": int(min(vals)), "median": out[key], "max": int(max(vals))}
    if out["answer_bytes"]:
        out["amp"] = round(out["resp_bytes_p50"] / out["answer_bytes"], 1)
    out["spread"] = spread
    # how far the worst measurement moved, as a fraction of its own median
    worst = 0.0
    for key in TIMED + ("resp_bytes_p50",):
        s = spread[key]
        if s["median"]:
            worst = max(worst, (s["max"] - s["min"]) / s["median"])
    out["relative_spread"] = round(worst, 3)
    # counts and byte totals are exact; take the median only because the on-disk layout can differ
    # by a page between runs, and never let that become a claim about the subject
    for key in ("store_bytes_per_record", "store_floor_bytes"):
        vals = [r.get(key) for r in runs if r.get(key) is not None]
        out[key] = int(statistics.median(vals)) if vals else None
    return out


def _measure_once(ad, writes, searches, repeat_start):
    if hasattr(ad, "reset"):
        ad.reset()
    with open(os.path.join(HERE, "retrieval_corpus.json"), encoding="utf-8") as fh:
        corpus = json.load(fh)
    # TWO BATCHES, NOT ONE. Dividing the store size by the record count measures the subject's
    # preallocation floor as if it were per-record growth: memento reads 350 kB/record that way when
    # its store is in fact a fixed 4.3 MB whatever it holds. The marginal between two batches is the
    # number that answers "what does one more memory cost", and the floor is reported beside it.
    batch1 = corpus["records"][:writes]
    batch2 = corpus["records"][writes:writes * 2]
    queries = [q for q in corpus["queries"] if q.get("expect")][:searches]
    by_id = {r["id"]: r for r in corpus["records"]}
    out = {"writes": len(batch1) + len(batch2), "searches": len(queries),
           "ceiling_seconds": harness.PROBE_TIMEOUT}

    # --- startup: cold, on a store the subject has never seen
    starts = []
    for _ in range(repeat_start):
        d = tempfile.mkdtemp(prefix="cost_start_")
        try:
            t0 = time.perf_counter()
            srv = ad.server(d)
            starts.append(time.perf_counter() - t0)
            srv.stop()
        finally:
            shutil.rmtree(d, ignore_errors=True)
    out["startup_p50"] = round(statistics.median(starts), 3)
    out["startup_max"] = round(max(starts), 3)

    d = tempfile.mkdtemp(prefix="cost_")
    try:
        srv = ad.server(d)
        try:
            write_times = []
            for rec in batch1:
                t0 = time.perf_counter()
                ad.write(srv, rec["id"], [rec["text"]])
                write_times.append(time.perf_counter() - t0)
            size_a = _dir_bytes(d)
            for rec in batch2:
                t0 = time.perf_counter()
                ad.write(srv, rec["id"], [rec["text"]])
                write_times.append(time.perf_counter() - t0)
            size_b = _dir_bytes(d)
        finally:
            srv.stop()
        out["first_write"] = round(write_times[0], 3)
        rest = write_times[1:] or write_times
        out["write_p50"] = round(statistics.median(rest), 3)
        out["write_max"] = round(max(write_times), 3)

        # on-disk cost of a record, measured as a marginal - a store that preallocates is not
        # "4 MB per record", and saying so would be a claim about the store's floor, not its growth
        if getattr(ad, "store_kind", None) and batch1 and batch2:
            out["store_floor_bytes"] = int(size_a)
            out["store_bytes_per_record"] = int((size_b - size_a) / len(batch2))
        else:
            out["store_floor_bytes"] = None
            out["store_bytes_per_record"] = None

        t0 = time.perf_counter()
        srv = ad.server(d)
        out["restart"] = round(time.perf_counter() - t0, 3)
        search_times = []
        resp_bytes = []
        try:
            for q in queries:
                t0 = time.perf_counter()
                text = ad.search_text(srv, q["query"], 3)
                search_times.append(time.perf_counter() - t0)
                resp_bytes.append(len(text.encode("utf-8")))
        finally:
            srv.stop()
        out["search_p50"] = round(statistics.median(search_times), 3)
        out["search_max"] = round(max(search_times), 3)
        out["resp_bytes_p50"] = int(statistics.median(resp_bytes))
        out["resp_bytes_max"] = int(max(resp_bytes))
        answer = statistics.median(len(by_id[q["expect"]]["text"].encode("utf-8")) for q in queries)
        out["answer_bytes"] = int(answer)
        out["amp"] = round(out["resp_bytes_p50"] / answer, 1) if answer else None
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = None
    adapter_name = "reference"
    manifest_path = None
    out_path = None
    writes, searches, repeat = 15, 8, 1
    for a in argv:
        if a.startswith("--cmd="):
            cmd = a.split("=", 1)[1]
        elif a.startswith("--adapter="):
            adapter_name = a.split("=", 1)[1]
        elif a.startswith("--manifest="):
            manifest_path = a.split("=", 1)[1]
        elif a.startswith("--json="):
            out_path = a.split("=", 1)[1]
        elif a.startswith("--writes="):
            writes = int(a.split("=", 1)[1])
        elif a.startswith("--searches="):
            searches = int(a.split("=", 1)[1])
        elif a.startswith("--repeat="):
            repeat = max(1, int(a.split("=", 1)[1]))
        elif a.startswith("--timeout="):
            harness.PROBE_TIMEOUT = float(a.split("=", 1)[1])
    if not cmd:
        print(__doc__)
        return 2
    adapters = {"control": harness.ControlAdapter, "retained": harness.RetainedAdapter,
                "basic-memory": harness.BasicMemoryAdapter, "memento": harness.MementoAdapter,
                "auto": harness.AutoAdapter}
    label = adapter_name
    if manifest_path:
        import manifest as manifestmod
        mf = manifestmod.load(manifest_path)
        ad = harness.ManifestAdapter(cmd, mf)
        label = mf.subject
    else:
        ad = adapters.get(adapter_name, harness.ReferenceAdapter)(cmd)
    m = measure(ad, writes, searches, repeat=repeat)
    print("%-24s startup %5.2fs | first write %6.2fs | write p50 %5.2fs (max %5.2fs) | "
          "search p50 %5.2fs (max %5.2fs) | resp %7d B (x%.0f) | store %s B/rec"
          % (label, m["startup_p50"], m["first_write"], m["write_p50"], m["write_max"],
             m["search_p50"], m["search_max"], m["resp_bytes_p50"], m["amp"] or 0,
             m["store_bytes_per_record"] if m["store_bytes_per_record"] is not None else "-"))
    if m.get("store_floor_bytes") is not None:
        print("%-24s store floor at %d records: %d bytes" % ("", m["writes"] // 2,
                                                             m["store_floor_bytes"]))
    if m.get("spread"):
        print("%-24s over %d passes:" % ("", m["repeat"]))
        for key in TIMED + ("resp_bytes_p50",):
            s = m["spread"][key]
            if key.startswith("resp"):
                print("%-24s   %-11s %6d B   (%d - %d)" % ("", key, s["median"],
                                                           s["min"], s["max"]))
            else:
                print("%-24s   %-11s %6.3fs   (%.3f - %.3f)" % ("", key, s["median"],
                                                               s["min"], s["max"]))
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(json.dumps(dict(m, subject=label, command=cmd), indent=2) + chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
