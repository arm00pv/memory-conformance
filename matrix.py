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
# IMPORTED, NOT COPIED. Four files kept their own copy of the probe list and each copy was a place
# to forget; check.py had been skipping forget for a whole phase without saying so.
import harness
PROBES = harness.PROBE_NAMES
SHORT = {"isolation": "isol", "ack_readback": "ack", "verbatim": "verb", "restart": "restart",
         "forget": "forget", "findable": "find", "foreign_field": "field",
         "foreign_record": "record", "concurrent": "conc", "large_record": "large"}
# A SHORT LABEL FOR EVERY PROBE, generated rather than listed, so a new probe cannot arrive as a
# KeyError in the middle of a twenty-minute run.
for _p in PROBES:
    SHORT.setdefault(_p, _p[:4])


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
def corpus_size():
    """How many records and questions the retrieval corpus holds, read rather than remembered.

    Three files used to state "36 records" in prose, and doubling the corpus silently falsified all
    three. A number that describes the instrument should come from the instrument.
    """
    path = os.path.join(HERE, "retrieval_corpus.json")
    if not os.path.isfile(path):
        return (0, 0)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return (len(doc.get("records") or []), len(doc.get("queries") or []))


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


def corpus_queries(corpus_path):
    """The questions a corpus file holds, as the tuples a saved report would have recorded."""
    with open(corpus_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return [(q.get("query"), q.get("expect"), q.get("difficulty")) for q in doc["queries"]]


def load_rows(path, corpus_path=None):
    """The saved per-question rows, or nothing when they answer a corpus that is no longer on disk.

    THE INSTRUMENT CAN CHANGE UNDER A NUMBER. Ten questions in retrieval_corpus.json were rewritten to
    fix the defects the validator proved, and every saved result for that corpus silently became an
    answer to a question nobody asks any more - nothing about the file's existence says so. So the rows
    are checked against the corpus they claim to be about, and a mismatch is treated as no measurement.
    """
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh).get("rows") or []
    if corpus_path and os.path.isfile(corpus_path):
        want = corpus_queries(corpus_path)
        got = [(r.get("query"), r.get("expect"), r.get("difficulty")) for r in rows]
        if got != want:
            print("  STALE: %s was measured against a different %s"
                  % (os.path.basename(path), os.path.basename(corpus_path)))
            return []
    return rows


def shape_extremes(retr):
    """The subject whose score moves most between the two phrasings, read from the summaries.

    THIS USED TO BE A NUMBER IN THE PROSE. "One subject is 6/60 and 29/60" was true when it was
    written and survived a corpus repair that moved it to 6/60 and 19/60, which is the same defect as a
    stale table with none of a table's visibility. The number now comes from the rows being printed.
    """
    worst = None
    for label, s in retr:
        a = (s or {}).get("all") or {}
        if "hit3_keyword" not in a:
            continue
        change = abs(a["hit3_keyword"] - a["hit3"])
        if worst is None or change > worst[4]:
            worst = (label, a["hit3"], a["n"], a["hit3_keyword"], change)
    return worst[:4] if worst else None


def replication_note():
    """The neighbouring-pair result, read from the report rather than remembered."""
    path = os.path.join(HERE, "REPLICATION.json")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    pairs, agree = doc.get("pairs") or 0, doc.get("agree") or 0
    if not pairs:
        return ""
    bad = pairs - agree
    return (" %d of the %d neighbouring pairs in the retrieval table do not reach the same conclusion"
            " on both, so a separation there holds for this question set until a third corpus agrees."
            % (bad, pairs)) if bad else (" Every neighbouring pair reaches the same conclusion on both.")


