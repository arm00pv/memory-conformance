"""List the tools a given MCP server exposes, over its own stdio transport."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import McpServer  # noqa: E402


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: discover.py <server command...>")
    cmd = " ".join(sys.argv[1:])
    store = tempfile.mkdtemp(prefix="disc-")
    print("cmd  :", cmd)
    print("store:", store)
    srv = McpServer(cmd, store).start()
    try:
        res = srv.request("tools/list", {})
        tools = res.get("tools") or []
        print("tools:", len(tools))
        for t in tools:
            schema = t.get("inputSchema") or {}
            props = list((schema.get("properties") or {}).keys())
            req = schema.get("required") or []
            print("  %-28s req=%-28s props=%s" % (
                t.get("name"), ",".join(req)[:28], ",".join(props)[:60]))
        print("files created:")
        for root, _dirs, files in os.walk(store):
            for f in files:
                p = os.path.join(root, f)
                print("   ", os.path.relpath(p, store), os.path.getsize(p), "bytes")
    finally:
        try:
            srv.proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    main()
