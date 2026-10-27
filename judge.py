#!/usr/bin/env python3
"""judge.py - a second opinion on the labels this repository assigns, and a third.

EVERY LABEL IN THE PRECISION READING COMES FROM A RULE ABOUT WORDS. A returned record is a near miss if it
shares a name token of four characters or more with the answer, or three words of five characters or more
that are not common to half the corpus; everything else is noise. PRECISION.md states the limit plainly -
deciding whether a returned record HELPS a caller is not a counting question, and it is the one place a
model reading the record would beat any rule.

This asks that question of two models, one pair at a time, with no label and no corpus in the prompt, and
reports three numbers rather than one:

  agreement   how far each reader is from the rule
  ceiling     how far the two readers are from EACH OTHER on the same pairs. One reader's kappa measures one
              opinion; two readers bound how much of a disagreement is the rule and how much is the reading
  disposition every pair, by what the rule said and what the readers said together

Every judgment is cached under its own key, so a re-run costs nothing and the report is reproducible from
the committed cache. @@@--report@@@ needs no model and no network, which is what the CI runs.

    python judge.py --sample=60        # ask every model, cache, write JUDGE.md
    python judge.py --report           # re-render JUDGE.md from the cache
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
CACHE = os.path.join("results", "judgments.json")
MODELS = ["glm-5.3:cloud", "deepseek-v4.1-flash:cloud"]
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


def key(model, corpus, query, rid):
    h = hashlib.sha1(("%s\x00%s\x00%s\x00%s" % (model, corpus, query, rid)).encode("utf-8"))
    return h.hexdigest()[:16]


def save(cache):
    with open(CACHE, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(cache, indent=1, sort_keys=True) + chr(10))


def load():
    """The cache, re-keyed when a key stops being unique.

    THE FIRST VERSION KEYED A JUDGMENT BY THE PAIR ALONE, which was fine while there was one reader and
    silently wrong the moment a second was added: two models judging the same pair would have collided, and
    the second opinion would have been the first one twice. Keys carry the model now, and old entries are
    re-keyed by the model they recorded.
    """
    if not os.path.isfile(CACHE):
        return {}
    with open(CACHE, encoding="utf-8") as fh:
        raw = json.load(fh)
    out, migrated = {}, 0
    for k, v in raw.items():
        want = key(v.get("model") or MODELS[0], v.get("corpus", ""), v.get("query", ""), v.get("id", ""))
        if k != want:
            migrated += 1
        out[want] = v
    if migrated:
        print("%d cached judgment(s) re-keyed by model" % migrated)
        save(out)
    return out


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
        out.extend(items[::step][:per * 4])
    out.sort(key=lambda p: (p["kind"], p["corpus"], p["query"], p["id"]))
    return out


def ask_judge(model, pair):
    """One pair, one verdict, and the model's own reason kept beside it.

    THE REASONING MODELS ANSWER IN PROSE EVEN WHEN TOLD NOT TO, so the reply is asked for as JSON and read
    with the backwards scan author.py already needed for the same models: they deliberate first, sometimes
    echoing the shape of the answer inside the reasoning, and the real answer is the last object that
    decodes. A verdict that cannot be read is UNPARSED and is asked again next run rather than counted.
    """
    import author
    text = author.ask(model, PROMPT % (pair["query"], pair["text"]), num_predict=600, temperature=0.0)
    got = author.json_of(text, dict) or {}
    value = got.get("relevant")
    if isinstance(value, str):
        value = value.strip().lower() in ("true", "yes", "1")
    verdict = "UNPARSED" if value not in (True, False) else ("YES" if value else "NO")
    return {"verdict": verdict, "why": str(got.get("why") or "").strip()[:200],
            "raw": text.strip()[:400], "model": model}


def collect(argv):
    models = list(MODELS)
    sample = None
    for a in argv:
        if a.startswith("--model="):
            models = [a.split("=", 1)[1]]
        elif a.startswith("--models="):
            models = [m.strip() for m in a.split("=", 1)[1].split(",") if m.strip()]
        elif a.startswith("--sample="):
            sample = int(a.split("=", 1)[1])
    chosen = pairs()
    if sample:
        chosen = chosen[:sample]
    cache = load()

    def settled(model, p):
        v = cache.get(key(model, p["corpus"], p["query"], p["id"])) or {}
        return v.get("verdict") in ("YES", "NO")

    print("%d pair(s) in the sample, %d model(s)" % (len(chosen), len(models)))
    for model in models:
        todo = [p for p in chosen if not settled(model, p)]
        print("  %s: %d already judged, %d to ask" % (model, len(chosen) - len(todo), len(todo)), flush=True)
        for n, p in enumerate(todo, 1):
            k = key(model, p["corpus"], p["query"], p["id"])
            try:
                cache[k] = ask_judge(model, p)
            except Exception as exc:
                cache[k] = {"verdict": "ERROR", "raw": str(exc)[:200], "model": model}
            cache[k]["corpus"] = p["corpus"]
            cache[k]["query"] = p["query"]
            cache[k]["id"] = p["id"]
            cache[k]["kind"] = p["kind"]
            if n % 10 == 0 or n == len(todo):
                print("    %d of %d" % (n, len(todo)), flush=True)
                save(cache)
    save(cache)
    print("written to %s" % CACHE)
    return 0


def kappa(rows):
    """Cohen's kappa: agreement beyond what two labellers would reach by guessing at the same rates."""
    n = len(rows)
    if not n:
        return None
    pa = sum(1 for a, b in rows if a == b) / float(n)
    p_yes = sum(1 for a, _b in rows if a) / float(n)
    q_yes = sum(1 for _a, b in rows if b) / float(n)
    pe = p_yes * q_yes + (1 - p_yes) * (1 - q_yes)
    return None if pe == 1 else (pa - pe) / (1 - pe)


