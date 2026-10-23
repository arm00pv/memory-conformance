#!/usr/bin/env python3
"""validate_corpus.py - is the question set itself honest?

A RETRIEVAL SCORE IS WORTH THE CORPUS AND NOT A PENNY MORE. Every band in the corpus rests on an
assumption that is invisible in the score: that "absent" really has no answer in the store, that
"adversarial" really has a near duplicate to be confused with, that "easy" really shares wording with
the record it names, and that no record answers two questions at once. If one of those is wrong, a
subject is not being measured and the table still prints a number.

So the assumptions are checked instead of asserted. This reads a corpus and reports what is true of it,
and it is run against BOTH corpora, including the one the published table was computed from. A
validator that only ever sees the new data has not been tested; a corpus that fails it is not
disqualified, it is documented.

  python validate_corpus.py                        # every corpus_*.json beside this file
  python validate_corpus.py retrieval_corpus_b.json
  python validate_corpus.py --json=out.json        # machine-readable, for CI

Exit 0 when every corpus passes, 1 when any fails a structural requirement. Warnings do not fail: they
are facts about the corpus worth printing, not defects in it.
"""
import glob
import json
import os
import sys

from words import STOP, tokens

HERE = os.path.dirname(os.path.abspath(__file__))
BAND_COUNT = {"easy": 0, "hard": 0, "adversarial": 0, "absent": 0}
BANDS = ("easy", "hard", "adversarial", "absent")

# THE STOPWORD LIST AND THE TOKENIZER LIVE IN words.py, because a second tool needs them to mean the
# same thing. STOP is still imported here by name so that anything reading this file sees where the
# reduction comes from rather than a call to a function with no visible contents.


