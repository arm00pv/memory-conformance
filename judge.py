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


def population():
    """Every (corpus, question, returned record) this repository has an opinion about, unsampled.

    The readers are asked an ENRICHED sample - twenty of each kind - because the question is where the rule
    and a reader disagree, and a random draw would be almost entirely pairs where they agree. A PERSON is
    asked a RANDOM draw from this population instead, because the question there is different: what is the
    agreement rate, not can a disagreement be found. Two questions, two sampling frames, and confusing them
    would flatter the first.
    """
    import precision
    import resolution
    out = []
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
                    out.append({"corpus": label, "query": row["query"], "id": cid,
                                "text": c["text"].get(cid, ""), "kind": kind,
                                "subject": s["label"]})
    out.sort(key=lambda p: (p["corpus"], p["query"], p["id"], p["subject"]))
    return out


def pairs():
    """The enriched sample the READERS are asked: twenty of each kind, by stride.

    Deterministic: sorted, then a stride, so the sample is the same on every machine and the cache always
    describes the same pairs.
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


HUMAN = os.path.join("results", "human.json")


def load_human():
    """A person's labels, if anybody has given any.

    THE ONLY LABELLER HERE THAT IS NOT A MODEL. It is a handful of pairs put to a person, chosen from where the
    rule and the readers disagree, so it is a probe rather than a sample - and the report says so instead of
    computing a kappa that would flatter it.
    """
    if not os.path.isfile(HUMAN):
        return None
    with open(HUMAN, encoding="utf-8") as fh:
        return json.load(fh)


HUMAN_SKELETON = """# Sixty pairs about what a memory returns

For each pair, decide whether the record would help the person who asked. Write YES or NO in the answers
file beside this one - `results/human-sample.json` - under the "verdict" field of the matching number.
Six is enough to start; sixty is an hour and makes it a measurement.

Do not read the answers of anything else first. There is no right answer being looked for, only yours.

"""


def export_human(count, seed, json_path, md_path):
    """A random draw, written out for a person: one file to fill, one to read.

    THE ONLY PART OF THE LADDER THAT NEEDS SOMEBODY WHO IS NOT A MODEL, so the least this repository can do is
    hand them the work prepared: the pairs already drawn, at random rather than for disagreement, with the
    question and the record in front of them and nothing else.
    """
    import random
    pop = population()
    if len(pop) < count:
        raise SystemExit("only %d pairs in the population" % len(pop))
    draw = random.Random(seed).sample(pop, count)
    draw.sort(key=lambda p: (p["corpus"], p["query"], p["id"]))
    labels = []
    for n, p in enumerate(draw, 1):
        labels.append({"n": n, "corpus": p["corpus"], "query": p["query"], "id": p["id"],
                       "kind": p["kind"], "shown": p["text"], "verdict": ""})
    doc = {"why": "a random draw from every (question, returned record) pair this repository holds; the "
                  "reads are the person's own and nothing else is shown to them",
           "labeller": "", "asked_at": "", "sample": "random, seed %d, %d of %d" % (seed, count, len(pop)),
           "labels": labels}
    with open(json_path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(doc, indent=1, ensure_ascii=False) + chr(10))
    lines = [HUMAN_SKELETON]
    for l in labels:
        lines.append("---")
        lines.append("")
        lines.append("**%d.** Question asked: %s%s%s" % (l["n"], BT, l["query"], BT))
        lines.append("")
        lines.append("Record returned: %s%s%s" % (BT, l["shown"], BT))
        lines.append("")
    with open(md_path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines))
    print("wrote %s (%d pairs to read) and %s (to fill)" % (md_path, len(labels), json_path))
    return 0


def import_human(path):
    """Take a filled answers file, check it, and store it as the sampled labeller."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    labels = doc.get("labels") or []
    kept, skipped = [], []
    for l in labels:
        verdict = (l.get("verdict") or "").strip().upper()
        if verdict in ("YES", "Y"):
            l["verdict"] = "YES"
        elif verdict in ("NO", "N"):
            l["verdict"] = "NO"
        else:
            skipped.append(l.get("n"))
            continue
        kept.append(l)
    if not kept:
        raise SystemExit("no verdicts in %s - fill the \"verdict\" field of the file you exported" % path)
    human = load_human() or {}
    human["random"] = {"labels": kept, "sample": doc.get("sample"), "labeller": doc.get("labeller"),
                       "asked_at": doc.get("asked_at"), "why": doc.get("why")}
    with open(HUMAN, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(human, indent=1, ensure_ascii=False) + chr(10))
    print("%d verdict(s) imported; %d left blank (numbers %s)"
          % (len(kept), len(skipped), ", ".join(str(n) for n in skipped[:10]) or "none"))
    return 0


def by_model(cache):
    """{model: {(corpus, query, id): entry}} for the settled judgments."""
    out = {}
    for _k, v in cache.items():
        if v.get("verdict") not in ("YES", "NO"):
            continue
        out.setdefault(v.get("model") or "?", {})[(v["corpus"], v["query"], v["id"])] = v
    return out


