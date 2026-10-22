"""Create a real store with one entity, then dump the SQLite schema and the row."""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import McpServer  # noqa: E402


def main():
    cmd = sys.argv[1]
    store = tempfile.mkdtemp(prefix="schema-")
    srv = McpServer(cmd, store).start()
    srv.call("create_entities", {"entities": [
        {"name": "keepme", "entityType": "probe", "observations": ["annotated"]}]}, timeout=180)
    srv.proc.kill()

    db = os.path.join(store, "memory.db")
    print("db:", db, os.path.getsize(db), "bytes")
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    for (name, sql) in con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"):
        try:
            n = con.execute("SELECT COUNT(*) FROM '%s'" % name).fetchone()[0]
        except Exception as exc:
            n = "err:%s" % exc
        print("\nTABLE %s  rows=%s" % (name, n))
        print((sql or "")[:300])
        try:
            for row in con.execute("SELECT * FROM '%s' LIMIT 2" % name):
                d = dict(row)
                print("   row:", {k: (str(v)[:60]) for k, v in list(d.items())[:8]})
        except Exception as exc:
            print("   (no sample)", exc)
    con.close()


if __name__ == "__main__":
    main()