def jaccard(a, b):
    a, b = set(tokens(a)), set(tokens(b))
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def check(path):
    """Everything that can be checked about one corpus, as three lists."""
    errors, warnings, facts = [], [], {}
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    records = doc.get("records") or []
    queries = doc.get("queries") or []
    facts["records"] = len(records)
    facts["queries"] = len(queries)
    facts["why"] = bool((doc.get("why") or "").strip())

    # --- structure ---------------------------------------------------------
    ids = [r.get("id") for r in records]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        errors.append("duplicate record id(s): %s" % ", ".join(map(str, dupes)))
    texts = {}
    for r in records:
        if not (r.get("text") or "").strip():
            errors.append("record %r has no text" % r.get("id"))
        texts[r.get("id")] = r.get("text") or ""
    band = {}
    for q in queries:
        band[q.get("difficulty")] = band.get(q.get("difficulty"), 0) + 1
    facts["bands"] = {b: band.get(b, 0) for b in BANDS}
    for b, n in facts["bands"].items():
        if not n:
            errors.append("band %r is empty - the corpus does not exercise it" % b)
    for q in queries:
        if q.get("difficulty") not in BANDS:
            errors.append("query %r has difficulty %r" % (q.get("query"), q.get("difficulty")))

    qs = [q.get("query") for q in queries]
    if len(set(qs)) != len(qs):
        errors.append("%d duplicated question string(s)" % (len(qs) - len(set(qs))))

    # --- the answer has to exist, and has to be the only answer ------------
    answered = [q for q in queries if q.get("difficulty") != "absent"]
    for q in answered:
        want = q.get("expect")
        if want is None:
            errors.append("question %r is labelled %r but expects nothing" %
                          (q.get("query"), q.get("difficulty")))
        elif want not in texts:
            errors.append("question %r expects %r, which is not a record" % (q.get("query"), want))
    wants = [q.get("expect") for q in answered if q.get("expect") in texts]
    facts["distinct_answers"] = len(set(wants))
    if len(set(wants)) != len(wants):
        shared = sorted({w for w in wants if wants.count(w) > 1})
        errors.append("%d record(s) answer more than one question: %s"
                      % (len(shared), ", ".join(shared)))

    # --- absent means absent ----------------------------------------------
    # A SHARED WORD IS NOT A SHARED ANSWER, and the first version of this check confused the two. A
    # question about the office wifi password and a record about a password policy both contain
    # "password", and the wifi password is still nowhere in the store. Charging that question as
    # answerable would have made four honest questions look dishonest.
    #
    # What makes an absent question dishonest is a single record that COVERS most of its words,
    # because that record is the answer nobody labelled. So the test is coverage of the whole question
    # by one record, a shared word on its own is printed and not charged, and the threshold is stated
    # rather than implied.
    ABSENT_COVER = 0.5
    leaked = {}
    thin = {}
    for q in queries:
        if q.get("difficulty") != "absent":
            continue
        qt = set(tokens(q.get("query")))
        if not qt:
            errors.append("absent question %r has no distinctive words at all" % q.get("query"))
            continue
        best = (None, 0.0, [])
        for rid, text in texts.items():
            shared = qt & set(tokens(text))
            if len(shared) / float(len(qt)) > best[1]:
                best = (rid, len(shared) / float(len(qt)), sorted(shared))
        if best[1] >= ABSENT_COVER:
            leaked[q.get("query")] = best
        elif best[2]:
            thin[q.get("query")] = best
    facts["absent_clean"] = len(leaked) == 0
    for q, (rid, frac, shared) in leaked.items():
        errors.append("absent question %r is %.0f%% covered by %r (%s), which is an unlabelled answer"
                      % (q, frac * 100, rid, ", ".join(shared)))
    for q, (rid, frac, shared) in thin.items():
        warnings.append("absent question %r shares %s with %r - still unanswerable, and worth knowing"
                        " what a keywording subject will match on" % (q, ", ".join(shared), rid))

    # --- adversarial means a trap -----------------------------------------
    # THE TRAP IS BETWEEN TWO RECORDS, NOT BETWEEN A QUESTION AND A RECORD. An earlier version asked
    # for a rival sharing two of the QUESTION's words and failed eleven of sixteen honest items: the
    # question "how long does the refresh token last" competes with a record about access token
    # lifetimes, which shares the word "token" and nothing else, and that single shared word is
    # exactly what makes the item adversarial.
    #
    # So the test is: the question picks out some words from its answer (its core), and does any
    # OTHER record also carry one of them? If nothing else competes the item is a hard question
    # wearing the wrong label. How strongly it competes is reported, because a one-word trap is a
    # weaker test than a three-word one.
    traps = {}
    for q in queries:
        if q.get("difficulty") != "adversarial":
            continue
        want = q.get("expect")
        if want not in texts:
            continue
        core = set(tokens(q.get("query"))) & set(tokens(texts[want]))
        rivals = []
        for rid, text in texts.items():
            if rid == want:
                continue
            shared = sorted(core & set(tokens(text)))
            if shared:
                rivals.append((rid, shared))
        strength = max([len(s) for _r, s in rivals] or [0])
        traps[q.get("query")] = strength
        if not rivals:
            errors.append("adversarial question %r competes with nothing: no other record carries any "
                          "of the words it shares with %r (%s), so this is a hard question labelled "
                          "adversarial" % (q.get("query"), want, ", ".join(sorted(core)) or "-"))
        elif strength < 2:
            warnings.append("adversarial question %r has only a one-word trap (%s), the weakest kind"
                            % (q.get("query"), ", ".join(sorted(rivals[0][1]))))
    facts["adversarial_traps"] = sorted(set(traps.values()))

    # --- easy means easy ---------------------------------------------------
    thin = []
    for q in queries:
        if q.get("difficulty") != "easy":
            continue
        want = q.get("expect")
        if want not in texts:
            continue
        qt = set(tokens(q.get("query")))
        shared = len(qt & set(tokens(texts[want])))
        if shared * 2 < len(qt):
            thin.append((q.get("query"), shared, len(qt)))
    facts["easy_share_wording"] = len(thin) == 0
    for q, shared, n in thin:
        errors.append("easy question %r shares only %d of %d words with the record it names"
                      % (q, shared, n))

    # --- hard means paraphrased -------------------------------------------
    # THE ONE BAND NOTHING CHECKED. Its definition is "a paraphrase that shares almost nothing with the
    # wording of the answer", and that is measurable: count the distinguishing words the question has in
    # common with the record it names. One shared word is the most "almost nothing" can mean; more than
    # one and the question is a keyword match wearing the label, which makes the band easier than the
    # thing it claims to test. The threshold was set AFTER measuring both corpora - corpus A reaches
    # three shared words, corpus B never exceeds one - and it is stated here rather than discovered in
    # the results.
    HARD_SHARE = 1
    too_close = []
    for q in queries:
        if q.get("difficulty") != "hard":
            continue
        want = q.get("expect")
        if want not in texts:
            continue
        shared = sorted(set(tokens(q.get("query"))) & set(tokens(texts[want])))
        if len(shared) > HARD_SHARE:
            too_close.append((q.get("query"), want, shared))
    facts["hard_paraphrased"] = len(too_close) == 0
    for q, want, shared in too_close:
        errors.append("hard question %r shares %d words with %r (%s) - a keyword match, not a paraphrase"
                      % (q, len(shared), want, ", ".join(shared)))

    # --- warnings: not defects, but things a reader should know ------------
    unused = [rid for rid in texts if rid not in set(wants)]
    facts["distractor_records"] = len(unused)
    longrec = [rid for rid, t in texts.items() if len(t) > 160]
    if longrec:
        warnings.append("%d record(s) longer than 160 characters: %s"
                        % (len(longrec), ", ".join(longrec[:5])))
    # NEAR-IDENTICAL QUESTIONS ARE THE POINT WHEN THEY TEST DIFFERENT FACTS. "How much is a peak return to
    # Coble Wharf?" and "What does an off-peak return to Coble Wharf come to?" are two words apart and
    # deliberately so: they are the pair a keyword matcher cannot tell apart. Warning on them charged the
    # corpus for doing its job. What is actually redundant is two questions that land on the SAME record,
    # because then one fact is being counted twice and a subject's score depends on it twice.
    near = []
    for i, a in enumerate(queries):
        for b in queries[i + 1:]:
            if a.get("expect") and a.get("expect") == b.get("expect"):
                if jaccard(a.get("query"), b.get("query")) >= 0.8:
                    near.append((a.get("query"), b.get("query")))
    if near:
        warnings.append("%d question pair(s) are near paraphrases of each other AND name the same"
                        " record, so one fact is being counted twice: %s"
                        % (len(near), "; ".join("%r/%r" % x for x in near[:3])))
    return errors, warnings, facts


