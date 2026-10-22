#!/usr/bin/env python3
"""matrix.py - run every declared subject and print one table.

A single rank is a lie by omission: these subjects fail on different axes, so the output is a
per-probe matrix rather than a score. Every cell comes from a run saved under results/, so any
number here can be reproduced from the command in subjects.json.

  python matrix.py                 # every declared subject
  python matrix.py memento memdb   # by name

A subject that fails the isolation probe is marked out-of-scope: its other verdicts describe leaked
state, and printing them without that marker is how a conformance report ends up lying.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = ["isolation", "ack_readback", "restart", "findable", "foreign_field", "foreign_record",
          "concurrent", "large_record"]
SHORT = {"isolation": "isol", "ack_readback": "ack", "restart": "restart", "findable": "find",
         "foreign_field": "field", "foreign_record": "record", "concurrent": "conc",
         "large_record": "large"}


def wilson(k, n, z=1.96):
    """The 95% Wilson interval for k successes in n trials, returned in COUNTS.

    Thirty questions is enough to separate 12 from 0 and not enough to separate 19 from 21. Quoting
    the raw fraction invites a reader to rank subjects on a difference that is inside the noise, so
    the interval travels with the number and the two rows visibly overlap.

    Wilson rather than the textbook interval because at 0/30 and 30/30 the textbook interval collapses
    to zero width and claims a precision the sample cannot support.
    """
    if not n:
        return (0, 0)
    p = k / float(n)
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = (z * ((p * (1.0 - p) / n + z * z / (4.0 * n * n)) ** 0.5)) / denom
    return (int(round((centre - half) * n)), int(round((centre + half) * n)))


PROBE_REPEAT = 3
RETRIEVAL_REPEAT = 3
COST_REPEAT = 3
# The cost metrics whose movement is a statement about the subject. Process spawn and restart are
# left out on purpose: they are dominated by the operating system's cache and fork cost, and letting
# them into one "vary" number would hide that the writes themselves are rock steady.
STEADY = ("first_write", "write_p50", "search_p50", "resp_bytes_p50")
# A RATIO NEEDS SOMETHING TO DIVIDE BY. memdb's write is 1 ms and moved to 1 ms; reported as a
# percentage of its own median that is "200%" and means nothing at all. Metrics whose median is
# below this floor are excluded from the variability figure and left in the JSON, where their
# absolute ranges are stated. Bytes are always included: they are never that small.
VARY_FLOOR_SECONDS = 0.02


def steady_vary(cost):
    """How far the steady-state measurements of one subject moved across the passes."""
    sp = (cost or {}).get("spread") or {}
    worst = 0.0
    for key in STEADY:
        s = sp.get(key)
        if not s or not s.get("median"):
            continue
        if not key.startswith("resp") and s["median"] < VARY_FLOOR_SECONDS:
            continue
        worst = max(worst, (s["max"] - s["min"]) / s["median"])
    return worst if sp else None


def run_retrieval(entry, timeout):
    """Second axis: can the subject ANSWER a question about what it kept?

    The probe table cannot see this. A store that keeps everything and returns nothing on a query
    scores eight of eight on conformance, which is why retention and retrieval are measured apart and
    reported apart - they are close to independent, and the matrix would otherwise reward a perfect
    backup with a perfect score.
    """
    slug = ("%s-%s" % (entry["name"], entry["version"])).replace("/", "_").replace("@", "")
    out = os.path.join("results", slug + "-retrieval.json")
    # REPEATED, BECAUSE THE INTERVAL IS THE WRONG ERROR BAR ON ITS OWN: it covers sampling variance
    # and not the same experiment run twice, which moved zenbrain by two questions in one day.
    args = [sys.executable, "retrieval.py", "--cmd=" + entry["cmd"],
            "--timeout=%d" % timeout, "--repeat=%d" % RETRIEVAL_REPEAT, "--json=" + out]
    args += (["--manifest=" + entry["manifest"]] if entry.get("manifest")
             else ["--adapter=" + entry.get("adapter", "reference")])
    subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.isfile(out):
        return None
    with open(out, encoding="utf-8") as fh:
        return json.load(fh).get("summary")


def run(entry, timeout):
    args = [sys.executable, "harness.py", "--cmd=" + entry["cmd"], "--timeout=%d" % timeout]
    args += (["--manifest=" + entry["manifest"]] if entry.get("manifest")
             else ["--adapter=" + entry.get("adapter", "reference")])
    # EVERY PROBE, EVERY SUBJECT. Repeating only the probes that have been seen to flake is the
    # assumption that has had to be retracted twice already, on the cost table and on the retrieval
    # table. A subject may override the count, never the coverage.
    args.append("--repeat=%d" % int(entry.get("repeat", PROBE_REPEAT)))
    if entry.get("expect"):
        args.append("--expect=" + entry["expect"])
    slug = ("%s-%s" % (entry["name"], entry["version"])).replace("/", "_").replace("@", "")
    os.makedirs("results", exist_ok=True)
    out = os.path.join("results", slug + ".json")
    args.append("--json=" + out)
    t0 = time.time()
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.isfile(out):
        return None, proc, time.time() - t0
    with open(out, encoding="utf-8") as fh:
        return json.load(fh), proc, time.time() - t0


def load_cost(entry):
    """The cached measurement, or None. --report-only must never launch a subject."""
    path = os.path.join("results", slug_of(entry) + "-cost.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run_cost(entry, timeout, force=False):
    """Third axis: the bill. Reads results/<slug>-cost.json, running cost.py only if absent.

    Cost is measured once and cached rather than re-measured with every matrix run, because a
    timing taken while nine other subjects are running is a timing of the machine.
    """
    slug = slug_of(entry)
    out = os.path.join("results", slug + "-cost.json")
    if force or not os.path.isfile(out):
        args = [sys.executable, "cost.py", "--cmd=" + entry["cmd"],
                "--timeout=%d" % timeout, "--repeat=%d" % COST_REPEAT, "--json=" + out]
        args += (["--manifest=" + entry["manifest"]] if entry.get("manifest")
                 else ["--adapter=" + entry.get("adapter", "reference")])
        subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.isfile(out):
        return None
    with open(out, encoding="utf-8") as fh:
        return json.load(fh)


def slug_of(entry):
    return ("%s-%s" % (entry["name"], entry["version"])).replace("/", "_").replace("@", "")


def load_saved(entry):
    """Re-render the tables from the reports already on disk, without re-running anything.

    A conformance verdict is worth nothing if the table around it can only be produced by a
    twenty-minute run, so the rendering is separable from the measuring.
    """
    slug = slug_of(entry)
    probes = os.path.join("results", slug + ".json")
    retr = os.path.join("results", slug + "-retrieval.json")
    report = None
    summary = None
    if os.path.isfile(probes):
        with open(probes, encoding="utf-8") as fh:
            report = json.load(fh)
    if os.path.isfile(retr):
        with open(retr, encoding="utf-8") as fh:
            summary = json.load(fh).get("summary")
    return report, summary


def main(argv):
    report_only = "--report-only" in argv
    cost_only = "--cost-only" in argv
    argv = [a for a in argv if a not in ("--report-only", "--cost-only")]
    want = set(argv)
    with open(os.path.join(HERE, "subjects.json"), encoding="utf-8") as fh:
        subjects = json.load(fh)
    if cost_only:
        # Timings are taken in one quiet pass of their own rather than interleaved with the probes,
        # because a write timed while nine other subjects are being probed is a timing of the machine.
        for entry in subjects:
            if want and entry["name"] not in want:
                continue
            label = "%s %s" % (entry["name"], entry["version"])
            print("cost %s ..." % label, flush=True)
            m = run_cost(entry, int(entry.get("timeout", 60)), force=True)
            print("  %s" % ("no measurement" if not m else
                            "startup %.2fs write %.3fs search %.3fs resp %d B x%s"
                            % (m["startup_p50"], m["write_p50"], m["search_p50"],
                               m["resp_bytes_p50"], m.get("amp"))), flush=True)
        return 0

    rows = []
    retr = []
    cost = []
    for entry in subjects:
        label = "%s %s" % (entry["name"], entry["version"])
        if want and entry["name"] not in want:
            continue
        if report_only:
            report, summary = load_saved(entry)
            secs = 0.0
            if report is None:
                print("  no saved report for %s" % label)
                rows.append((label, entry, {p: "ERROR" for p in PROBES}, secs, 0))
                retr.append((label, summary))
                cost.append((label, load_cost(entry)))
                continue
            got = {r["probe"]: r for r in report["probes"]}
            rows.append((label, entry, {p: got.get(p, {}).get("verdict", "-") for p in PROBES},
                         secs, int(report.get("ceiling_seconds") or 0)))
            retr.append((label, summary))
            cost.append((label, load_cost(entry)))
            continue
        print("running %s ..." % label, flush=True)
        report, proc, secs = run(entry, int(entry.get("timeout", 60)))
        if report is None:
            print("  no report; stderr tail: %s" % proc.stderr.strip()[-300:])
            rows.append((label, entry, {p: "ERROR" for p in PROBES}, secs, 0))
            continue
        got = {r["probe"]: r for r in report["probes"]}
        rows.append((label, entry, {p: got.get(p, {}).get("verdict", "-") for p in PROBES}, secs,
                     int(report.get("ceiling_seconds") or 0)))
        print("  retrieval ...", flush=True)
        retr.append((label, run_retrieval(entry, int(entry.get("timeout", 60)))))
        print("  cost ...", flush=True)
        cost.append((label, run_cost(entry, int(entry.get("timeout", 60)))))

    print()
    header = "%-24s %s %5s" % ("subject", "  ".join("%-7s" % SHORT[p] for p in PROBES), "ceil")
    print(header)
    print("-" * len(header))
    for label, _e, v, _s, ceil in rows:
        out_of_scope = v.get("isolation") != "PASS"
        cells = []
        for p in PROBES:
            cell = v[p]
            if out_of_scope and p != "isolation":
                cell = "(" + cell + ")"
            cells.append("%-7s" % cell)
        print("%-24s %s %4ds" % (label, "  ".join(cells), ceil))
    print()
    print("(x) verdict qualified by a failed isolation precondition - not publishable on its own")
    print("ceil is the per-call ceiling each subject was given; a verdict measured at one ceiling")
    print("does not transfer to another, and memento is the proof: same machine, PASS at 180s and")
    print("FAIL at 60s on the same probe.")
    oos = sum(1 for _l, _e, v, _s, _c in rows if v.get("isolation") != "PASS")
    print("%d subject(s) out of scope, %d measured" % (oos, len(rows) - oos))

    # --- second axis -------------------------------------------------------
    print()
    print("retrieval, cold start, 36 records - a score, not a verdict. hit@3 per band: easy shares")
    print("wording with the answer, hard is a paraphrase, adversarial has a near duplicate competing.")
    print("'noans' is questions with no answer in the store that were answered anyway: 0 is right.")
    header2 = "%-24s %-7s %-7s %-7s %-8s %-8s %-7s %-9s %s" % (
        "subject", "easy", "hard", "adver", "all h1", "all h3", "noans", "runs", "95%")
    print(header2)
    print("-" * len(header2))
    for label, s in retr:
        if not s:
            print("%-24s %s" % (label, "no report"))
            continue
        cells = []
        for band in ("easy", "hard", "adversarial"):
            v = s.get(band)
            cells.append("%d/%d" % (v["hit3"], v["n"]) if v else "-")
        a = s.get("all") or {}
        ab = s.get("absent") or {}
        ci = ""
        if a:
            lo, hi = wilson(a["hit3"], a["n"])
            ci = "%d-%d" % (lo, hi)
        runs = ""
        if a and a.get("runs"):
            runs = "%d-%d" % (min(a["runs"]), max(a["runs"]))
        print("%-24s %-7s %-7s %-7s %-8s %-8s %-7s %-9s %s" % (
            label, cells[0], cells[1], cells[2],
            "%d/%d" % (a["hit1"], a["n"]) if a else "-",
            "%d/%d" % (a["hit3"], a["n"]) if a else "-",
            "%d/%d" % (ab["answered"], ab["n"]) if ab else "-", runs, ci))
    print()
    print("'runs' is the min-max of the same experiment repeated %d times; '95%%' is the Wilson"
          % RETRIEVAL_REPEAT)
    print("interval for the majority result, in counts. The first covers repeating the experiment,")
    print("the second covers asking a different thirty questions. They are not the same error.")

    # --- third axis --------------------------------------------------------
    print()
    print("cost, measured once per subject with nothing else running. 'resp' is the median bytes the")
    print("server sends back for one question and 'amp' is that divided by the answer's own size - a")
    print("system that answers by returning the whole store shows up here. A subject that returns")
    print("nothing is cheap for the wrong reason, so read this table with the one above it.")
    header3 = "%-24s %-8s %-8s %-9s %-9s %-8s %-7s %-7s" % (
        "subject", "startup", "lst write", "write p50", "search p50", "resp B", "amp", "vary")
    print(header3)
    print("-" * len(header3))
    for label, c in cost:
        if not c:
            print("%-24s no measurement" % label)
            continue
        vary = ""
        sv = steady_vary(c)
        if sv is not None:
            vary = "%.0f%%" % (sv * 100)
        print("%-24s %7.2fs %7.2fs %8.3fs %8.3fs %8d %7s %7s" % (
            label, c["startup_p50"], c["first_write"], c["write_p50"], c["search_p50"],
            c["resp_bytes_p50"], ("x%.0f" % c["amp"]) if c.get("amp") else "-", vary))
    print()
    print("'vary' is how far the worst steady-state measurement moved across %d passes, as a fraction"
          % COST_REPEAT)
    print("of its own median: first write, write, search and response bytes, with timings under %d ms"
          % int(VARY_FLOOR_SECONDS * 1000))
    print("left out because a ratio of millisecond noise is not a measurement. Absolute ranges and")
    print("the noisier startup/restart figures are in results/*-cost.json.")

    with open("MATRIX.md", "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write("# Measured subjects" + chr(10) + chr(10))
        fh.write("| subject | " + " | ".join(PROBES) + " | ceiling |" + chr(10))
        fh.write("|---" * (len(PROBES) + 2) + "|" + chr(10))
        for label, _e, v, _s, ceil in rows:
            bad = v.get("isolation") != "PASS"
            cells = [v[p] if (p == "isolation" or not bad) else "(%s)" % v[p] for p in PROBES]
            fh.write("| %s | %s | %ds |" % (label, " | ".join(cells), ceil) + chr(10))
        fh.write(chr(10) + "Cells in parentheses belong to a subject that failed `isolation`; its"
                 " other verdicts describe leaked state." + chr(10))
        fh.write(chr(10) + "## Retrieval: a score, not a verdict" + chr(10) + chr(10))
        fh.write("36 records, 30 questions, cold start. hit@3 per band; \"easy\" shares wording with"
                 " its answer, \"hard\" is a paraphrase, \"adversarial\" has a near duplicate competing."
                 " \"noans\" is questions with no answer in the store that were answered anyway." + chr(10) + chr(10))
        fh.write("| subject | easy h3 | hard h3 | adversarial h3 | all h1 | all h3 | no-answer answered"
                 " | runs | h3 95% |" + chr(10))
        fh.write("|---|---|---|---|---|---|---|---|---|" + chr(10))
        for label, s in retr:
            if not s:
                fh.write("| %s | - | - | - | - | - | - | - | - |" % label + chr(10))
                continue
            cells = []
            for band in ("easy", "hard", "adversarial"):
                v = s.get(band)
                cells.append("%d/%d" % (v["hit3"], v["n"]) if v else "-")
            a = s.get("all") or {}
            ab = s.get("absent") or {}
            cells.append("%d/%d" % (a["hit1"], a["n"]) if a else "-")
            cells.append("%d/%d" % (a["hit3"], a["n"]) if a else "-")
            cells.append("%d/%d" % (ab["answered"], ab["n"]) if ab else "-")
            cells.append(("%d-%d" % (min(a["runs"]), max(a["runs"]))) if a and a.get("runs") else "-")
            cells.append(("%d-%d" % wilson(a["hit3"], a["n"])) if a else "-")
            fh.write("| %s | %s |" % (label, " | ".join(cells)) + chr(10))
        fh.write(chr(10) + "The last column is the 95% Wilson interval for all-band hit@3, in counts."
                 " Two subjects whose intervals overlap are not separated by this corpus." + chr(10))
        fh.write(chr(10) + "## Cost" + chr(10) + chr(10))
        fh.write("Measured once per subject with nothing else running. \"resp\" is the median bytes"
                 " returned for one question and \"amp\" is that divided by the answer's own size."
                 " A subject that returns nothing is cheap for the wrong reason - read this table"
                 " with the retrieval one." + chr(10) + chr(10))
        fh.write("| subject | startup | first write | write p50 | search p50 | resp bytes | amp |"
                 " store B/rec | vary |" + chr(10))
        fh.write("|---|---|---|---|---|---|---|---|---|" + chr(10))
        for label, c in cost:
            if not c:
                fh.write("| %s | - | - | - | - | - | - | - | - |" % label + chr(10))
                continue
            sv = steady_vary(c)
            vary = ("%.0f%%" % (sv * 100)) if sv is not None else "-"
            fh.write("| %s | %.2fs | %.2fs | %.3fs | %.3fs | %d | %s | %s | %s |" % (
                label, c["startup_p50"], c["first_write"], c["write_p50"], c["search_p50"],
                c["resp_bytes_p50"], ("x%.0f" % c["amp"]) if c.get("amp") else "-",
                c["store_bytes_per_record"] if c["store_bytes_per_record"] is not None else "-",
                vary) + chr(10))
        fh.write(chr(10) + "`vary` is how far the worst steady-state measurement moved across %d"
                 " passes, as a fraction of its own median: first write, write, search and response"
                 " bytes, with timings under %d ms excluded because a ratio of millisecond noise is"
                 " not a measurement. Absolute ranges and the noisier startup and restart figures"
                 " are in `results/*-cost.json`." % (COST_REPEAT, int(VARY_FLOOR_SECONDS * 1000))
                 + chr(10))
    print("written to MATRIX.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))