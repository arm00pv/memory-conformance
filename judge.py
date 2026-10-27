#!/usr/bin/env python3
"""judge.py - a second opinion on the labels this repository assigns.

EVERY LABEL IN THE PRECISION READING COMES FROM A RULE ABOUT WORDS. A returned record is a near miss if
it shares a name token of four characters or more with the answer, or three words of five characters or
more that are not common to half the corpus; everything else is noise. PRECISION.md states the limit
plainly - deciding whether a returned record HELPS a caller is not a counting question, and it is the one
place a model reading the record would beat any rule - and until now that sentence was the end of the
conversation rather than the start of a measurement.

This asks a model the plain question, one pair at a time, and reports how often the rule and the reader
agree. The model is shown a question and a record and nothing else: no label, no corpus, no hint about
which of the three kinds the rule thinks it is. That is the whole design - a second opinion that knows
what the first one said is not a second opinion.

WHAT IT MEASURES

  calibration   the model is asked about the EXPECTED record too. If it says "not relevant" to the record
                the corpus says answers the question, the judge is broken or the question is, and either
                way nothing below it can be believed.
  agreement     raw agreement and Cohen's kappa between the rule (answer or near = relevant) and the
                model, over every pair it ruled on.
  disagreements the pairs where they differ, with both readings printed, so a person can adjudicate.

Every judgment is cached under its own key, so a re-run costs nothing and the report is reproducible from
the committed cache. The report is regenerated from the cache alone: @@@--report@@@ needs no model and no
network, which is what the CI runs.

    python judge.py --sample=60      # ask the model, cache, write JUDGE.md
    python judge.py --report         # re-render JUDGE.md from the cache
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
CACHE = os.path.join("results", "judgments.json")
MODEL = "glm-5.3:cloud"
PER_CLASS = 20
CORPORA = [("A", "retrieval_corpus.json", ""),
           ("B", "retrieval_corpus_b.json", "-b"),
           ("real", "retrieval_corpus_real.json", "-real"),
           ("large", "large_corpus.json", "-large")]

PROMPT = """You are reading what a memory store handed back to a question somebody asked.

QUESTION: %s

RECORD RETURNED: %s

