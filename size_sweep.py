"""Find where a subject stops completing a write, rather than waiting for one timeout.

A timeout says "slower than N seconds". A sweep says WHERE it breaks and how fast it grows,
which is the difference between a complaint and a defect report.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import McpServer  # noqa: E402


def main():
    cmd = sys.argv[1]
    sizes = [int(x) for x in (sys.argv[2:] or ["100", "1000", "5000", "10000", "25000", "50000", "100000"])]
    ceiling = 150.0
    print("cmd:", cmd)
    print("%10s %10s %s" % ("chars", "seconds", "result"))
    for n in sizes:
        store = tempfile.mkdtemp(prefix="sweep-")
        t0 = time.time()
        try:
            srv = McpServer(cmd, store).start()
            try:
                srv.call("create_entities", {"entities": [
                    {"name": "big", "entityType": "probe", "observations": ["x" * n]}]},
                    timeout=ceiling)
                dt = time.time() - t0
                print("%10d %10.2f %s" % (n, dt, "ok"))
            finally:
                srv.proc.kill()
        except Exception as exc:
            dt = time.time() - t0
            print("%10d %10.2f %s" % (n, dt, "FAILED: " + str(exc)[:70]))
        finally:
            import shutil
            shutil.rmtree(store, ignore_errors=True)


if __name__ == "__main__":
    main()
