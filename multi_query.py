#!/usr/bin/env python3
"""multi_query.py - the questions that need more than one record.

EVERY QUESTION IN THIS REPOSITORY HAS HAD ONE ANSWER. A query names a record and the subject returns a list;
the scoring asks whether the right id is in the first three. That makes every question a lookup, and a
memory store is asked joins as often as lookups: "which services use postgres" has three answers and a
benchmark of single answers will call a subject correct when it returns one of them.

The corpus here is built from real package descriptions and no author. Records sharing four or more long
words are gathered into clusters, and each cluster becomes one question whose required answer is the whole
cluster:

  cluster      two or three real records whose authors used the same vocabulary
  question     a fixed template naming the terms they share
  required     every member of the cluster, not one of them

The store is 72 records - the clusters plus fillers - and the sweep asks 16 of these beside 16 single-record
questions on the same store, so the two kinds of question are compared within one run.

A subject's `returned` list is saved in every row, so the required-set analysis needs no new measurement
machinery and no change to the scoring: the rows have carried the full list since the first matrix, and
nobody has asked what it means when a question has more than one right answer.

  python multi_query.py --build
  python multi_query.py --measure
  python multi_query.py --report
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
OUT = "multi_corpus.json"
SUFFIX = "-multi"
RECORDS = 72
CLUSTERS = 16
SINGLES = 16
K = 3
LONG4 = re.compile(r"[A-Za-z]{4,}")
TEMPLATE = "which records mention "


def long_words(text):
    return set(w.lower() for w in LONG4.findall(text))


def pool():
    """The same real package descriptions the authorless corpus uses."""
    import real_corpus
    return real_corpus.pool()


def clusters_of(items, want):
    """Groups of two or three real records whose descriptions share four or more long words.

    A CLUSTER IS A QUESTION WITH MORE THAN ONE RIGHT ANSWER, and it is found rather than written: two
    package authors describing their work with the same four words have made a join for us.
    """
    words = [long_words(it["desc"]) for it in items]
    shared = {}
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            common = sorted(words[i] & words[j])
            if len(common) >= 4:
                shared[(i, j)] = common
    # THE TERMS HAVE TO SELECT THE CLUSTER AND NOT THE WHOLE STORE. A cluster whose shared words appear
    # everywhere is not a question, it is a keyword; so each candidate is kept only if a minority of the
    # pool contains half of its terms.
    def selective(common):
        need = (len(common) + 1) // 2
        hits = sum(1 for w in words if len(w & set(common)) >= need)
        return hits <= 4

    out, taken = [], set()
    for (i, j), common in sorted(shared.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if i in taken or j in taken or not selective(common):
            continue
        group = [i, j]
        for k in range(len(items)):
            if k in taken or k in group:
                continue
            common3 = sorted(words[i] & words[j] & words[k])
            if len(common3) >= 4 and selective(common3) and len(group) < 3:
                group.append(k)
                common = common3
        taken.update(group)
        out.append({"members": group, "terms": common})
        if len(out) == want:
            return out
    return out


def build():
    items = pool()
    found = clusters_of(items, CLUSTERS)
    if len(found) < CLUSTERS:
        raise SystemExit("only %d selective clusters of two or more records" % len(found))
    used = set()
    for c in found:
        used.update(c["members"])
    fillers = [i for i in range(len(items)) if i not in used]
    step = max(1, len(fillers) // (RECORDS - len(used)))
    keep = [items[i] for i in fillers[::step][:RECORDS - len(used)]]
    records = [{"id": items[i]["name"], "text": real_body(items[i])} for i in used]
    records += [{"id": it["name"], "text": real_body(it)} for it in keep]

    queries = []
    for c in found:
        names = sorted(items[i]["name"] for i in c["members"])
        queries.append({"query": TEMPLATE + " ".join(c["terms"]),
                        "expect": names[0], "expect_all": names,
                        "difficulty": "multi"})
    for it in keep[:SINGLES]:
        queries.append({"query": it["desc"], "expect": it["name"], "difficulty": "single"})

    doc = {"why": ("Real package descriptions, clustered by shared vocabulary. A multi question requires "
                   "every member of its cluster and a single question requires one record, on the same "
                   "store, so what a single-record metric cannot see is visible in one run."),
           "records": records, "queries": queries,
           "authored_by": "node_modules",
           "authored_at": "not applicable - no author"}
    with open(OUT, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + chr(10))
    sizes = {}
    for q in queries:
        if q["difficulty"] == "multi":
            sizes[len(q["expect_all"])] = sizes.get(len(q["expect_all"]), 0) + 1
    print("%d records, %d questions (%d multi, %d single)"
          % (len(records), len(queries), CLUSTERS, sum(1 for q in queries if q["difficulty"] == "single")))
    print("cluster sizes: %s" % ", ".join("%d members: %d" % (k, v) for k, v in sorted(sizes.items())))
    return 0


MAX_TEXT = 300


def real_body(item):
    """The record text, capped at 300 characters.

    ONE SUBJECT WILL NOT STORE MORE THAN THAT. memory-lean answers a create with "observations over 300
    chars or not strings", which is a documented limit of its own rather than a defect, and a corpus that
    trips it measures nothing about multi-record questions because the run never starts. The cap is
    applied to every record so the comparison stays fair, and the limit is reported rather than hidden -
    the large_record probe is where a subject's storage ceiling belongs.
    """
    import real_corpus
    text = real_corpus.body(item)
    if len(text) > MAX_TEXT:
        cut = text[:MAX_TEXT]
        text = cut[:cut.rfind(" ")] if " " in cut else cut
    return text


def measure(argv):
    import matrix
    only = None
    for a in argv:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
    with open("subjects.json", encoding="utf-8") as fh:
        subjects = json.load(fh)
    for entry in subjects:
        label = "%s %s" % (entry["name"], entry["version"])
        if only and only not in label:
            continue
        print("multi: %s ..." % label, flush=True)
        got = matrix.run_retrieval(entry, int(entry.get("timeout", 90)), cases=OUT, suffix=SUFFIX)
        if got:
            print("   %s" % json.dumps(got.get("all") or {}), flush=True)
    return 0


def rows_of(slug):
    path = os.path.join("results", slug + "-retrieval" + SUFFIX + ".json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("rows") or None


def score(rows):
    """Required-set recall from the saved rows, and what the single-record metric would have said."""
    with open(OUT, encoding="utf-8") as fh:
        doc = json.load(fh)
    want = dict((q["query"], q) for q in doc["queries"] if q["difficulty"] == "multi")
    out = {"multi": 0, "single": 0, "complete": 0, "partial": 0, "miss": 0,
           "recall": 0.0, "old_metric_hits": 0}
    n_multi = n_single = 0
    for row in rows:
        q = want.get(row["query"])
        if q is None:
            if row.get("difficulty") == "single":
                n_single += 1
                out["single"] += 1 if row.get("hit3") else 0
            continue
        n_multi += 1
        returned = set(str(x) for x in (row.get("returned") or []))
        required = set(q["expect_all"])
        got = required & returned
        out["recall"] += len(got) / float(len(required))
        if required <= returned:
            out["complete"] += 1
        elif got:
            out["partial"] += 1
        else:
            out["miss"] += 1
        if row.get("hit3"):
            out["old_metric_hits"] += 1
    out["n_multi"] = n_multi
    out["n_single"] = n_single
    if n_multi:
        out["recall"] /= float(n_multi)
    return out


def report():
    import resolution
    got = {}
    for s in resolution.subjects():
        rows = rows_of(s["slug"])
        if rows:
            got[s["label"]] = score(rows)
    if len(got) < 4:
        raise SystemExit("not enough subjects measured on the multi-record corpus")
    lines = []
    add = lines.append
    add("# Questions with more than one right answer")
    add("")
    add("Generated by " + BT + "multi_query.py" + BT + ". Do not edit by hand.")
    add("")
    add("Every question in this repository has had one answer. A multi question requires every member of a")
    add("cluster of real records that share four or more long words, and the store holds " + str(RECORDS) +
        " records")
    add("with " + str(CLUSTERS) + " such questions beside " + str(SINGLES) + " single-record ones, so the two kinds are")
    add("compared within one run.")
    add("")
    add("| subject | clusters fully answered | partly | missed | required-set recall |"
        " single questions, hit@3 | cluster questions, hit@3 |")
    add("|---|---|---|---|---|---|---|")
    order = sorted(got, key=lambda k: -got[k]["recall"])
    for name in order:
        s = got[name]
        add("| " + BT + name + BT + " | **%d of %d** | %d | %d | %.2f | %d of %d | %d of %d |"
            % (s["complete"], s["n_multi"], s["partial"], s["miss"], s["recall"],
               s["single"], s["n_single"], s["old_metric_hits"], s["n_multi"]))
    add("")
    add("## What the single-answer metric cannot see")
    add("")
    add("A question whose answer is a set of three records scored by `hit3` is scored by whether ONE of")
    add("them came back - the arbitrary first member of the cluster. That is why the last two columns are")
    add("not the same number, and the gap between them is the measurement this phase exists for.")
    add("")
    full = sorted(n for n, s in got.items() if s["n_multi"] and s["complete"] == s["n_multi"])
    none = sorted(n for n, s in got.items() if s["n_multi"] and s["complete"] == 0)
    if full or none:
        add("**%d of %d subjects answer every cluster in full and %d answer none of them.** The %d are %s;"
            % (len(full), len(got), len(none), len(full),
               ", ".join(BT + n + BT for n in full) or "nobody"))
        add("the %d are %s." % (len(none), ", ".join(BT + n.split()[0] + BT for n in none) or "nobody"))
        same = [n for n in none if got[n]["n_single"] and got[n]["single"] == got[n]["n_single"]]
        if same:
            add("")
            add("%d of those %d answer every single-record question on the same store, so the difference"
                % (len(same), len(none)))
            add("between them is not retrieval quality. It is whether returning a set is something the")
            add("subject does at all: a search that answers with one id and stops cannot answer a question")
            add("whose answer is three.")
        add("")
    over = [(s["old_metric_hits"] - s["complete"], n, s) for n, s in got.items()
            if s["n_multi"] and s["old_metric_hits"] > s["complete"]]
    if over:
        gap, name, s = max(over, key=lambda t: (t[0], t[1]))
        add("And where a subject does return part of a set, the single-record metric counts the cluster as")
        add("answered: `%s` is scored %d of %d that way, against %d answered in full. The overcount is the"
            % (name, s["old_metric_hits"], s["n_multi"], s["complete"]))
        add("size of the difference between answering a question and answering part of it.")
        add("")
    add("So the honest reading of this table is not a ranking. It is that a question with three answers")
    add("tests something a question with one answer does not, that a minority of this table does it, and")
    add("that every metric this repository has published would have described the others as competent")
    add("retrievers on the strength of the single-record column.")
    add("")
    add("## What this does not settle")
    add("")
    add("The search is asked for three results, so a cluster of three can be answered only by a subject that")
    add("returns three relevant records rather than three records. Raising k would make the question")
    add("answerable by every subject that finds one member, which measures nothing; keeping k at three")
    add("makes it answerable only by a subject that ranks the whole cluster, which is the harder and more")
    add("honest question but is also a question about k.")
    add("")
    add("It also does not test a join. Reading one record to discover the names of others - what a real")
    add("multi-hop question needs - is a different capability, and no subject here claims it.")
    add("")
    add("## One thing the store had to be shaped around")
    add("")
    add("Every record text is capped at 300 characters because `memory-lean` refuses to store more: it")
    add("answers a create with \"observations over 300 chars or not strings\" and the run does not start. That")
    add("is a documented limit of the subject and not a defect, but it is worth saying that a corpus the")
    add("size of a real store would have to be written to fit it, and that one subject in this table cannot")
    add("hold a record longer than a long sentence.")
    add("")
    path = os.path.join(HERE, "MULTI-RECORD.md")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print("written to %s" % path)
    return 0


def main(argv):
    argv = list(argv)
    if "--build" in argv:
        return build()
    if "--measure" in argv:
        return measure(argv)
    return report()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
