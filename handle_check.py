import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import McpServer

srv = McpServer(sys.argv[1], tempfile.mkdtemp(prefix="handle-")).start()
try:
    res = srv.call("store_memory", {"content": "HANDLE-TOKEN-9 an observation",
                                     "tags": ["probe"]}, timeout=120)
    print("store_memory ->", res[:400])
    print()
    for tool, args in (("memory_stats", {}),
                       ("search_memories", {"query": "HANDLE-TOKEN-9"}),
                       ("recall", {"query": "HANDLE-TOKEN-9"})):
        try:
            out = srv.call(tool, args, timeout=120)
            hit = "HANDLE-TOKEN-9" in out
            print("%-16s hit=%-5s len=%-5d %s" % (tool, hit, len(out), out[:160].replace(chr(10), " ")))
        except Exception as exc:
            print("%-16s ERROR %s" % (tool, str(exc)[:90]))
finally:
    srv.proc.kill()
