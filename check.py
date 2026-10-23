#!/usr/bin/env python3
"""check.py - run everything against one server and print one verdict.

  python check.py "node my-server.js"
  python check.py "node my-server.js" --manifest=manifests/memdb.json
  python check.py "node my-server.js" --repeat=3 --badge

This is the command to run on your own package. It answers three questions with the numbers behind
each of them: does it keep what it acknowledges, can it find what it kept, and what does it cost -
measured in both phrasings, because the same subject scores differently depending on how a question is
put.

It never guesses a binding without proving it, and it never turns "I could not measure this" into a
pass or a failure. A probe that cannot be expressed against a subject is reported as UNKNOWN, and
this tool then tells you how to make it answerable - usually with a manifest of about fourteen
lines.

Exit codes:
  0  every probe that could be run was kept
  1  at least one probe failed
  2  the subject could not be graded at all (it leaked state, or nothing could be measured)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = ["isolation", "ack_readback", "restart", "forget", "findable", "foreign_field",
          "foreign_record", "concurrent", "large_record"]
PAD = max(len(p) for p in PROBES) + 1


def run(script, cmd, extra, ceiling, repeat, out):
    args = [sys.executable, script, "--cmd=" + cmd, "--timeout=%d" % ceiling,
            "--json=" + out] + extra
    if repeat > 1:
        args.append("--repeat=%d" % repeat)
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=HERE)
    if not os.path.isfile(out):
        return None, proc
    with open(out, encoding="utf-8") as fh:
        return json.load(fh), proc


def corpus_counts():
    """The corpus size, read from the corpus. Three files used to state it in prose and all three
    were falsified the moment the corpus grew."""
    path = os.path.join(HERE, "retrieval_corpus.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception:
        return (0, 0)
    return (len(doc.get("records") or []), len(doc.get("queries") or []))


def badge_svg(kept, unknown, failed):
    """A self-contained badge. No service is called, so it works offline and cannot rot."""
    label = "memory-conformance"
    value = "%d kept" % kept
    if failed:
        value += ", %d failed" % failed
    if unknown:
        value += ", %d unknown" % unknown
    colour = "#d1242f" if failed else ("#bf8700" if unknown else "#1a7f37")
    lw, vw = 7 * len(label) + 20, 7 * len(value) + 20
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="20" role="img" '
            'aria-label="%s: %s">' % (lw + vw, label, value) +
            '<rect width="%d" height="20" fill="#555"/>' % lw +
            '<rect x="%d" width="%d" height="20" fill="%s"/>' % (lw, vw, colour) +
            '<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">' +
            '<text x="10" y="14">%s</text>' % label +
            '<text x="%d" y="14">%s</text></g></svg>' % (lw + 10, value))


def register(name, version, cmd, manifest, leaking):
    """Add the subject to subjects.json so the next matrix run includes it.

    A subject that leaks state is still registered, and marked, because "this one is out of scope and
    here is why" is a result. Dropping it would quietly shrink the denominator.
    """
    path = os.path.join(HERE, "subjects.json")
    with open(path, encoding="utf-8") as fh:
        subjects = json.load(fh)
    entry = {"name": name, "version": version, "cmd": cmd}
    if manifest:
        entry["manifest"] = manifest
    else:
        entry["adapter"] = "auto"
    existing = [i for i, s in enumerate(subjects)
                if s.get("name") == name and str(s.get("version")) == str(version)]
    if existing:
        subjects[existing[0]] = entry
        action = "updated"
    else:
        subjects.append(entry)
        action = "added"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(subjects, indent=2) + "\n")
    print()
    print("subjects.json %s: %s %s%s" % (action, name, version,
                                         " (out of scope: leaks state)" if leaking else ""))
    print("now run  python matrix.py --report-only  to fold it into MATRIX.md")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = None
    adapter, manifest, repeat, ceiling, want_badge = "auto", None, 1, 60, False
    submit, name, version = False, None, None
    for a in argv:
        if a.startswith("--cmd="):
            cmd = a.split("=", 1)[1]
        elif a.startswith("--adapter="):
            adapter = a.split("=", 1)[1]
        elif a.startswith("--manifest="):
            manifest = a.split("=", 1)[1]
        elif a.startswith("--repeat="):
            repeat = max(1, int(a.split("=", 1)[1]))
        elif a.startswith("--timeout="):
            ceiling = float(a.split("=", 1)[1])
        elif a == "--badge":
            want_badge = True
        elif a == "--submit":
            submit = True
        elif a.startswith("--name="):
            name = a.split("=", 1)[1]
        elif a.startswith("--version="):
            version = a.split("=", 1)[1]
        elif not a.startswith("-"):
            cmd = a
    if not cmd:
        print(__doc__)
        return 2

    extra = (["--manifest=" + manifest] if manifest else ["--adapter=" + adapter])
    if submit:
        # A SUBMITTED NUMBER SHOULD BE A REPEATED ONE. Three attempts is what the published matrix
        # uses; anything less is a claim about a single draw.
        repeat = max(repeat, 3)

    if submit:
        slug = ("%s-%s" % (name or os.path.basename(cmd.split()[-1]), version or "0")).replace("/", "_")
        os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
        p_json = os.path.join(HERE, "results", slug + ".json")
        r_json = os.path.join(HERE, "results", slug + "-retrieval.json")
        c_json = os.path.join(HERE, "results", slug + "-cost.json")
    else:
        tmp = tempfile.mkdtemp(prefix="check_")
        p_json = os.path.join(tmp, "probes.json")
        r_json = os.path.join(tmp, "retrieval.json")
        c_json = os.path.join(tmp, "cost.json")

    print("subject : %s" % cmd)
    print("binding : %s" % ("declared in " + manifest if manifest else "discovered, proven by round-trip"))
    print("attempt : %d, ceiling %gs" % (repeat, ceiling))
    print()

    report, proc = run("harness.py", cmd, extra, int(ceiling), repeat, p_json)
    if report is None:
        print(proc.stdout.strip() or proc.stderr.strip()[-400:])
        print()
        print("Could not grade this subject. If it published no usable write tool, it is not a")
        print("memory server; if the binding could not be proven, its tools did not round-trip.")
        return 2

    rows = {r["probe"]: r for r in report["probes"]}
    kept = sum(1 for p in PROBES if rows.get(p, {}).get("verdict") == "PASS")
    failed = sum(1 for p in PROBES if rows.get(p, {}).get("verdict") == "FAIL")
    unknown = sum(1 for p in PROBES if rows.get(p, {}).get("verdict") == "UNKNOWN")

    print("conformance")
    for p in PROBES:
        r = rows.get(p)
        if not r:
            continue
        label = r["verdict"]
        if r.get("kind") not in ("kept", "failed"):
            label += "(%s)" % r["kind"]
        print("  %-*s %-22s %s" % (PAD, p, label, r["evidence"][:96]))
    print("  %d kept, %d unknown, %d failed" % (kept, unknown, failed))

    summary = None
    # BOTH PHRASINGS, ALWAYS: the same subject is 6/60 and 29/60 on one corpus depending only on how
    # the question is put, so a retrieval section with one number in it is a report about the wording.
    got, _p = run("retrieval.py", cmd, extra + ["--shapes"], int(ceiling), repeat, r_json)
    if got:
        summary = got.get("summary")
    if summary:
        a = summary.get("all") or {}
        ab = summary.get("absent") or {}
        print()
        print("retrieval (%d records, %d questions, cold start)" % corpus_counts())
        print("  hit@3  easy %s  hard %s  adversarial %s  ->  all %d/%d"
              % tuple(["%d/%d" % (summary[b]["hit3"], summary[b]["n"]) if b in summary else "-/-"
                       for b in ("easy", "hard", "adversarial")] + [a.get("hit3", 0), a.get("n", 0)]))
        if "hit3_keyword" in a:
            print("  hit@3, the same %d questions put as keywords          ->  all %d/%d  (%+d)"
                  % (a.get("n", 0), a["hit3_keyword"], a.get("n", 0),
                     a["hit3_keyword"] - a.get("hit3", 0)))
            if ab.get("answered_keyword") is not None:
                print("  questions with no answer answered anyway: %d/%d as written, %d/%d as keywords"
                      % (ab.get("answered", 0), ab.get("n", 0), ab["answered_keyword"], ab.get("n", 0)))
        else:
            print("  questions with no answer that were answered anyway: %d/%d"
                  % (ab.get("answered", 0), ab.get("n", 0)))

    cost, _p = run("cost.py", cmd, extra, int(ceiling), repeat, c_json)
    if cost:
        print()
        print("cost")
        print("  startup %.2fs   first write %.2fs   write %.3fs   search %.3fs"
              % (cost["startup_p50"], cost["first_write"], cost["write_p50"], cost["search_p50"]))
        print("  %d bytes per question (%sx the size of the answer)   %s bytes per record"
              % (cost["resp_bytes_p50"], ("%.0f" % cost["amp"]) if cost.get("amp") else "-",
                 cost["store_bytes_per_record"] if cost["store_bytes_per_record"] is not None else "-"))

    # THE BLOCKER COMES FIRST. Telling a subject that leaks state to write a manifest is telling it
    # to describe a store it cannot be pointed at; the thing to fix is the leak, and until it is
    # fixed nothing else in this report is about the subject.
    leaking = rows.get("isolation", {}).get("verdict") == "FAIL"
    advice = []
    if leaking:
        advice.append("The subject keeps state across separate stores. Until it can be pointed at a"
                      " fresh store, no other verdict here describes it - fix that first.")
    elif not manifest:
        unm = [p for p in ("foreign_field", "foreign_record")
               if rows.get(p, {}).get("kind") == "not-applicable"]
        if unm:
            advice.append("%s %s UNKNOWN because no store is declared. A manifest of about"
                          " fourteen lines makes %s answerable - see manifests/memdb.json."
                          % (" and ".join(unm), "are" if len(unm) > 1 else "is",
                             "them" if len(unm) > 1 else "it"))
    na = [p for p in PROBES if rows.get(p, {}).get("kind") == "harness-error"]
    if na:
        advice.append("The harness could not drive %s. That is probably a gap in this suite, not a"
                      " defect in the subject; please report it." % ", ".join(na))
    if repeat == 1:
        advice.append("Each probe ran once. Add --repeat=3 to find out whether the verdicts are stable.")
    if advice:
        print()
        print("what to do next")
        for line in advice:
            print("  - " + line)

    if want_badge:
        svg = badge_svg(kept, unknown, failed)
        path = "conformance-badge.svg"
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(svg)
        print()
        print("badge written to %s - copy it into your README and link it to the full report:" % path)
        print("  ![memory-conformance](%s)" % path)

    if submit:
        register(name or os.path.basename(cmd.split()[-1]), version or "0", cmd, manifest,
                 rows.get("isolation", {}).get("verdict") == "FAIL")

    if rows.get("isolation", {}).get("verdict") == "FAIL":
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