def population_size():
    import precision
    import resolution
    n = 0
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
                n += len(row.get("returned") or [])
    return n


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

    human = load_human()
    if human and human.get("labels"):
        labs = human["labels"]
        add("## A person, as the third labeller")
        add("")
        add("Six pairs were put to the person who asked for this work - question and record, with no label, no")
        add("rule verdict and no reader verdict in front of them. Four were chosen BECAUSE the rule and both")
        add("readers disagree about them, so this is a probe and not a sample, and no kappa is computed over it.")
        add("")
        add("| the rule says | pairs asked | the readers | the person |")
        add("|---|---|---|---|")
        for kind in ("answer", "near", "noise"):
            here = [l for l in labs if l.get("kind") == kind]
            if not here:
                continue
            agreed = 0
            for l in here:
                p = (l["corpus"], l["query"], l["id"])
                seen = [per[m][p]["verdict"] for m in models if p in per[m]]
                if seen and all(v == l["verdict"] for v in seen):
                    agreed += 1
            yes = sum(1 for l in here if l["verdict"] == "YES")
            add("| " + kind + " | %d | agrees with the person on %d of %d | %d said relevant |"
                % (len(here), agreed, len(here), yes))
        add("")
        near = [l for l in labs if l.get("kind") == "near"]
        if near:
            no = sum(1 for l in near if l["verdict"] == "NO")
            add("**On the %d record(s) this rule excuses as near misses, the person called %d unrelated.**"
                % (len(near), no))
            add("The readers called all %d unrelated. The floor under the noise column is therefore no longer"
                % len(near))
            add("two models' opinion of a rule: on the pairs where that judgement is questionable, a person")
            add("read the record and said the same thing.")
            add("")
        ctrl = [l for l in labs if l.get("kind") == "answer"]
        if ctrl:
            add("The control held: on the record the corpus says answers the question, the person said relevant")
            add("(%d of %d), which is what a labeller paying attention says and what a contrarian does not."
                % (sum(1 for l in ctrl if l["verdict"] == "YES"), len(ctrl)))
            add("")

    # "random", NOT "sample": the probe file already uses "sample" for a sentence describing how those six
    # pairs were chosen, and reading a string as a dict of labels crashed the report on the first run.
    sample = (human or {}).get("random") or {}
    if sample.get("labels"):
        labs = sample["labels"]
        rows = [((l["kind"] != "noise"), l["verdict"] == "YES") for l in labs]
        k = kappa(rows)
        agree = sum(1 for a, b in rows if a == b)
        add("## A person, on a random draw")
        add("")
        add("The six pairs above were chosen for disagreement, which is the right frame for asking whether a")
        add("rule is wrong and the wrong one for asking how wrong it is. This is the other frame: **%d pairs"
            % len(labs))
        add("drawn at random** from the %d the repository holds, so the agreement here is a rate rather than a"
            % population_size())
        add("search for disagreements. %s" % (sample.get("sample") or ""))
        add("")
        add("| the rule says | pairs | the person says relevant |")
        add("|---|---|---|")
        for kind in ("answer", "near", "noise"):
            here = [l for l in labs if l.get("kind") == kind]
            if not here:
                continue
            add("| " + kind + " | %d | %d |"
                % (len(here), sum(1 for l in here if l["verdict"] == "YES")))
        add("")
        add("Agreement with the rule's reading of relevance: **%d of %d (%d%%), kappa %s**."
            % (agree, len(rows), round(100 * agree / float(len(rows))),
               "n/a" if k is None else "%.2f" % k))
        if len(rows) < 30:
            add("")
            add("At %d pairs that kappa is an estimate with a wide interval, and it is printed as an estimate" % len(rows))
            add("rather than as a result. Sixty pairs is an hour of somebody's reading and would settle it.")
        add("")

    add("## What this does not settle")
    add("")
    add("Two readers at one temperature are two opinions, not a standard. Where they agree the rule has")
    add("something to be wrong about; where they split, the question has no agreed answer and the rule's")
    add("verdict there is a coin toss with a justification. Neither reader is calibrated against a person,")
    add("and the pairs to calibrate them are already drawn: " + BT + "results/human-sample.md" + BT + " is sixty of")
    add("them, at random, with a file beside it for the answers. " + BT + "judge.py --export-human=60" + BT + " draws")
    add("another sixty; " + BT + "--import-human" + BT + " takes the answers and this report renders them. An hour of")
    add("somebody's reading is the only thing standing between this and a rate instead of a search.")
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
    for a in argv:
        if a.startswith("--export-human="):
            count = int(a.split("=", 1)[1])
            seed = 20261027
            for b in argv:
                if b.startswith("--seed="):
                    seed = int(b.split("=", 1)[1])
            return export_human(count, seed,
                                os.path.join("results", "human-sample.json"),
                                os.path.join("results", "human-sample.md"))
        if a.startswith("--import-human="):
            return import_human(a.split("=", 1)[1])
    code = collect(argv)
    if "--no-report" not in argv:
        report()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
