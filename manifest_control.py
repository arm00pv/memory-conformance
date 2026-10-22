#!/usr/bin/env python3
"""manifest_control.py - does the declarative path agree with the hand-written one?

memento has both a hand-written adapter and a manifest. Running the same probes through both turns
the disagreement between them into a test: if the manifest mechanism resolves the store wrongly, or
wires the predicate wrongly, the verdicts split and one of the two is wrong.

This is the check that has to pass before any subject is graded through a manifest alone, because a
manifest is a claim about where the bytes are, and a wrong claim produces confident nonsense rather
than an error.

  python manifest_control.py            # uses memento, the only subject with both paths
"""
import subprocess
import sys

CMD = "node node_modules/@iachilles/memento/index.js"
PATHS = [("hand-written", ["--adapter=memento"]),
         ("declared", ["--manifest=manifests/memento.json"])]
PROBES = ["ack_readback", "foreign_field", "foreign_record"]


def main():
    seen = {}
    for label, extra in PATHS:
        for probe in PROBES:
            args = ([sys.executable, "harness.py", "--cmd=" + CMD, "--timeout=180",
                     "--only=" + probe] + extra)
            res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace")
            line = [ln for ln in res.stdout.splitlines() if ln.startswith(probe)]
            seen[(label, probe)] = line[0] if line else "NO OUTPUT: " + res.stderr[-200:]
            print("%-13s %-15s %s" % (label, probe, seen[(label, probe)]), flush=True)
    print()
    bad = 0
    for probe in PROBES:
        hand = seen[("hand-written", probe)].split()
        decl = seen[("declared", probe)].split()
        vh = hand[1] if len(hand) > 1 else "?"
        vd = decl[1] if len(decl) > 1 else "?"
        agree = vh == vd
        bad += 0 if agree else 1
        # UNKNOWN on both sides agrees about nothing; only a real verdict pair is evidence
        note = "" if (agree and vh != "UNKNOWN") else ("  (agrees, but proves nothing)" if agree else "")
        print("%-16s hand=%-7s declared=%-7s %s%s"
              % (probe, vh, vd, "AGREE" if agree else "DISAGREE", note))
    print()
    print("%d probe(s) disagree" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