Would this record help the person who asked? Reply with one JSON object and nothing else:
{"relevant": true} if it would help, {"relevant": false} if it would not, and a "why" field of at most
twelve words."""


def key(corpus, query, rid):
    h = hashlib.sha1(("%s\x00%s\x00%s" % (corpus, query, rid)).encode("utf-8"))
    return h.hexdigest()[:16]


def load():
    if not os.path.isfile(CACHE):
        return {}
    with open(CACHE, encoding="utf-8") as fh:
        return json.load(fh)


def save(cache):
    with open(CACHE, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(cache, indent=1, sort_keys=True) + chr(10))


def pairs():
    """Every (corpus, question, returned record) this repository has an opinion about.

    Sampled deterministically: sorted, then a stride, so the sample is the same on every machine and the
    cache always describes the same pairs.
    """
    import precision
    import resolution
    by_class = {"answer": [], "near": [], "noise": []}
    for label, path, suffix in CORPORA:
        if not os.path.isfile(path):
            continue
        c = precision.corpus(label)
        for s in resolution.subjects():
            rows = precision.rows_of(s["slug"], suffix)
            if not rows:
                continue
            for row in rows:
                q = c["want"].get(row["query"])
                if q is None or q["difficulty"] == "absent":
                    continue
                for cid in [str(x) for x in (row.get("returned") or [])]:
                    kind = precision.classify(cid, q["ids"], c)
                    by_class[kind].append({"corpus": label, "query": row["query"], "id": cid,
                                           "text": c["text"].get(cid, ""), "kind": kind,
                                           "subject": s["label"]})
    out = []
    per = max(1, PER_CLASS // 4)
    for kind, items in by_class.items():
        items.sort(key=lambda p: (p["corpus"], p["query"], p["id"]))
        step = max(1, len(items) // (per * 4))
        picked = items[::step][:per * 4]
        out.extend(picked)
    out.sort(key=lambda p: (p["kind"], p["corpus"], p["query"], p["id"]))
    return out, dict((k, len(v)) for k, v in by_class.items())


def ask_judge(model, pair):
    """One pair, one verdict, and the model's own reason kept beside it.

    THE REASONING MODEL ANSWERS IN PROSE EVEN WHEN TOLD NOT TO, so the reply is asked for as JSON and read
    with the backwards scan author.py already needed for the same model: it deliberates first, sometimes
    echoing the shape of the answer inside its reasoning, and the real answer is the last object that
    decodes. A verdict that cannot be read is UNPARSED and is asked again next run rather than counted.
    """
    import author
    text = author.ask(model, PROMPT % (pair["query"], pair["text"]), num_predict=600, temperature=0.0)
    got = author.json_of(text, dict) or {}
    value = got.get("relevant")
    if isinstance(value, str):
        value = value.strip().lower() in ("true", "yes", "1")
    verdict = "UNPARSED" if value not in (True, False) else ("YES" if value else "NO")
    why = str(got.get("why") or "").strip()[:200]
    return {"verdict": verdict, "why": why, "raw": text.strip()[:400], "model": model}


def collect(argv):
    model = MODEL
    sample = None
    for a in argv:
        if a.startswith("--model="):
            model = a.split("=", 1)[1]
        elif a.startswith("--sample="):
            sample = int(a.split("=", 1)[1])
    chosen, totals = pairs()
    if sample:
        chosen = chosen[:sample]
    cache = load()
    def settled(p):
        v = cache.get(key(p["corpus"], p["query"], p["id"])) or {}
        return v.get("verdict") in ("YES", "NO")

    todo = [p for p in chosen if not settled(p)]
    print("%d pair(s) in the sample, %d already judged, %d to ask"
          % (len(chosen), len(chosen) - len(todo), len(todo)))
    for n, p in enumerate(todo, 1):
        k = key(p["corpus"], p["query"], p["id"])
        try:
            cache[k] = ask_judge(model, p)
        except Exception as exc:
            cache[k] = {"verdict": "ERROR", "raw": str(exc)[:200], "model": model}
        cache[k]["corpus"] = p["corpus"]
        cache[k]["query"] = p["query"]
        cache[k]["id"] = p["id"]
        cache[k]["kind"] = p["kind"]
        if n % 10 == 0 or n == len(todo):
            print("  %d of %d judged" % (n, len(todo)), flush=True)
            save(cache)
    save(cache)
    print("written to %s" % CACHE)
    return 0


def kappa(rows):
    """Cohen's kappa: agreement beyond what two labellers would reach by guessing at the same rates."""
    n = len(rows)
    if not n:
        return None
    agree = sum(1 for a, b in rows if a == b)
    pa = agree / float(n)
    p_yes = sum(1 for a, _b in rows if a) / float(n)
    q_yes = sum(1 for _a, b in rows if b) / float(n)
    pe = p_yes * q_yes + (1 - p_yes) * (1 - q_yes)
    return None if pe == 1 else (pa - pe) / (1 - pe)


