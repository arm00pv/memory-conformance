#!/usr/bin/env python3
"""control/memory_server.py - a minimal MCP memory server built so the probes CAN pass.

A conformance suite that only ever fails is not measuring anything: it proves nothing except that the
probes are harsh. This is the positive control - the smallest server that keeps the four promises the
probes test, and it is built around the opposite decision from the server that fails:

  APPEND-ONLY, NEVER REWRITE. The reference implementation parses the store into its own model and
  rewrites the whole file on every mutation, so a field it does not model is discarded. Here a write
  appends one line and touches nothing else, which means unknown fields, unknown record types and
  concurrent writers are preserved by construction rather than by care.

  A WRITE IS NOT ACKNOWLEDGED UNTIL IT IS READ BACK. Every write is answered with the bytes that were
  written and the bytes that were read from the file afterwards, so a caller can tell a landed write
  from a claimed one.

Tools:
  memory_write {name, observations, fields?}  -> {ok, seq, line, bytes, readback_verified}
  memory_forget {name}                        -> {ok, forgotten, bytes}   (appends a tombstone)
  memory_read  {}                             -> {entities: [...]}
  memory_verify {}                            -> {records, verified, corrupt_lines, path}

stdio only, newline-delimited JSON-RPC, no dependencies beyond the standard library.

DELIBERATELY BROKEN COPIES. Set MEMORY_MUTANT=<name> and this same file becomes a subject that breaks
exactly one promise, so the probe that watches that promise has something to fail on. A control proves
the probes CAN pass; this proves each probe CAN fail, and neither of the two is worth much alone. The
names live in mutants.py with the verdict vector each one is expected to produce.
"""
import json
import os
import sys

STORE = os.environ.get("MEMORY_FILE_PATH") or os.path.join(os.getcwd(), "memory.json")

# ONE PROMISE, BROKEN ON PURPOSE. Empty means "the control as documented".
MUTANT = (os.environ.get("MEMORY_MUTANT") or "").strip()

# A SECOND FILE THE MUTANT CAN WRITE TO. Kept out of the store directory on purpose: the isolation
# probe hands the server two different directories and expects them to stay different, so a leak has
# to be somewhere the per-store path does not reach.
# GATED ON THE MUTANT. A leak that is merely available is a leak that every other mutant gets for
# free, and a verdict vector nobody predicted is not a test - it is a surprise.
LEAK = ((os.environ.get("MEMORY_LEAK_PATH") or "").strip()
        if MUTANT == "leak-everywhere" else "")

# The store as this process first saw it. Never re-read, which is what makes two processes disagree.
_CACHE = None


def _locked(fn):
    """An OS lock around the append. The first version of this file relied on O_APPEND alone and
    lost 4 of 20 concurrent writes on Windows: the position is fixed at open time, so two processes
    can write at the same offset and clobber each other. That is the same failure the reference
    server is reported to have, and the fix is the boring one - one writer at a time."""
    lock_path = STORE + ".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        return fn()
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _append_line(obj):
    """One append under the lock, then read the file back and compare what landed."""
    line = json.dumps(obj, sort_keys=True)
    data = (line + chr(10)).encode("utf-8")

    def do():
        # O_BINARY IS NOT OPTIONAL ON WINDOWS. Without it the C runtime translates this "\n" into
        # "\r\n" on the way out, so the bytes on disk never match the bytes this server wrote - and
        # the read-back check below was FALSE for every write this server ever made, on every probe,
        # for eighteen phases. Nothing noticed because the suite checks the read-back itself and never
        # asked the control whether its own verification had passed. A server that reports failure and
        # does the right thing is still reporting failure.
        fd = os.open(STORE, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0),
                     0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)

    _locked(do)
    with open(STORE, "rb") as fh:
        body = fh.read()
    ok = body.endswith(data)
    return line, len(data), ok


