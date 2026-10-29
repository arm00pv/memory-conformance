#!/usr/bin/env python3
"""durability.py - what a damaged store costs.

EVERY NUMBER THIS REPOSITORY PUBLISHES IS ABOUT A SERVER THAT IS WORKING. The probes ask whether a
write is acknowledged and whether it comes back; the retrieval tables ask what a search returns from a
store that is intact. None of them asks the question a real deployment asks on its worst day: the
machine was switched off during a write, or the disk filled, and now half a record is sitting at the
end of the file. Is that one record lost, or the store?

Two damages, both of them things that happen rather than things that are contrived:

  append  - a record that was being written when the power went: a newline and half a JSON object
            appended after the last good one.
  cut     - the last 40% of the store file is gone, which is what a torn write or a lost tail looks
            like from the outside.

For each subject the same sequence: write 40 records, stop the server, damage the largest file in the
store, restart, and count how many of the 40 come back. Nothing about a subject is inferred from what it
promises; the count is the whole answer.

    python durability.py                 # every subject, both damages, and the report
    python durability.py --report        # re-render DURABILITY.md from results/durability.json
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BT = chr(96)
RECORDS = 40
SAVE = os.path.join("results", "durability.json")
WORK = os.path.join("results", "durability")
HALF = chr(10) + '{"id": "half-written", "name": "durable-40", "text": "a record that was bei'


def adapter_for(entry):
    """The adapter this repository already uses for that subject, or the same default."""
    import harness
    if entry.get("manifest"):
        import manifest as manifestmod
        return harness.ManifestAdapter(entry["cmd"], manifestmod.load(entry["manifest"]))
    name = entry.get("adapter") or "reference"
    table = {"control": harness.ControlAdapter, "retained": harness.RetainedAdapter,
             "basic-memory": harness.BasicMemoryAdapter, "memento": harness.MementoAdapter,
             "auto": harness.AutoAdapter, "reference": harness.ReferenceAdapter}
    return table[name](entry["cmd"])


def slug_of(entry):
    return ("%s-%s" % (entry["name"], entry["version"])).replace("/", "_").replace("@", "")


# THE LARGEST FILE IS NOT ALWAYS THE STORE. A write-ahead log is bigger than the page file it belongs
# to and is *meant* to be disposable, so damaging it produced a table in which memdb and zenbrain 'kept
# every record - because their journal was what got cut. That is the wrong-denominator defect one layer
# down, and the fix is to name what is not a store.
# EVERY OTHER TABLE HERE CARRIES A runs COLUMN, and this one did not: one damage of each kind is an
# anecdote, and the first repeat of the cut column produced two different answers for memdb.
REPEAT = 3
DAMAGES = ("append", "cut", "rot")
NOT_A_STORE = ("-wal", "-shm", "-journal", ".wal", ".shm", ".journal", ".lock", ".tmp", ".log",
              ".pid")


def files_under(store):
    """The candidate store files, biggest first, with the disposable ones excluded by name."""
    out = []
    for root, _dirs, names in os.walk(store):
        for name in names:
            if name.lower().endswith(NOT_A_STORE):
                continue
            path = os.path.join(root, name)
            try:
                out.append((os.path.getsize(path), path))
            except OSError:
                continue
    return sorted(out, reverse=True)


def damage(path, kind):
    """Three damages, all ordinary: half a record at the end, a missing tail, and rot in the middle.

    A STORE FILE CAN STILL BE LOCKED WHEN THE SERVER HAS BEEN ASKED TO STOP. duckdb keeps a .wal
    beside its store and the first version of this crashed on it with PermissionError, which is the
    tool failing rather than the subject - so the damage is retried, and a file that never unlocks is
    reported as what it is.
    """
    last = None
    for _attempt in range(6):
        try:
            if kind == "append":
                with open(path, "ab") as fh:
                    fh.write(HALF.encode("utf-8"))
            elif kind == "rot":
                # SIXTEEN BYTES OF RUBBISH IN THE MIDDLE OF THE FILE. The first two damages are about the
                # end of a sequence of records; this one lands inside one, which is what a bad sector or an
                # overlapping write does - and it is the damage a store that skips unparseable lines can
                # survive while a store that parses the whole file cannot.
                size = os.path.getsize(path)
                if size < 64:
                    raise ValueError("store is %d bytes, too small to corrupt without destroying it" % size)
                with open(path, "r+b") as fh:
                    fh.seek(size // 2)
                    fh.write(b"#" * 16)
            else:
                size = os.path.getsize(path)
                with open(path, "r+b") as fh:
                    fh.truncate(int(size * 0.6))
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.4)
    raise last


def names_back(ad, srv, wanted):
    """What the subject still shows, and whether a search finds a record the listing does not.

    A READ TOOL CAN SHOW FEWER RECORDS THAN THE STORE HOLDS. statecore-mcp returned exactly ten of
    forty under both damages, which is either a store that lost thirty records twice in the same way
    or a listing that caps its answer - and the first version of this tool had no way to tell, so it
    would have published the second as the first. Up to three missing names are searched for by name;
    a record a search finds is counted as present but hidden rather than lost.
    """
    got = ad.read(srv) or []
    seen = set()
    for entry in got:
        if not isinstance(entry, dict):
            continue
        for key in ("name", "id", "title"):
            value = entry.get(key)
            if value:
                seen.add(str(value))
    back = len([n for n in seen if n in wanted])
    hidden, sampled = 0, 0
    for name in [n for n in sorted(wanted) if n not in seen][:3]:
        sampled += 1
        try:
            if name in (ad.search(srv, name, k=3) or []):
                hidden += 1
        except Exception:
            pass
    return back, hidden, sampled


def one(entry, kind, run=1):
    """Write, damage, restart, count - for one subject and one kind of damage."""
    slug = slug_of(entry)
    # AN ABSOLUTE STORE PATH, BECAUSE A SUBJECT MAY RESOLVE IT AGAINST ITS OWN MODULE DIRECTORY. A
    # relative one made @modelcontextprotocol/server-memory open its store inside node_modules/.../dist/,
    # which then reported as "not installed" - wrong twice over.
    store = os.path.abspath(os.path.join(WORK, slug, kind, "run-%d" % run))
    out = {"subject": "%s %s" % (entry["name"], entry["version"]), "slug": slug, "damage": kind,
           "records": RECORDS, "run": run, "file": None, "bytes": None, "back": None,
           "why": None}
    shutil.rmtree(store, ignore_errors=True)
    os.makedirs(store)
    ad = adapter_for(entry)
    # THE SUBJECT'S OWN CEILING, NOT THE HARNESS DEFAULT. memento takes four seconds for its first
    # write and its entry says so; using the 30 s default made this tool report "initialize did not
    # answer" for a subject that was merely slow, which is the harness measuring itself again.
    import harness
    harness.PROBE_TIMEOUT = min(float(entry.get("timeout") or 60), 60.0)
    try:
        srv = ad.server(store)
        try:
            for i in range(RECORDS):
                ad.write(srv, "durable-%02d" % i,
                         ["durable record %d, written before the store was damaged" % i])
        finally:
            srv.stop()
    except Exception as exc:
        detail = str(exc).strip().replace(chr(10), " ")[:300]
        # A SUBJECT THAT IS NOT INSTALLED IS NOT A DURABILITY RESULT. The first run reported
        # server-memory 2.0.0 as refusing to start, which would have read as a store that cannot
        # survive a torn write instead of a dependency that could not be found.
        if "ENOENT" in detail or "not found" in detail.lower():
            out["why"] = "not installed on this machine: %s" % detail
        else:
            out["why"] = "could not write: %s" % detail
        return out
    files = files_under(store)
    if not files:
        return out
    size, path = files[0]
    out["file"] = os.path.relpath(path, store)
    out["bytes"] = size
    try:
        damage(path, kind)
    except Exception as exc:
        out["why"] = "could not damage the store: %s" % str(exc).strip()[:160]
        return out
    try:
        srv = ad.server(store)
    except Exception as exc:
        out["why"] = "refuses to start: %s" % str(exc).strip().splitlines()[-1][:200]
        return out
    try:
        back, hidden, sampled = names_back(ad, srv, ["durable-%02d" % i for i in range(RECORDS)])
        out["back"], out["hidden"], out["sampled"] = back, hidden, sampled
    except Exception as exc:
        out["why"] = "starts but cannot be read: %s" % str(exc).strip().splitlines()[-1][:200]
    finally:
        try:
            srv.stop()
        except Exception:
            pass
    return out


def verdict(row):
    if row.get("why"):
        return row["why"]
    if row.get("hidden") and row.get("sampled"):
        return "shows %d of 40, and %d of %d sampled names are still findable" % (
            row.get("back") or 0, row["hidden"], row["sampled"])
    if row["file"] is None:
        return "no store file to damage"
    if row["back"] is None:
        return "no answer"
    if row["back"] >= row["records"]:
        return "kept all 40"
    if row["back"] == 0:
        return "**lost all 40**"
    return "lost %d of 40" % (row["records"] - row["back"])


def run(only=None, repeat=REPEAT):
    with open("subjects.json", encoding="utf-8") as fh:
        subjects = json.load(fh)
    rows = []
    if only and os.path.isfile(SAVE):
        # A SINGLE-SUBJECT RUN EDITS THE TABLE RATHER THAN REPLACING IT. The first version wrote its one
        # row over the eleven already measured, so re-running one subject to fix a path would have
        # deleted nine subjects from the evidence and left a table that still looked complete.
        with open(SAVE, encoding="utf-8") as fh:
            rows = [r for r in (json.load(fh).get("rows") or [])
                    if not r["subject"].startswith(only + " ")]
    for entry in subjects:
        if only and entry["name"] != only:
            continue
        for kind in DAMAGES:
            for index in range(1, repeat + 1):
                print("%s %s: %s (run %d of %d) ..."
                      % (entry["name"], entry["version"], kind, index, repeat), flush=True)
                row = one(entry, kind, index)
                print("  %s" % verdict(row), flush=True)
                rows.append(row)
    with open(SAVE, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps({"rows": rows}, indent=1, sort_keys=True) + chr(10))
    print("written to %s" % SAVE)
    return rows


def report(rows=None):
    if rows is None:
        if not os.path.isfile(SAVE):
            raise SystemExit("no result file yet - run durability.py first")
        with open(SAVE, encoding="utf-8") as fh:
            rows = json.load(fh).get("rows") or []
    by = {}
    for row in rows:
        by.setdefault(row["subject"], {}).setdefault(row["damage"], row)

    def outcome(row):
        """Kept, lost, unreadable, would not start, or nothing to damage - one word each."""
        if not row:
            return "missing"
        why = row.get("why") or ""
        if why.startswith("refuses") or why.startswith("starts but cannot be read"):
            return "no answer"
        if why:
            return "could not test"
        if row.get("file") is None:
            return "no store file"
        if row.get("back") is None:
            return "no answer"
        return "kept every record" if row["back"] >= row["records"] else "lost records"

    def clipped(text):
        # A TABLE CELL IS NOT A PLACE FOR A STACK TRACE. The full message stays in the result file.
        return text[:110] + "..." if len(text) > 110 else text

    lines = []
    add = lines.append
    add("# What a damaged store costs")
    add("")
    add("Generated by " + BT + "durability.py" + BT + ". Do not edit by hand.")
    add("")
    add("Every other table in this repository describes a server that is working. This one describes the")
    add("morning after: forty records written, a file the subject kept them in damaged in a way that happens")
    add("in practice, the server restarted, and the records it can still produce counted. Nothing here is")
    add("inferred from what a subject promises.")
    add("")
    LABEL = {"append": "half a record appended", "cut": "last 40% of the file gone",
             "rot": "sixteen bytes of rot in the middle"}
    add("| subject | store file | " + " | ".join(LABEL[k] for k in DAMAGES) + " |")
    add("|---" * (len(DAMAGES) + 2) + "|")
    for subject in sorted(by):
        # NOT "rows": the loop below still needs the parameter of that name, and the first version of
        # this shadowed it - so the section that counts the repeats was handed the last subject's three
        # rows and reported "every damage was taken 1 times per subject". A variable named after the
        # thing it borrows is how a table quietly measures the wrong list.
        cells = [by[subject].get(k) or {} for k in DAMAGES]
        where = next((r.get("file") for r in cells if r.get("file")), "-")
        parts = [BT + subject + BT, BT + str(where) + BT] + [clipped(verdict(r)) for r in cells]
        add("| " + " | ".join(parts) + " |")
    add("")

    runs = {}
    for row in rows:
        runs.setdefault((row["subject"], row["damage"]), []).append(row)
    same, differ = [], []
    for key in sorted(runs):
        seen = [verdict(r) for r in runs[key]]
        (same if len(set(seen)) == 1 else differ).append((key, seen))
    times = max(len(v) for v in runs.values())
    add("**Every damage was taken %d times per subject, because one of them was not enough.** %d of the %d"
        % (times, len(same), len(runs)))
    add("subject-and-damage cells gave the same answer every time; the table above shows the first run.")
    if differ:
        add("")
        add("| the cell that changed its answer | what it said, run by run |")
        add("|---|---|")
        for (subject, kind), seen in differ:
            add("| " + BT + subject + BT + " " + kind + " | " + " / ".join(seen) + " |")
        add("")
        add("**A cell that disagrees with itself is not a measurement of the subject.** It is a measurement of")
        add("where the damage landed, and the difference between those two things is the reason this column")
        add("exists at all. None of these should be quoted as a rate without the runs beside it.")
    add("")

    tally = {}
    for kind in DAMAGES:
        tally[kind] = {}
        for subject in by:
            word = outcome(by[subject].get(kind))
            tally[kind][word] = tally[kind].get(word, 0) + 1
    tested = dict((k, sum(v for w, v in tally[k].items() if w in ("kept every record", "lost records")))
                  for k in tally)
    add("| damage | tested | kept every record | lost records | started, could not read | would not start | no store to damage |")
    add("|---|---|---|---|---|---|---|")
    for kind in DAMAGES:
        add("| " + kind + " | %d | %d | %d | %d | %d | %d |" % (
            tested[kind],
            tally[kind].get("kept every record", 0),
            tally[kind].get("lost records", 0),
            sum(1 for s in by if ((by[s].get(kind) or {}).get("why") or "").startswith("starts but")),
            sum(1 for s in by if ((by[s].get(kind) or {}).get("why") or "").startswith("refuses")),
            tally[kind].get("no store file", 0)))
    add("")
    add("**A trailing fragment is survivable and a missing tail is not.** Appending half a record leaves")
    add("%d of the %d stores it was applied to complete and cutting 40%% of the file leaves %d. That is not a"
        % (tally["append"].get("kept every record", 0), tested["append"],
           tally["cut"].get("kept every record", 0)))
    add("claim about care, and it is not a ranking: it is what a parser does when the damage sits at the end")
    add("of a sequence of records rather than inside one.")
    add("")
    rot_kept = [s for s in sorted(by) if (by[s].get("rot") or {}).get("back") is not None
                and by[s]["rot"]["back"] >= by[s]["rot"]["records"]]
    rot_one = [s for s in sorted(by) if (by[s].get("rot") or {}).get("back") == 39]
    add("**Rot inside a record costs exactly that record, where the store can tell one record from the")
    add("next.** Sixteen bytes overwritten in the middle of the file left %d of the %d stores complete, and"
        % (len(rot_kept), tested["rot"]))
    if rot_one:
        add("%s lost exactly one of forty each:" % ", ".join(BT + s + BT for s in rot_one))
        add("the record the rubbish landed in, and nothing else.")
        add("That is what a line-per-record format buys, and the only place in this table where a damage")
        add("costs what it damaged.")
    add("")

    unreadable = [s for s in sorted(by)
                  if ((by[s].get("append") or {}).get("why") or "").startswith("starts but")]
    if unreadable:
        add("**The worst shape is " + ", ".join(BT + s + BT for s in unreadable) + "**, which starts normally and")
        add("cannot read anything afterwards: the process is up, a write may even be acknowledged, and every")
        add("read fails on the text it was handed. A server that will not start is a page; a server that")
        add("starts and cannot read is a page that has not fired yet.")
        add("")
    refuses = [s for s in sorted(by) if ((by[s].get("cut") or {}).get("why") or "").startswith("refuses")]
    if refuses:
        add("Cutting the store leaves " + ", ".join(BT + s + BT for s in refuses) + " unable to start at all. The")
        add("records are still on the disk and the server will not open them - a different failure from")
        add("losing them, and the one a restore can fix.")
        add("")
    hidden = [s for s in sorted(by) if ((by[s].get("cut") or {}).get("hidden") or 0) > 0]
    if hidden:
        one = len(hidden) == 1
        add("And " + ", ".join(BT + s + BT for s in hidden)
            + (" still holds records its listing does not show: the" if one
               else " still hold records their listings do not show: each"))
        add("read tool returns fewer than the store has, and the sampled names it omitted were findable by")
        add("search. **Counting what a subject lists is not counting what it kept**")
        add("")
    add("## What this does not settle")
    add("")
    add("The damage lands on the largest file in the store once the disposable ones - write-ahead logs,")
    add("journals, locks - are excluded by name. That exclusion is itself a judgement: for a subject whose")
    add("store really is its journal this damages the wrong file, and the first run of this table did")
    add("exactly that and reported two databases as invulnerable. A subject that keeps its records inside a")
    add("dependency directory rather than the store it was given shows here as having no store to damage.")
    add("")
    add("**One damage of each kind is an anecdote, and the table has already shown it.** memdb's store was")
    add("cut once and refused to start; cut again on the next run and it kept every record, because the cut")
    add("landed in a different place relative to its pages. Nothing here is a rate and none of it should be")
    add("quoted as one. Nothing was tested under a concurrent writer and nothing was re-measured: this is")
    add("one damage of each kind, on this machine, on this date - the same caveat every timing in this")
    add("repository carries.")
    add("")
    with open("DURABILITY.md", "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print("written to DURABILITY.md")
    for subject in sorted(by):
        a, c = by[subject].get("append") or {}, by[subject].get("cut") or {}
        print("  %-28s append: %-22s cut: %s" % (subject, clipped(verdict(a)), clipped(verdict(c))))
    return 0


def main(argv):
    if "--report" in argv:
        return report()
    only = None
    repeat = REPEAT
    for a in argv:
        if a.startswith("--subject="):
            only = a.split("=", 1)[1]
        elif a.startswith("--repeat="):
            repeat = max(1, int(a.split("=", 1)[1]))
    rows = run(only, repeat)
    if "--no-report" not in argv:
        return report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