def report():
    cache = load()
    judged = [v for v in cache.values() if v.get("verdict") in ("YES", "NO")]
    if len(judged) < 12:
        raise SystemExit("not enough judgments to report on (%d)" % len(judged))
    models = sorted(set(v.get("model") or "?" for v in judged))
    rows = []
    for v in judged:
        rule = v["kind"] != "noise"
        rows.append((rule, v["verdict"] == "YES", v))
    tally = {}
    for v in judged:
        k = v["kind"]
        tally.setdefault(k, {"n": 0, "yes": 0})
        tally[k]["n"] += 1
        tally[k]["yes"] += 1 if v["verdict"] == "YES" else 0
    k = kappa([(a, b) for a, b, _v in rows])
    agree = sum(1 for a, b, _v in rows if a == b)
    lines = []
    add = lines.append
    add("# A second opinion on the labels")
    add("")
    add("Generated by " + BT + "judge.py" + BT + ". Do not edit by hand.")
    add("")
    add("Every label in the precision reading comes from a rule about words. This asks a model the plain")
    add("question - would this record help the person who asked - one pair at a time, with no label and no")
    add("corpus name in the prompt, and compares.")
    add("")
    add("Model: " + ", ".join(BT + m + BT for m in models) + ". " + str(len(judged)) + " judgments, cached in")
    add(BT + "results/judgments.json" + BT + "; re-running the report needs no model and no network.")
    add("")
    add("## What the judge says, by what the rule called it")
    add("")
    add("| the rule says | pairs | the judge says YES | share |")
    add("|---|---|---|---|")
    for kind in ("answer", "near", "noise"):
        t = tally.get(kind)
        if not t:
            continue
        add("| " + kind + " | %d | %d | %d%% |" % (t["n"], t["yes"], round(100 * t["yes"] / float(t["n"]))))
    add("")
    cal = tally.get("answer")
    if cal:
        add("**Calibration: the judge called %d of %d expected records relevant.**" % (cal["yes"], cal["n"]))
        if cal["yes"] < cal["n"]:
            add("The ones it refused are the first thing to read: a judge that says no to the answer is")
            add("either wrong about what the record says or right about the question, and the difference")
            add("matters for every number below.")
        add("")
    add("## Do the rule and the reader agree")
    add("")
    add("Treating the rule's reading as a labeller - answer or near means relevant, noise means not - the")
    add("two agree on **%d of %d pairs (%d%%)**, and Cohen's kappa is **%s**."
        % (agree, len(rows), round(100 * agree / float(len(rows))),
           "not computable" if k is None else "%.2f" % k))
    add("")
    add("Kappa is reported beside the raw agreement because the two classes are not equally frequent: a")
    add("labeller that called everything relevant would agree with the rule on every answer and every near")
    add("miss and be wrong about all of the noise. Kappa subtracts exactly that, and above 0.6 is usually")
    add("called substantial, 0.4 to 0.6 moderate.")
    add("")
    worst = [v for a, b, v in rows if a and not b]
    best = [v for a, b, v in rows if not a and b]
    if worst and not best:
        add("**Every disagreement in this sample runs one way, and that is the result.** The rule calls")
        add("%d records near misses that the reader calls unrelated, and calls nothing noise that the" % len(worst))
        add("reader would use. So the three-way split is wrong in the direction the report already claims")
        add("for it: the noise count is a **floor**, because a record this reading excuses as a near miss")
        add("may be junk a caller pays for. That sentence was a caveat in PRECISION.md; it is a measurement")
        add("now, and it says the published noise figures are optimistic by at least %d of %d near-miss"
            % (len(worst), len([v for a, b, v in rows if a]) or 1))
        add("credits in this sample.")
        add("")
    add("## Where they disagree")
    add("")
    add("**The rule called it a near miss and the judge called it unrelated: %d pair(s).** These are the ones" % len(worst))
    add("that inflate the near-miss count and so flatter every subject's precision.")
    add("")
    for v in worst[:5]:
        add("- " + BT + v["corpus"] + BT + " " + BT + v["query"][:70] + BT + " -> " + BT + v["id"] + BT)
        add("  the judge: " + (v.get("why") or "(no reason given)"))
    add("")
    add("**The rule called it unrelated and the judge called it relevant: %d pair(s).** These are the ones" % len(best))
    add("that deflate it - a record a reader would use, charged to the subject as noise.")
    add("")
    for v in best[:5]:
        add("- " + BT + v["corpus"] + BT + " " + BT + v["query"][:70] + BT + " -> " + BT + v["id"] + BT)
        add("  the judge: " + (v.get("why") or "(no reason given)"))
    add("")
    add("## What this does not settle")
    add("")
    add("One model at one temperature is not a standard. It is a reader, and readers disagree with each")
    add("other; the number here is how far a particular reader is from a particular rule, not how far the")
    add("rule is from the truth. A second model would make that visible, and a third would make it")
    add("quantifiable, and neither is done.")
    add("")
    add("The prompt is a judgement call of its own. It asks whether the record would help, which is the")
    add("question the report claims not to be able to answer; it does not ask whether it is the answer,")
    add("because that is what the corpus already says and asking it would test nothing.")
    add("")
    path = os.path.join(HERE, "JUDGE.md")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print("written to %s" % path)
    print("agreement %d of %d (%.2f kappa)" % (agree, len(rows), -1 if k is None else k))
    return 0


def main(argv):
    if "--report" in argv:
        return report()
    code = collect(argv)
    if "--no-report" not in argv:
        report()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