def _write_rows(rows):
    fd = os.open(STORE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
                 0o644)
    try:
        blob = "".join(json.dumps(obj, sort_keys=True) + chr(10) for obj in rows)
        os.write(fd, blob.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return len(rows)


def _rewrite(rows):
    """Replace the whole store with these rows. The mutation lever: a server that rewrites has to
    decide what it keeps, and everything it does not model is what disappears."""
    _locked(lambda: _write_rows(rows))
    return len(rows)


def _remodel(transform):
    """Read, transform and rewrite as ONE step under ONE lock.

    ONE MUTATION AT A TIME, AND THE LOCK IS PART OF THAT. The field and record mutations rewrite the
    whole store, and the first version read the store outside the lock and wrote it back inside, so
    two concurrent writers could each overwrite the other's append with what they had read a moment
    earlier. That is a concurrency defect bolted onto a mutation that was supposed to be about what
    the server keeps - two promises broken, and the row stops saying which one the probe caught.

    It also made the table platform-dependent and nothing noticed: on Windows the race did not bite
    and both mutants passed `concurrent`, on Linux it wiped the store and both failed it. The
    prediction was written for one mutation and the code shipped two, which is the kind of thing only
    a second scheduler finds.
    """
    def do():
        rows, _corrupt = _records()
        return _write_rows(transform(rows))
    return _locked(do)


def _leak_append(obj):
    """Write the same record somewhere no per-store path points at."""
    if not LEAK:
        return
    with open(LEAK, "a", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(obj, sort_keys=True) + chr(10))


def _leak_records():
    out = []
    if not LEAK:
        return out
    try:
        with open(LEAK, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    out.append(json.loads(raw))
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return out


def _records():
    out = []
    corrupt = 0
    try:
        with open(STORE, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    out.append(json.loads(raw))
                except ValueError:
                    corrupt += 1
    except FileNotFoundError:
        pass
    return out, corrupt


def tool_write(args):
    global _CACHE
    # UNKNOWN FIELDS RIDE ALONG. A caller - or another tool - may attach anything; it is stored and
    # returned untouched, because this server has no model to lose it in.
    obj = {"name": args.get("name"), "entityType": args.get("entityType", "probe"),
           "observations": list(args.get("observations") or [])}
    for key, value in (args.get("fields") or {}).items():
        if key not in obj:
            obj[key] = value

    if MUTANT == "lossy-locale":
        # THE CLASSIC ONE. Text is round-tripped through the machine's own codepage on the way to
        # disk, because that is what "just write it out" does when nobody says otherwise. cp1252 has
        # an e-acute, does not have a CJK character, and has never held an emoji. Everything here is
        # returned as a successful write.
        obj["observations"] = [o.encode("cp1252", "replace").decode("cp1252")
                               if isinstance(o, str) else o for o in obj["observations"]]
    if MUTANT == "truncate-large":
        obj["observations"] = [o[:1000] if isinstance(o, str) else o
                               for o in obj["observations"]]
    if MUTANT == "no-persist":
        # The write is acknowledged and never happens. This is the failure every memory server is
        # one bug away from, and the one the caller cannot detect from the answer alone.
        return {"ok": True, "seq": 0, "bytes": 0, "line": "", "readback_verified": True}
    if MUTANT == "stale-cache":
        # Read once at startup, rewrite from that copy forever. One process is indistinguishable from
        # correct; two processes on one store each overwrite the other's writes.
        if _CACHE is None:
            _CACHE = list(_records()[0])
        _CACHE.append(obj)
        return {"ok": True, "seq": _rewrite(_CACHE), "bytes": 0, "line": "",
                "readback_verified": True}

    line, size, verified = _append_line(obj)
    if MUTANT == "keep-last":
        # Only the newest record survives a write. A single write is unaffected, which is exactly why
        # ack_readback still passes it and restart does not.
        _rewrite([obj])
    elif MUTANT == "reshape-modelled":
        # The reference implementation's actual defect, confined to the field axis: a record this
        # server would have written is re-serialised from its own model, so anything attached to it
        # by another tool is dropped - while a record it would never have written is passed through
        # untouched, which is why this one fails foreign_field and leaves foreign_record passing.
        KEEP = ("name", "entityType", "observations")

        def remodel(rows):
            out = []
            for row in rows:
                if isinstance(row, dict) and row.get("name"):
                    out.append(dict((k, row[k]) for k in KEEP if k in row))
                else:
                    out.append(row)
            return out

        _remodel(remodel)
    elif MUTANT == "drop-unnamed":
        # Everything this server would have written, it keeps; everything else it silently discards -
        # including the fields it does not model, on the records it does.
        _remodel(lambda rows: [o for o in rows if isinstance(o, dict) and o.get("name")])
    _leak_append(obj)
    seq = len(_records()[0])
    return {"ok": verified, "seq": seq, "bytes": size, "line": line,
            "readback_verified": verified}


def _live():
    """The records a reader should see: everything except tombstones and what they name."""
    ents, corrupt = _records()
    ents = ents + _leak_records()
    dead = {e.get("tombstone") for e in ents if "tombstone" in e}
    return [e for e in ents if "tombstone" not in e and e.get("name") not in dead], corrupt


def tool_forget(args):
    """FORGETTING IS AN APPEND TOO. This store never rewrites, so a deletion is a tombstone line: the
    bytes that were written stay written, a reader after a restart sees the record gone, and nothing
    that was acknowledged is ever destroyed - including the evidence that it existed."""
    name = args.get("name")
    if MUTANT == "no-forget":
        # Acknowledged, and the record stays exactly where it was.
        return {"ok": True, "forgotten": name, "bytes": 0}
    if MUTANT == "forget-all":
        # The over-forgetting direction, which looks identical from the caller's side. The probe has
        # to notice that the records nobody asked about went too, or this passes as a clean delete.
        doomed = [e.get("name") for e in _live()[0] if e.get("name")]
    else:
        doomed = [name]
    size = 0
    verified = True
    for victim in doomed:
        _line, size, verified = _append_line({"tombstone": victim})
        _leak_append({"tombstone": victim})
    return {"ok": verified, "forgotten": name, "bytes": size}


def tool_read(args):
    ents, _corrupt = _live()
    return {"entities": ents, "count": len(ents)}


def tool_verify(args):
    ents, corrupt = _records()
    with open(STORE, "rb") as fh:
        body = fh.read()
    lines = [l for l in body.decode("utf-8", "replace").split(chr(10)) if l.strip()]
    parsed = 0
    for raw in lines:
        try:
            json.loads(raw)
            parsed += 1
        except ValueError:
            pass
    return {"records": len(ents), "parsed_lines": parsed, "corrupt_lines": corrupt,
            "bytes": len(body), "path": STORE, "intact": parsed == len(lines)}


TOOLS = {
    "memory_write": (tool_write, {"type": "object", "properties": {
        "name": {"type": "string"}, "observations": {"type": "array", "items": {"type": "string"}},
        "entityType": {"type": "string"}, "fields": {"type": "object"}},
        "required": ["name"]}),
    "memory_forget": (tool_forget, {"type": "object", "properties": {
        "name": {"type": "string"}}, "required": ["name"]}),
    "memory_read": (tool_read, {"type": "object", "properties": {}}),
    "memory_verify": (tool_verify, {"type": "object", "properties": {}}),
}


def reply(msg_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + chr(10))
    sys.stdout.flush()


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        reply(mid, {"protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "conformance-control", "version": "0.1"}})
        return
    if method == "tools/list":
        reply(mid, {"tools": [{"name": n, "description": n, "inputSchema": schema}
                              for n, (_fn, schema) in TOOLS.items()]})
        return
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = (TOOLS.get(name) or (None, None))[0]
        if fn is None:
            reply(mid, {"content": [{"type": "text", "text": "no such tool: %s" % name}],
                        "isError": True})
            return
        try:
            result = fn(args)
        except Exception as exc:
            reply(mid, {"content": [{"type": "text", "text": "error: %s" % exc}], "isError": True})
            return
        reply(mid, {"content": [{"type": "text", "text": json.dumps(result)}], "isError": False})
        return
    if mid is not None:
        reply(mid, {})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        handle(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
