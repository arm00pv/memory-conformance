"""Time each MCP operation for a subject so a timeout can be attributed."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import McpServer  # noqa: E402


def timed(label, fn):
    t0 = time.time()
    try:
        res = fn()
        dt = time.time() - t0
        print("  %-22s %6.2fs  ok" % (label, dt))
        return res
    except Exception as exc:
        dt = time.time() - t0
        print("  %-22s %6.2fs  FAILED: %s" % (label, dt, str(exc)[:120]))
        return None


def main():
    cmd = sys.argv[1]
    store = tempfile.mkdtemp(prefix="timing-")
    print("cmd:", cmd)
    t0 = time.time()
    srv = McpServer(cmd, store).start()
    print("  %-22s %6.2fs  started" % ("initialize", time.time() - t0))

    timed("tools/list", lambda: srv.request("tools/list", {}))
    timed("create_entities", lambda: srv.call("create_entities", {"entities": [
        {"name": "alpha", "entityType": "probe", "observations": ["first"]}]}, timeout=120))
    timed("add_observations", lambda: srv.call("add_observations", {"observations": [
        {"entityName": "alpha", "contents": ["second"]}]}, timeout=120))
    timed("read_graph", lambda: srv.call("read_graph", {}, timeout=120))
    timed("search_nodes", lambda: srv.call("search_nodes", {"query": "alpha"}, timeout=120))

    srv.proc.kill()
    t0 = time.time()
    srv2 = McpServer(cmd, store).start()
    print("  %-22s %6.2fs  restarted" % ("re-initialize", time.time() - t0))
    timed("read_graph (after restart)", lambda: srv2.call("read_graph", {}, timeout=120))
    srv2.proc.kill()
    print("store files:")
    for root, _d, files in os.walk(store):
        for f in files:
            p = os.path.join(root, f)
            print("   ", os.path.relpath(p, store), os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