def run_retrieval(entry, timeout, cases=None, suffix=""):
    """Second axis: can the subject ANSWER a question about what it kept?

    The probe table cannot see this. A store that keeps everything and returns nothing on a query
    scores eight of eight on conformance, which is why retention and retrieval are measured apart and
    reported apart - they are close to independent, and the matrix would otherwise reward a perfect
    backup with a perfect score.
    """
    slug = ("%s-%s" % (entry["name"], entry["version"])).replace("/", "_").replace("@", "")
    out = os.path.join("results", slug + "-retrieval" + suffix + ".json")
    # REPEATED, BECAUSE THE INTERVAL IS THE WRONG ERROR BAR ON ITS OWN: it covers sampling variance
    # and not the same experiment run twice, which moved zenbrain by two questions in one day.
    args = [sys.executable, "retrieval.py", "--cmd=" + entry["cmd"],
            "--timeout=%d" % timeout, "--repeat=%d" % RETRIEVAL_REPEAT, "--json=" + out]
    # A SECOND CORPUS IS THE ONLY WAY TO ASK WHETHER THE ORDERING WAS AN ARTEFACT OF THE QUESTIONS.
    if cases:
        args.append("--cases=" + cases)
    # AND THE SAME QUESTION ASKED TWO WAYS IS THE ONLY WAY TO ASK WHETHER THE SCORE WAS AN ARTEFACT OF
    # THE PHRASING. On by default: a score without its shape is the incomplete measurement that corpus
    # B exposed, and it costs one extra search per question rather than a second experiment.
    args.append("--shapes")
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
            doc = json.load(fh)
        summary = doc.get("summary")
        # THE ROWS KNOW WHAT THE SUMMARY WAS WRITTEN BEFORE. A saved report predates the shape axis
        # but its per-question rows still carry both phrasings, so the keyword totals are recomputed
        # from them instead of the subject being measured again to fill in a column.
        import retrieval
        summary = retrieval.with_keywords(summary, doc.get("rows") or [])
    return report, summary