def diff_baseline(report, baseline):
    """Compare what this run found with the defects somebody already looked at and accepted.

    THE SAME IDIOM AS --expect ON THE PROBES. A corpus cannot be made defect-free by argument, and a
    check that always fails is a check nobody reads. So the known defects are written down, a NEW one
    fails the build, and a pinned one that stops happening is itself reported - because that means the
    corpus changed, which is exactly the thing a pinned baseline exists to notice.
    """
    new, fixed = [], []
    for name, res in report.items():
        pinned = (baseline.get(name) or {}).get("errors") or []
        for e in res["errors"]:
            if e not in pinned:
                new.append((name, e))
        for e in pinned:
            if e not in res["errors"]:
                fixed.append((name, e))
    return new, fixed


def main(argv):
    out_path = None
    baseline_path = None
    write_baseline = None
    argv = list(argv)
    for a in argv:
        if a.startswith("--json="):
            out_path = a.split("=", 1)[1]
        elif a.startswith("--baseline="):
            baseline_path = a.split("=", 1)[1]
        elif a.startswith("--write-baseline="):
            write_baseline = a.split("=", 1)[1]
    argv = [a for a in argv if not a.startswith(("--json=", "--baseline=", "--write-baseline="))]
    paths = argv or sorted(glob.glob(os.path.join(HERE, "corpus_*.json")) +
                           glob.glob(os.path.join(HERE, "retrieval_corpus*.json")))
    if not paths:
        print("no corpus found")
        return 2
    report = {}
    failed = 0
    for path in paths:
        name = os.path.basename(path)
        try:
            errors, warnings, facts = check(path)
        except Exception as exc:
            errors, warnings, facts = ["could not read: %s" % exc], [], {}
        report[name] = {"errors": errors, "warnings": warnings, "facts": facts}
        bands = facts.get("bands") or {}
        print("%s: %d records, %d questions (%s)" % (
            name, facts.get("records", 0), facts.get("queries", 0),
            ", ".join("%s %d" % (b, bands.get(b, 0)) for b in BANDS)))
        print("  %d distinct answers, %d distractor records, adversarial rival shares %s word(s)"
              % (facts.get("distinct_answers", 0), facts.get("distractor_records", 0),
                 "/".join(map(str, facts.get("adversarial_traps") or [])) or "-"))
        for e in errors:
            print("  FAIL  " + e)
        for w in warnings:
            print("  warn  " + w)
        if not errors:
            print("  ok    every structural assumption above holds")
        failed += 1 if errors else 0
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(json.dumps(report, indent=2) + chr(10))
    if write_baseline:
        pinned = {name: {"note": "defects looked at and accepted, so that a new one fails the build",
                         "errors": res["errors"]}
                  for name, res in report.items() if res["errors"]}
        with open(write_baseline, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(json.dumps(pinned, indent=2) + chr(10))
        print("baseline written to %s" % write_baseline)
    print()
    print("%d of %d corpus file(s) failed" % (failed, len(paths)))
    if baseline_path and os.path.isfile(baseline_path):
        with open(baseline_path, encoding="utf-8") as fh:
            baseline = json.load(fh)
        new, fixed = diff_baseline(report, baseline)
        for name, e in new:
            print("  UNPINNED  %s: %s" % (name, e))
        for name, e in fixed:
            print("  DRIFT     %s: pinned defect did not reproduce, so the corpus changed: %s"
                  % (name, e))
        for name in report:
            note = (baseline.get(name) or {}).get("errors") or []
            if note:
                print("  %s carries %d pinned defect(s) - see %s" % (name, len(note), baseline_path))
        if new:
            return 1
        if fixed:
            return 2
        return 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
