import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import McpServer

cmd = sys.argv[1]
cases = [
    ("plain",        {"content": "TOKENALPHA an observation", "tags": ["probe"]}),
    ("spaces-tag",   {"content": "TOKENBETA an observation", "tags": ["TOKENBETA an observation"]}),
    ("hyphen-token", {"content": "autodetect-search-1 an observation", "tags": ["probe"]}),
    ("hyphen-tag",   {"content": "TOKENGAMMA an observation", "tags": ["autodetect-search-1"]}),
]
srv = McpServer(cmd, tempfile.mkdtemp(prefix="tok-")).start()
try:
    for label, args in cases:
        try:
            w = srv.call("store_memory", args, timeout=120)
        except Exception as exc:
            print("%-14s WRITE FAILED %s" % (label, str(exc)[:110]))
            continue
        q = args["content"].split()[0]
        try:
            out = srv.call("search_memories", {"query": q}, timeout=120)
            print("%-14s query=%-22s hit=%-5s len=%d" % (label, q, str(q in out), len(out)))
        except Exception as exc:
            print("%-14s SEARCH FAILED %s" % (label, str(exc)[:110]))
finally:
    srv.proc.kill()