def by_model(cache):
    """{model: {(corpus, query, id): entry}} for the settled judgments."""
    out = {}
    for _k, v in cache.items():
        if v.get("verdict") not in ("YES", "NO"):
            continue
        out.setdefault(v.get("model") or "?", {})[(v["corpus"], v["query"], v["id"])] = v
    return out


def report():
    cache = load()
    per = by_model(cache)
    models = [m for m in MODELS if m in per] + [m for m in per if m not in MODELS]
    if not models or sum(len(per[m]) for m in models) < 12:
        raise SystemExit("not enough judgments to report on")
    lines = []
    add = lines.append
    add("# A second opinion on the labels")
    add("")
    add("Generated by " + BT + "judge.py" + BT + ". Do not edit by hand.")
    add("")
    add("Every label in the precision reading comes from a rule about words. This asks models the plain")
    add("question - would this record help the person who asked - one pair at a time, with no label and no")
    add("corpus name in the prompt, and reports how far each reader is from the rule, and how far the")
    add("readers are from each other.")
    add("")
    add("Readers: " + ", ".join(BT + m + BT for m in models) + ". Judgment counts: "
        + ", ".join("%d" % len(per[m]) for m in models) + ". Cached in " + BT + "results/judgments.json" + BT)
    add("with the model in the key; re-running the report needs no model and no network.")
    add("")

    add("## What each reader says, by what the rule called it")
    add("")
    add("| reader | the rule says | pairs | relevant | share |")
    add("|---|---|---|---|---|")
    tally = {}
    for m in models:
        tally[m] = {}
        for v in per[m].values():
            t = tally[m].setdefault(v["kind"], [0, 0])
            t[0] += 1
            t[1] += 1 if v["verdict"] == "YES" else 0
        for kind in ("answer", "near", "noise"):
            if kind not in tally[m]:
                continue
            n, yes = tally[m][kind]
            add("| " + BT + m + BT + " | " + kind + " | %d | %d | %d%% |"
                % (n, yes, round(100 * yes / float(n))))
    add("")
    cal = ["%s called %d of %d" % (m.split(":")[0], tally[m]["answer"][1], tally[m]["answer"][0])
           for m in models if "answer" in tally[m]]
    add("**Calibration, on the records the corpus says answer the question:** " + "; ".join(cal) + ".")
    add("A reader that refuses the answer is either wrong about the record or right about the question, and")
    add("either way nothing it says about the other pairs can be believed without that sentence beside it.")
    add("")

    add("## The rule against each reader")
    add("")
    add("Treating the rule as a labeller - answer or near means relevant, noise means not - the agreement")
    add("with each reader, and Cohen's kappa, which subtracts what two labellers would reach by guessing at")
    add("the same rates:")
    add("")
    add("| reader | pairs | agree | kappa | rule says near, reader says no | reader says yes, rule says noise |")
    add("|---|---|---|---|---|---|")
    summary = {}
    for m in models:
        rows = [((v["kind"] != "noise"), v["verdict"] == "YES") for v in per[m].values()]
        k = kappa(rows)
        agree = sum(1 for a, b in rows if a == b)
        generous = sum(1 for a, b in rows if a and not b)
        stingy = sum(1 for a, b in rows if not a and b)
        summary[m] = {"n": len(rows), "agree": agree, "kappa": k}
        add("| " + BT + m + BT + " | %d | %d | %s | %d | %d |"
            % (len(rows), agree, "n/a" if k is None else "%.2f" % k, generous, stingy))
    add("")

    both = []
    if len(models) > 1:
        both = sorted(p for p in set(per[models[0]]) if all(p in per[m] for m in models))
    if both:
        rows = [(per[models[0]][p]["verdict"] == "YES", per[models[1]][p]["verdict"] == "YES") for p in both]
        k = kappa(rows)
        agree = sum(1 for a, b in rows if a == b)
        add("## How far the readers are from each other")
        add("")
        add("On the **%d pairs both readers judged** they agree on %d (%d%%), kappa **%s**. That is the"
            % (len(rows), agree, round(100 * agree / float(len(rows))),
               "n/a" if k is None else "%.2f" % k))
        add("ceiling on how close any rule can come to what a reader thinks: the two readers disagree with")
        add("each other on %d of these pairs, so a rule cannot be closer to both than they are to themselves."
            % (len(rows) - agree))
        add("")
        both_yes = [p for p in both if all(per[m][p]["verdict"] == "YES" for m in models)]
        both_no = [p for p in both if all(per[m][p]["verdict"] == "NO" for m in models)]
        add("## What both readers agree about, against what the rule says")
        add("")
        add("| the rule says | both readers say relevant | both say not | they split |")
        add("|---|---|---|---|")
        for kind in ("answer", "near", "noise"):
            here = [p for p in both if per[models[0]][p]["kind"] == kind]
            if not here:
                continue
            yes = sum(1 for p in here if p in both_yes)
            no = sum(1 for p in here if p in both_no)
            add("| " + kind + " | %d of %d | %d of %d | %d |"
                % (yes, len(here), no, len(here), len(here) - yes - no))
        add("")
        worst = [p for p in both_no if per[models[0]][p]["kind"] == "near"]
        if worst:
            add("**%d record(s) the rule calls near misses are, to both readers, unrelated.** Those are"
                % len(worst))
            add("excluded from the noise count in PRECISION.md, so that count is a floor - and two readers")
            add("agreeing makes it a floor rather than one model's opinion:")
            add("")
            for p in worst[:4]:
                v = per[models[0]][p]
                add("- " + BT + v["corpus"] + BT + " " + BT + v["query"][:64] + BT + " -> " + BT + v["id"] + BT)
                add("  " + (v.get("why") or "(no reason given)"))
            add("")
        stingy = [p for p in both_yes if per[models[0]][p]["kind"] == "noise"]
        if stingy:
            add("**And %d record(s) the rule calls noise are, to both readers, relevant** - the other"
                % len(stingy))
            add("direction, where the rule is too harsh and the subject's precision is understated.")
            add("")
        split = [p for p in both if per[models[0]][p]["verdict"] != per[models[1]][p]["verdict"]]
        if split:
            add("**%d pair(s) the readers split on**, by what the rule said: %s. A rule that happens to"
                % (len(split), ", ".join("%s %d" % (kind, sum(1 for p in split
                                                              if per[models[0]][p]["kind"] == kind))
                                         for kind in ("answer", "near", "noise"))))
            add("agree with one of them there is not thereby right.")
            add("")

    add("## What this does not settle")
    add("")
    add("Two readers at one temperature are two opinions, not a standard. Where they agree the rule has")
    add("something to be wrong about; where they split, the question has no agreed answer and the rule's")
    add("verdict there is a coin toss with a justification. Neither reader is calibrated against a person,")
    add("and that is the next rung - an expensive one, which is why it is named rather than done.")
    add("")
    add("The prompt is a judgement call of its own. It asks whether the record would help, not whether it")
    add("is the answer, because the corpus already says which record is the answer and asking again would")
    add("test nothing.")
    add("")
    path = os.path.join(HERE, "JUDGE.md")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print("written to %s" % path)
    for m in models:
        s = summary[m]
        print("  %-30s agree %d of %d, kappa %s"
              % (m, s["agree"], s["n"], "n/a" if s["kappa"] is None else "%.2f" % s["kappa"]))
    if both:
        rows = [(per[models[0]][p]["verdict"] == "YES", per[models[1]][p]["verdict"] == "YES") for p in both]
        k = kappa(rows)
        print("  %-30s agree %d of %d, kappa %s"
              % ("readers against each other", sum(1 for a, b in rows if a == b), len(rows),
                 "n/a" if k is None else "%.2f" % k))
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
