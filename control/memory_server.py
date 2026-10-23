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
"""
import json
import os
import sys

STORE = os.environ.get("MEMORY_FILE_PATH") or os.path.join(os.getcwd(), "memory.json")


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
    # UNKNOWN FIELDS RIDE ALONG. A caller - or another tool - may attach anything; it is stored and
    # returned untouched, because this server has no model to lose it in.
    obj = {"name": args.get("name"), "entityType": args.get("entityType", "probe"),
           "observations": list(args.get("observations") or [])}
    for key, value in (args.get("fields") or {}).items():
        if key not in obj:
            obj[key] = value
    line, size, verified = _append_line(obj)
    seq = len(_records()[0])
    return {"ok": verified, "seq": seq, "bytes": size, "line": line,
            "readback_verified": verified}


def _live():
    """The records a reader should see: everything except tombstones and what they name."""
    ents, corrupt = _records()
    dead = {e.get("tombstone") for e in ents if "tombstone" in e}
    return [e for e in ents if "tombstone" not in e and e.get("name") not in dead], corrupt


def tool_forget(args):
    """FORGETTING IS AN APPEND TOO. This store never rewrites, so a deletion is a tombstone line: the
    bytes that were written stay written, a reader after a restart sees the record gone, and nothing
    that was acknowledged is ever destroyed - including the evidence that it existed."""
    name = args.get("name")
    line, size, verified = _append_line({"tombstone": name})
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
