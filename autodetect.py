"""Propose and then VERIFY a write/read binding for an arbitrary MCP server.

A hand-written adapter per subject does not scale to a leaderboard. This classifies the tools a
server actually publishes, builds an argument mapping from each tool's own JSON schema, and then
proves the mapping by round-tripping a unique token - because a guess that is not tested is a
benchmark that lies.

usage: autodetect.py "<server command>"
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import McpServer  # noqa: E402

WRITE_HINTS = ("create", "store", "add", "write", "save", "remember", "insert", "put", "append")
READ_HINTS = ("read", "list", "dump", "retrieve", "load", "export", "fetch", "all", "nodes")
SEARCH_HINTS = ("search", "query", "find", "recall", "lookup", "match")
NAME_HINTS = ("name", "title", "key", "entity", "label")
CONTENT_HINTS = ("content", "text", "body", "value", "data", "memory", "message",
                 "observ", "description", "note")


def score(tool_name, hints):
    low = tool_name.lower()
    return sum(1 for h in hints if h in low)


def schema_of(tool):
    return tool.get("inputSchema") or {}


def props_of(tool):
    return schema_of(tool).get("properties") or {}


def required_of(tool):
    return schema_of(tool).get("required") or []


def pick_write(tools):
    scored = [(score(t["name"], WRITE_HINTS), t) for t in tools]
    scored = [(s, t) for s, t in scored if s > 0]
    if not scored:
        return None
    # prefer the one that can carry the most content: an array/observation field beats a bare string
    def richness(t):
        p = props_of(t)
        r = 0
        for spec in p.values():
            if spec.get("type") == "array":
                r += 3
        return r
    scored.sort(key=lambda st: (richness(st[1]), st[0]), reverse=True)
    return scored[0][1]


def read_candidates(tools, exclude):
    """Every plausible read tool, best first.

    A single guess is not enough: "recall" matches the substring "all" and then rejects an empty
    query, so the first candidate can be wrong while a perfectly good reader sits next to it. The
    caller tries them in order and keeps the first that actually returns the token.
    """
    cands = []
    for t in tools:
        if t is exclude:
            continue
        s = score(t["name"], READ_HINTS)
        # a tool that needs no arguments can plausibly list everything, even if its name gives
        # nothing away (memory_stats, get_status, list_memories)
        bonus = 2 if not required_of(t) else 0
        if s + bonus == 0:
            continue
        cands.append((s + bonus, t))
    cands.sort(key=lambda st: st[0], reverse=True)
    return [t for _s, t in cands]


def pick_read(tools, exclude):
    c = read_candidates(tools, exclude)
    return c[0] if c else None


def search_candidates(tools, exclude):
    cands = [(score(t["name"], SEARCH_HINTS), t) for t in tools
             if score(t["name"], SEARCH_HINTS) > 0 and t is not exclude]
    cands.sort(key=lambda st: st[0], reverse=True)
    return [t for _s, t in cands]


def pick_search(tools, exclude):
    c = search_candidates(tools, exclude)
    return c[0] if c else None


def build_search_args(tool, query):
    """Fill a search tool's required arguments with the query itself.

    Many memory servers have no "list everything" tool at all - only search. A search for the token
    is then the only honest way to ask "did you keep it?", so it belongs in the reader fallback.
    """
    args = {}
    props = props_of(tool)
    for key in (required_of(tool) or list(props)):
        spec = props.get(key) or {}
        t = spec.get("type")
        if t == "integer" or t == "number":
            args[key] = 10
        elif t == "boolean":
            args[key] = False
        elif t == "array":
            args[key] = []
        elif t == "object":
            args[key] = {}
        else:
            args[key] = query
    return args


def build_write_args(tool, name, observations):
    """Bind (name, observations) onto the tool's own schema.

    If the tool has a field that looks like an identifier, the name goes there. If it does not,
    the name is embedded in the content string - otherwise the token could never be found on the
    way back and a correct server would score as a loss.

    THE SEPARATOR IS A SPACE, NOT A COLON. Subjects tokenise content before indexing it; a colon
    splits "detect-token-1:" into pieces, so an exact-token search misses and a server that stored
    the record perfectly is scored as having lost it. A space keeps the token whole.
    """
    props = props_of(tool)
    req = required_of(tool)

    # nested: entities: [ { name, entityType, observations } ]
    for key, spec in props.items():
        if spec.get("type") != "array":
            continue
        item = spec.get("items") or {}
        item_props = item.get("properties") or {}
        if not item_props:
            continue
        obj = {}
        has_name = False
        for pn, ps in item_props.items():
            lp = pn.lower()
            if "type" in lp:
                # entityType is a category, not an identifier - it must not swallow the token
                obj[pn] = "probe"
            elif any(h in lp for h in NAME_HINTS):
                obj[pn] = name
                has_name = True
            elif ps.get("type") == "array":
                obj[pn] = list(observations)
            elif any(h in lp for h in CONTENT_HINTS):
                obj[pn] = observations[0] if observations else ""
            elif ps.get("type") == "string":
                obj[pn] = "probe"
        if not has_name:
            for pn, ps in item_props.items():
                if ps.get("type") == "array" and obj.get(pn):
                    obj[pn] = [name + " " + str(x) for x in obj[pn]]
                    break
        return {key: [obj]}

    # flat
    args = {}
    name_slot = None
    content_slot = None
    keys = req or list(props)
    for key in keys:
        spec = props.get(key) or {}
        t = spec.get("type")
        lk = key.lower()
        if t == "array":
            if "tag" in lk or "label" in lk or "categor" in lk:
                # A TAG IS A LABEL, NOT CONTENT. memdb rejects a tag containing spaces and the
                # write fails while the caller is told nothing, so stuffing the record body into
                # tags turns a good server into a false negative.
                args[key] = ["probe"]
            else:
                args[key] = [name + " " + str(x) for x in observations] if observations else [name]
                content_slot = key
        elif any(h in lk for h in NAME_HINTS):
            args[key] = name
            name_slot = key
        elif any(h in lk for h in CONTENT_HINTS):
            args[key] = name + " " + " ".join(observations)
            content_slot = key
        elif t == "integer" or t == "number":
            args[key] = 1
        elif t == "boolean":
            args[key] = True
        else:
            args[key] = name
            if name_slot is None:
                name_slot = key
    if name_slot is None and content_slot is None:
        return None
    return args


def build_read_args(tool):
    args = {}
    for key in required_of(tool):
        spec = props_of(tool).get(key) or {}
        args[key] = 100 if spec.get("type") in ("integer", "number") else ""
    return args


def main():
    cmd = sys.argv[1]
    store = tempfile.mkdtemp(prefix="auto-")
    srv = McpServer(cmd, store).start()
    try:
        tools = srv.request("tools/list", {}).get("tools") or []
        print("tools:", len(tools))
        w = pick_write(tools)
        r = pick_read(tools, w)
        s = pick_search(tools, w)
        print("write candidate :", w["name"] if w else None)
        print("read candidate  :", r["name"] if r else None)
        print("search candidate:", s["name"] if s else None)
        if not w:
            print("VERDICT: no usable write tool")
            return

        # TRY EVERY READER, KEEP THE FIRST THAT PROVES ITSELF. A candidate list ranked by name is a
        # hypothesis; only a token that comes back is evidence.
        for i, r in enumerate(read_candidates(tools, w)):
            token = "autodetect-token-%d" % (i + 1)
            args = build_write_args(w, token, ["an observation"])
            if args is None:
                print("VERDICT: write schema could not carry a token")
                return
            if i == 0:
                print("write args      :", json.dumps(args)[:160])
            try:
                srv.call(w["name"], args, timeout=120)
                got = srv.call(r["name"], build_read_args(r), timeout=120)
            except Exception as exc:
                print("  reader %-22s rejected: %s" % (r["name"], str(exc)[:70]))
                continue
            if token in got:
                print("read chosen     :", r["name"])
                print("VERDICT         : ROUND-TRIP OK")
                print("read head       :", got[:180].replace(chr(10), " "))
                return
            print("  reader %-22s did not return the token" % r["name"])

        # FALLBACK: a search queried with the token is also a reader.
        for i, st in enumerate(search_candidates(tools, w)):
            token = "autodetect-search-%d" % (i + 1)
            args = build_write_args(w, token, ["an observation"])
            try:
                srv.call(w["name"], args, timeout=120)
                got = srv.call(st["name"], build_search_args(st, token), timeout=120)
            except Exception as exc:
                print("  search %-22s rejected: %s" % (st["name"], str(exc)[:70]))
                continue
            if token in got:
                print("read chosen     : %s (via search)" % st["name"])
                print("VERDICT         : ROUND-TRIP OK")
                print("read head       :", got[:180].replace(chr(10), " "))
                return
            print("  search %-22s did not return the token" % st["name"])
        print("VERDICT: no reader recovered the token")
    finally:
        try:
            srv.proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    main()
