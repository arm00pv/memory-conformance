#!/usr/bin/env python3
"""mutants.py - break one promise at a time and check that the probe watching it says so.

THE GAP THIS CLOSES. Every subject in this suite was measured once, by probes that had never been
shown to fail on that subject. The control proves the probes CAN pass; nothing proved they CAN fail.
That is not a theoretical worry here - the forget probe shipped with six PASSes, five "this subject
cannot be asked" and no FAIL at all, so nothing in the published table distinguished "the probe
found no defect" from "the probe would not have noticed one".

So: take the control, break exactly one promise in it, and predict - in the registry below, before
running anything - the verdict every one of the nine probes must return. Then run the whole suite
against it and compare. A mutant that is not failed by the probe aimed at it is a hole in the suite,
and it is found here rather than by whoever trusted the table.

THE PREDICTION IS THE TEST, NOT THE OBSERVATION. Filling in the expected vector from what the run
happened to print would make this a description of the code instead of a check on it. The vectors
below were written against the probes as read, including which mutations cannot fail a probe alone -
so every disagreement is either a bad mutant or a probe that does not do what its docstring says,
and both are worth stopping for.

WHY TWO ROOTS CANNOT BE ISOLATED. ack_readback asks whether one acknowledged write survives the
process; every other probe begins by writing and then reading, so a subject that loses writes fails
all of them. restart asks the same question three times over three lifetimes. No mutation can break
the first without breaking the second, and the table says so instead of pretending otherwise.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "control", "memory_server.py")

import harness

# THE SAME LIST THE SUITE RUNS, imported rather than copied: a battery that predicts verdicts for a
# probe list of its own is measuring a suite that may not be the one being shipped.
PROBES = harness.PROBE_NAMES

SHORT = {"isolation": "iso", "ack_readback": "ack", "verbatim": "vbt", "restart": "rst",
         "forget": "fgt", "findable": "fnd", "foreign_field": "ffd", "foreign_record": "frc",
         "concurrent": "cnc", "large_record": "lrg"}
for _p in PROBES:
    SHORT.setdefault(_p, _p[:3])


def expect(**over):
    """Every probe passes unless the mutation says otherwise - stated, not defaulted."""
    row = dict((p, "PASS") for p in PROBES)
    for key, value in over.items():
        if key not in row:
            raise SystemExit("unknown probe in expectation: %s" % key)
        row[key] = value
    return row


MUTANTS = [
    dict(name="leak-everywhere", breaks="isolation",
         what="Every write is also written outside the store directory and every read returns both, "
              "so two separate stores are one store. This is memory-mcp-1file's defect.",
         expect=expect(isolation="FAIL")),
    dict(name="no-persist", breaks="ack_readback",
         what="A write is acknowledged and never stored. Everything downstream reads a store that "
              "was never written, so the failure propagates by construction.",
         expect=expect(ack_readback="FAIL", verbatim="FAIL", restart="FAIL", forget="UNKNOWN",
                       findable="FAIL", foreign_field="UNKNOWN", concurrent="FAIL",
                       large_record="FAIL")),
    dict(name="keep-last", breaks="restart",
         what="Each write replaces the store with itself, so one write survives and three do not. "
              "The root probes come apart here: ack_readback still passes it.",
         # VERBATIM IS HERE BECAUSE THE PROBE GREW A SECOND RECORD. This prediction said PASS while
         # the probe wrote one record and the mutation keeps the newest; the probe now writes a canary
         # as well, so keep-last drops one of the two and the probe fails for the same reason restart
         # does. The prediction was stale, not the code. Recorded rather than quietly corrected.
         expect=expect(restart="FAIL", verbatim="FAIL", forget="UNKNOWN", findable="FAIL",
                       foreign_field="FAIL", foreign_record="FAIL", concurrent="FAIL")),
    dict(name="no-forget", breaks="forget",
         what="memory_forget answers ok and writes nothing. The record is still readable after the "
              "restart, which is the exact failure the caller cannot see.",
         expect=expect(forget="FAIL")),
    dict(name="forget-all", breaks="forget",
         what="memory_forget deletes every record instead of the one named. From the caller's side "
              "the answer is identical to a clean delete, so only a probe that also checks what "
              "nobody asked to remove can tell them apart.",
         expect=expect(forget="UNKNOWN")),
    dict(name="reshape-modelled", breaks="foreign_field",
         what="Records this server would have written are re-serialised from its own model, so a "
              "field another tool attached is discarded on the next write - while records it would "
              "never have written pass through untouched. The reference implementation's real defect.",
         expect=expect(foreign_field="FAIL")),
    dict(name="drop-unnamed", breaks="foreign_record",
         what="Anything that is not a record this server would have written is discarded on the next "
              "write, and modelled fields on its own records are kept. The mirror of reshape-modelled.",
         expect=expect(foreign_record="FAIL")),
    dict(name="stale-cache", breaks="concurrent",
         what="The store is read once at startup and rewritten from that copy forever. One process "
              "is indistinguishable from correct; two processes each lose the other's writes.",
         expect=expect(concurrent="FAIL")),
    dict(name="truncate-large", breaks="large_record",
         what="Anything longer than 1000 characters is cut to 1000 and acknowledged as stored. A "
              "silent cap, which is the failure the ladder in the probe exists to see.",
         expect=expect(large_record="FAIL")),
    dict(name="lossy-locale", breaks="verbatim",
         what="Text is round-tripped through the machine's own codepage on the way to disk. cp1252 "
              "has an e-acute and does not have a CJK character, and nothing in it is an emoji. Every "
              "other probe in this suite uses ASCII names and passes it.",
         expect=expect(verbatim="FAIL")),
    dict(name="mute-search", breaks="findable",
         what="The store is perfect and nothing is ever found. Retention without retrieval.",
         expect=expect(findable="FAIL")),
    dict(name="blind-search", breaks="findable",
         what="The same three records come back whatever is asked - memento's real defect, which "
              "every other probe in the suite would have scored as a pass.",
         expect=expect(findable="FAIL")),
]


def run_one(mutant, workdir):
    leak = os.path.join(workdir, mutant["name"] + ".leak.jsonl")
    out = os.path.join(workdir, mutant["name"] + ".json")
    env = dict(os.environ)
    env["MEMORY_MUTANT"] = mutant["name"]
    env["MEMORY_LEAK_PATH"] = leak
    cmd = [sys.executable, os.path.join(HERE, "harness.py"),
           '--cmd="%s" "%s"' % (sys.executable, SERVER),
           "--adapter=mutant", "--mutant=%s" % mutant["name"], "--json=%s" % out]
    proc = subprocess.run(cmd, cwd=HERE, env=env, timeout=1800,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = (proc.stdout or b"").decode("utf-8", "replace")
    if not os.path.isfile(out):
        return None, text[-2000:] or "(no output)"
    with open(out, encoding="utf-8") as fh:
        rows = json.load(fh).get("probes") or []
    got = {}
    kinds = {}
    evidence = {}
    for row in rows:
        got[row["probe"]] = row["verdict"]
        kinds[row["probe"]] = row.get("kind") or ""
        evidence[row["probe"]] = row.get("evidence") or ""
    return dict(got=got, kinds=kinds, evidence=evidence), text


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    def opt(key, default=None):
        pref = "--" + key + "="
        for a in argv:
            if a.startswith(pref):
                return a.split("=", 1)[1]
        return default

    only = opt("only")
    md_path = opt("md", os.path.join(HERE, "MUTANTS.md"))
    json_path = opt("json", os.path.join(HERE, "results", "mutants.json"))
    if "--report" in argv:
        # A REPORT IS NOT A MEASUREMENT. MUTANTS.md was the last published table with no way to rebuild it
        # except by running twelve broken servers through ten probes each, so nothing could tell whether it
        # still described the harness it claims to test. The verdicts are saved beside it now and this
        # renders from them.
        if not os.path.isfile(json_path):
            sys.exit("no saved mutant verdicts at %s - run mutants.py once" % json_path)
        with open(json_path, encoding="utf-8") as fh:
            saved = json.load(fh)
        results = saved.get("results") or []
        bad = saved.get("bad") or 0
        _matrix(results)
        _write_md(md_path, results, bad)
        return 1 if bad else 0
    workdir = tempfile.mkdtemp(prefix="memconf_mut_")
    results = []
    bad = 0
    try:
        for mutant in MUTANTS:
            if only and mutant["name"] != only:
                continue
            print("=" * 78)
            print("%s -> aimed at %s" % (mutant["name"], mutant["breaks"]))
            print("  %s" % mutant["what"])
            measured, log = run_one(mutant, workdir)
            if measured is None:
                print("  COULD NOT RUN")
                print(log)
                bad += 1
                results.append(dict(mutant=mutant, got=None, disagreements=[], log=log))
                continue
            got = measured["got"]
            disagreements = []
            for probe in PROBES:
                want = mutant["expect"][probe]
                have = got.get(probe)
                if have != want:
                    disagreements.append((probe, want, have, measured["kinds"].get(probe, "")))
            killed = got.get(mutant["breaks"])
            if disagreements:
                bad += 1
                print("  PREDICTION WRONG in %d place(s):" % len(disagreements))
                for probe, want, have, kind in disagreements:
                    print("    %-14s predicted %-8s measured %-8s %s"
                          % (probe, want, have, ("(%s)" % kind) if kind else ""))
                    print("      %s" % measured["evidence"].get(probe, "")[:180])
            else:
                print("  every one of the %d predicted verdicts matched" % len(PROBES))
            print("  the probe it targets said %s" % killed)
            results.append(dict(mutant=mutant, got=got, kinds=measured["kinds"],
                                evidence=measured["evidence"], disagreements=disagreements))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    with open(json_path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps({"bad": bad, "results": results}, indent=1) + chr(10))
    print("saved %d verdict set(s) to %s" % (len(results), json_path))
    _matrix(results)
    _write_md(md_path, results, bad)
    return 1 if bad else 0


def _matrix(results):
    print()
    print("%-20s %-15s %s" % ("mutant", "aimed at", " ".join(
        "%-4s" % SHORT[p] for p in PROBES)))
    print("-" * 78)
    for r in results:
        got = r["got"] or {}
        cells = []
        for p in PROBES:
            v = got.get(p)
            cells.append("%-4s" % {"PASS": ".", "FAIL": "FAIL", "UNKNOWN": "unk"}.get(v, "?"))
        mark = "" if not r["disagreements"] else "   <-- prediction wrong"
        print("%-20s %-15s %s%s" % (r["mutant"]["name"], r["mutant"]["breaks"],
                                    " ".join(cells), mark))
    print("-" * 78)
    print("  .    the control's own verdict - the mutation did not reach this probe")
    print("  FAIL this probe caught the mutation")
    print("  unk  no verdict: the subject could not be asked, or the probe could not tell")


def _write_md(path, results, bad):
    lines = []
    add = lines.append
    add("# Does the suite have teeth?")
    add("")
    add("Generated by `mutants.py`. Do not edit by hand.")
    add("")
    add("The control in `control/memory_server.py` exists to prove these probes **can** pass. This")
    add("table exists to prove they **can fail**: each row is that same control with exactly one")
    add("promise broken, run through all nine probes with the expected verdicts written down before")
    add("the run.")
    add("")
    add("A probe that has never failed anything is indistinguishable from a probe that cannot.")
    add("")
    add("| mutant | aimed at | " + " | ".join(SHORT[p] for p in PROBES) + " |")
    add("|---|---|" + "---|" * len(PROBES))
    for r in results:
        got = r["got"] or {}
        cells = []
        for p in PROBES:
            v = got.get(p)
            cells.append({"PASS": "·", "FAIL": "**FAIL**", "UNKNOWN": "unk"}.get(v, "?"))
        add("| `%s` | %s | %s |" % (r["mutant"]["name"], r["mutant"]["breaks"],
                                     " | ".join(cells)))
    add("")
    add("Legend: `·` the probe passed, exactly as the control does — the mutation did not reach it.")
    add("**FAIL** the probe caught it. `unk` no verdict could be returned.")
    add("")
    add("## What each mutation is")
    add("")
    for r in results:
        add("- **`%s`** — %s" % (r["mutant"]["name"], r["mutant"]["what"]))
    add("")
    killers = dict((p, []) for p in PROBES)
    for r in results:
        got = r["got"] or {}
        for probe in PROBES:
            if got.get(probe) == "FAIL":
                killers[probe].append(r["mutant"]["name"])
    # FAILS ALONE MEANS ONE MUTANT, ONE PROBE. Not "no other probe has any killer" - every probe has
    # one, because the root mutations cascade - but "some mutation reached this probe and stopped".
    isolator = {}
    for r in results:
        got = r["got"] or {}
        for probe in PROBES:
            if got.get(probe) == "FAIL" and probe not in isolator:
                if all(got.get(o) != "FAIL" for o in PROBES if o != probe):
                    isolator[probe] = r["mutant"]["name"]
    alone = [p for p in PROBES if p in isolator]
    add("## Summary")
    add("")
    add("%d probes, %d of them failed by at least one subject built to break exactly that promise."
        % (len(PROBES), len([p for p in PROBES if killers[p]])))
    add("")
    add("| probe | failed by |")
    add("|---|---|")
    for probe in PROBES:
        hits = killers[probe]
        marks = [("%s%s" % ("`%s`" % h,
                             " **on its own**" if isolator.get(probe) == h else ""))
                 for h in hits]
        cell = ", ".join(marks) if marks else "nothing - no subject was built that breaks it"
        add("| %s | %s |" % (probe, cell))
    add("")
    if alone:
        add("%d of %d fail **alone** - one mutation reached that probe and stopped there: %s."
            % (len(alone), len(PROBES),
               ", ".join("`%s`" % p for p in alone)))
        add("")
    roots = [p for p in PROBES if p not in alone]
    if roots:
        add("The remaining %d cannot be isolated, and the reason is structural rather than a weakness"
            % len(roots))
        add("in the probes: %s. Every probe begins by writing a record and"
            % ", ".join("`%s`" % p for p in roots))
        add("reading it back, so a subject that loses writes at the root fails all of them. The")
        add("cascade in those rows is the diagnosis, not an accident of the table.")
        add("")
    unknown_only = [r["mutant"]["name"] for r in results
                    if (r["got"] or {}).get(r["mutant"]["breaks"]) == "UNKNOWN"]
    if unknown_only:
        add("%s %s the one mutation that no probe returns PASS for and none returns FAIL for either:"
            % (" and ".join("`%s`" % n for n in unknown_only),
               "is" if len(unknown_only) == 1 else "are"))
        add("a store that deleted everything answers a clean delete exactly as convincingly as a")
        add("store that deleted one record, so the probe declines to certify either way. Declining is")
        add("the correct answer, and it is why the probe counts the records nobody named.")
        add("")
    if bad:
        add("**%d mutant(s) did not produce the predicted verdicts.** The prediction is the test;"
            % bad)
        add("see the run output.")
    else:
        add("Every predicted verdict matched, on every mutant, for all %d probes." % len(PROBES))
    add("")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print()
    print("written to %s" % path)


if __name__ == "__main__":
    sys.exit(main())
