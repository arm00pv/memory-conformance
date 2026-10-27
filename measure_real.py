"""measure every subject on the real corpus, the one with no author."""
import json, os, sys
sys.path.insert(0, "C:\\Users\\andre\\OneDrive\\Documents\\AI\\mcpc\\memory-conformance")
os.chdir("C:\\Users\\andre\\OneDrive\\Documents\\AI\\mcpc\\memory-conformance")
import matrix
with open("subjects.json", encoding="utf-8") as fh:
    subjects = json.load(fh)
for entry in subjects:
    label = "%s %s" % (entry["name"], entry["version"])
    print("real corpus: %s ..." % label, flush=True)
    summary = matrix.run_retrieval(entry, int(entry.get("timeout", 90)),
                                   cases="retrieval_corpus_real.json", suffix="-real")
    if summary:
        a = summary.get("all") or {}
        print("   h1 %s/%s, h3 %s/%s, as keywords %s"
              % (a.get("hit1"), a.get("n"), a.get("hit3"), a.get("n"), a.get("hit3_keyword")),
              flush=True)
    else:
        print("   no result", flush=True)