def main(argv):
    report_only = "--report-only" in argv
    cost_only = "--cost-only" in argv
    # ONE AXIS AT A TIME. Adding a probe changes the probe column and nothing else, so re-rolling
    # retrieval and cost would move numbers that did not change and invite the reader to think they
    # had. The other two axes are re-read from disk instead.
    probes_only = "--probes-only" in argv
    argv = [a for a in argv if a not in ("--report-only", "--cost-only", "--probes-only")]
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
        if probes_only:
            _saved, summary = load_saved(entry)
            retr.append((label, summary))
            cost.append((label, load_cost(entry)))
            continue
        print("  retrieval ...", flush=True)
        retr.append((label, run_retrieval(entry, int(entry.get("timeout", 60)))))
        print("  cost ...", flush=True)
        cost.append((label, run_cost(entry, int(entry.get("timeout", 60)))))

    # THE SUBJECT COLUMN SIZES ITSELF. It was fixed at 24 characters until a package whose name is
    # 34 arrived and pushed every other column out of line. A table whose alignment depends on which
    # subjects happen to be in it is a table that breaks every time it grows.
    W = max([24] + [len(label) for label, _e, _v, _s, _c in rows])

    print()
    header = "%-*s %s %5s" % (W, "subject", "  ".join("%-7s" % SHORT[p] for p in PROBES), "ceil")
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
        print("%-*s %s %4ds" % (W, label, "  ".join(cells), ceil))
    print()
    print("(x) verdict qualified by a failed isolation precondition - not publishable on its own")
    print("ceil is the per-call ceiling each subject was given; a verdict measured at one ceiling")
    print("does not transfer to another, and memento is the proof: same machine, PASS at 180s and")
    print("FAIL at 60s on the same probe.")
    oos = sum(1 for _l, _e, v, _s, _c in rows if v.get("isolation") != "PASS")
    print("%d subject(s) out of scope, %d measured" % (oos, len(rows) - oos))

    # --- second axis -------------------------------------------------------
    print()
    n_rec, n_q = corpus_size()
    print("retrieval, cold start, %d records and %d questions - a score, not a verdict. hit@3 per"
          % (n_rec, n_q))
    print("per band - easy shares wording with the answer, hard is a paraphrase, adversarial has a")
    print("near duplicate competing. 'noans' is questions with no answer that were answered anyway;")
    print("0 is right.")
    header2 = "%-*s %-7s %-7s %-7s %-8s %-8s %-8s %-8s %-7s %-9s %s" % (
        W, "subject", "easy", "hard", "adver", "all h1", "all h3", "kw h3", "change", "noans",
        "runs", "95%")
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
        kw = "%d/%d" % (a["hit3_keyword"], a["n"]) if a and "hit3_keyword" in a else "-"
        change = ("%+d" % (a["hit3_keyword"] - a["hit3"])) if a and "hit3_keyword" in a else "-"
        print("%-*s %-7s %-7s %-7s %-8s %-8s %-8s %-8s %-7s %-9s %s" % (
            W, label, cells[0], cells[1], cells[2],
            "%d/%d" % (a["hit1"], a["n"]) if a else "-",
            "%d/%d" % (a["hit3"], a["n"]) if a else "-", kw, change,
            "%d/%d" % (ab["answered"], ab["n"]) if ab else "-", runs, ci))
    print()
    print("'runs' is the min-max of the same experiment repeated %d times; '95%%' is the Wilson"
          % RETRIEVAL_REPEAT)
    print("interval for the majority result, in counts. The first covers repeating the experiment,")
    print("the second covers asking a different set of %d questions. They are not the same error."
          % n_q)
    worst = shape_extremes(retr)
    print("'kw h3' is the same %d questions asked again with the words that carry no meaning removed:"
          % n_q)
    if worst:
        print("%s is %d/%d one way and %d/%d the other on the same corpus, so a score quoted without"
              % (worst[0], worst[1], worst[2], worst[3], worst[2]))
        print("its phrasing is half a measurement. Per-band detail is in SHAPE.md.")
    else:
        print("a score quoted without its phrasing is half a measurement. Per-band detail is in SHAPE.md.")

    # --- third axis --------------------------------------------------------
    print()
    print("cost, measured once per subject with nothing else running. 'resp' is the median bytes the")
    print("server sends back for one question and 'amp' is that divided by the answer's own size - a")
    print("system that answers by returning the whole store shows up here. A subject that returns")
    print("nothing is cheap for the wrong reason, so read this table with the one above it.")
    header3 = "%-*s %-8s %-8s %-9s %-9s %-8s %-7s %-7s" % (
        W, "subject", "startup", "lst write", "write p50", "search p50", "resp B", "amp", "vary")
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
        print("%-*s %7.2fs %7.2fs %8.3fs %8.3fs %8d %7s %7s" % (
            W, label, c["startup_p50"], c["first_write"], c["write_p50"], c["search_p50"],
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
        fh.write("%d records, %d questions, cold start. hit@3 per band; \"easy\" shares wording with"
                 % (n_rec, n_q) +
                 " its answer, \"hard\" is a paraphrase, \"adversarial\" has a near duplicate competing."
                 " \"noans\" is questions with no answer in the store that were answered anyway." + chr(10) + chr(10))
        fh.write("| subject | easy h3 | hard h3 | adversarial h3 | all h1 | all h3 | h3 as keywords"
                 " | change | no-answer answered | runs | h3 95% |" + chr(10))
        fh.write("|---|---|---|---|---|---|---|---|---|---|---|" + chr(10))
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
            cells.append(("%d/%d" % (a["hit3_keyword"], a["n"])) if a and "hit3_keyword" in a else "-")
            cells.append(("%+d" % (a["hit3_keyword"] - a["hit3"])) if a and "hit3_keyword" in a else "-")
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
        # THE TABLE ABOVE IS ONE CORPUS'S OPINION. Saying so in the generated file, rather than only in
        # the README, is the difference between a number with a caveat and a number without one.
        if os.path.isfile(os.path.join(HERE, "REPLICATION.md")):
            fh.write(chr(10) + "## Replication" + chr(10) + chr(10) +
                     "The same subjects on a second corpus, written by an author who never saw this one,"
                     " are compared in `REPLICATION.md`." + replication_note() + chr(10))
        if os.path.isfile(os.path.join(HERE, "SHAPE.md")):
            worst = shape_extremes(retr)
            fh.write(chr(10) + "The retrieval score is also a pair: every question is asked again with"
                     " the words that carry no meaning removed, and `SHAPE.md` reports the gap."
                     + ((" %s is %d/%d one way and %d/%d the other on the same corpus, so a hit@3"
                         " number without its phrasing is half a measurement."
                         % (worst[0], worst[1], worst[2], worst[3], worst[2]))
                        if worst else
                        " A hit@3 number without its phrasing is half a measurement.")
                     + chr(10))
    print("written to MATRIX.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))