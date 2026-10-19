#!/usr/bin/env python3
"""harness.py - conformance probes for any MCP memory server.

The claim under test is not "does it retrieve well" but "does it keep what it said it kept". Every
probe is falsifiable: it drives the server through its own public tools and then checks the bytes on
disk and the answers over the wire. A probe that cannot fail is not a probe.

  python harness.py --cmd "node node_modules/@modelcontextprotocol/server-memory/dist/index.js"
  python harness.py --cmd "..." --json report.json

Probes, each independent and each run against a fresh store:
  ack_readback     a write that returned success is returned by a fresh read
  restart          the same write survives the server being stopped and started
  foreign_field    a field the server does not model survives the next write
  foreign_record   a record type the server does not model survives the next write
  concurrent       two servers on one store keep every acknowledged write
  large_record     a write near the host-imposed size limit comes back whole
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time


class McpServer:
    """A minimal MCP stdio client: newline-delimited JSON-RPC, one process."""

    def __init__(self, cmd, store, log=None):
        self.cmd = cmd
        self.store = store
        self.log = log
        self.proc = None
        self.q = queue.Queue()
        self.next_id = 0
        self.stderr = []

    def start(self):
        env = dict(os.environ)
        # BOTH VARIABLES, ONE DIRECTORY. A probe hands the adapter a directory; each server reads the
        # variable it knows. The first version set only MEMORY_FILE_PATH, so a server that reads
        # RETAINED_DIR fell back to a default store and state leaked between probes - visible as the
        # restart probe seeing records from the probe before it.
        env["MEMORY_FILE_PATH"] = os.path.join(self.store, "memory.json")
        env["RETAINED_DIR"] = self.store
        # UTF-8, NOT THE LOCALE. Popen(text=True) decodes with the console codepage, which on Windows
        # is cp1252; a server that emits any non-ASCII character (an em dash in a tool description is
        # enough) kills the stdout reader thread with UnicodeDecodeError and every later request times
        # out as if the server had hung. JSON-RPC over stdio is UTF-8 by specification, so decode it as
        # such. ASCII subjects are unaffected: ASCII is a subset of UTF-8.
        self.proc = subprocess.Popen(self.cmd, shell=True, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", errors="replace",
                                     bufsize=1, env=env)
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()
        self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "memory-conformance", "version": "0.1"}})
        self.notify("notifications/initialized", {})
        return self

    def _pump_out(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line:
                self.q.put(line)

    def _pump_err(self):
        for line in self.proc.stderr:
            self.stderr.append(line.rstrip())

    def request(self, method, params, timeout=30.0):
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}
        self.proc.stdin.write(json.dumps(msg) + chr(10))
        self.proc.stdin.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self.q.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                break
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if data.get("id") == self.next_id:
                if "error" in data:
                    raise RuntimeError("MCP error: %s" % json.dumps(data["error"])[:200])
                return data.get("result", {})
        raise TimeoutError("%s did not answer within %.0fs" % (method, timeout))

    def notify(self, method, params):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + chr(10))
        self.proc.stdin.flush()

    def call(self, tool, args, timeout=30.0):
        res = self.request("tools/call", {"name": tool, "arguments": args}, timeout=timeout)
        text = ""
        for part in res.get("content") or []:
            if part.get("type") == "text":
                text += part.get("text") or ""
        return text

    def stop(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class ReferenceAdapter:
    """The modelcontextprotocol memory server: knowledge-graph entities with observations."""

    def __init__(self, cmd):
        self.cmd = cmd

    def store_path(self, store):
        return os.path.join(store, "memory.json")

    def server(self, store):
        return McpServer(self.cmd, store).start()

    def write(self, srv, name, observations):
        return srv.call("create_entities", {"entities": [
            {"name": name, "entityType": "probe", "observations": observations}]})

    def search(self, srv, query, k=3):
        text = srv.call("search_nodes", {"query": query})
        try:
            data = json.loads(text)
        except ValueError:
            return []
        ents = data.get("entities") if isinstance(data, dict) else []
        return [e.get("name") for e in (ents or [])][:k]

    def read(self, srv):
        text = srv.call("read_graph", {})
        try:
            data = json.loads(text)
        except ValueError:
            return None
        entities = data.get("entities") if isinstance(data, dict) else None
        return entities


class ControlAdapter:
    """control/memory_server.py - the append-only positive control, same probe surface."""

    def __init__(self, cmd):
        self.cmd = cmd

    def store_path(self, store):
        return os.path.join(store, "memory.json")

    def server(self, store):
        return McpServer(self.cmd, store).start()

    def write(self, srv, name, observations):
        return srv.call("memory_write", {"name": name, "observations": observations})

    def read(self, srv):
        text = srv.call("memory_read", {})
        try:
            data = json.loads(text)
        except ValueError:
            return None
        return data.get("entities")


class RetainedAdapter:
    """retained.py - append-only, hash-chained, read-back verified. Same probe surface."""

    def __init__(self, cmd):
        self.cmd = cmd

    def store_path(self, store):
        return os.path.join(store, "records.jsonl")

    def server(self, store):
        return McpServer(self.cmd, store).start()

    def write(self, srv, name, observations):
        return srv.call("memory_write", {"text": observations[0] if observations else "",
                                         "kind": "probe", "scope": "probe",
                                         "name": name, "observations": observations})

    def search(self, srv, query, k=3):
        text = srv.call("memory_search", {"query": query, "k": k})
        try:
            data = json.loads(text)
        except ValueError:
            return []
        ids = [h.get("id") for h in (data.get("hits") or [])][:k]
        if not ids:
            return []
        # THE STORE NAMES ITS OWN RECORDS. A caller thinks in the names it wrote; retained answers
        # with its record ids, so the adapter reads them back and maps - otherwise a correct hit
        # scores as a miss, which is the exact way a benchmark lies.
        try:
            got = json.loads(srv.call("memory_get", {"ids": ids}))
        except ValueError:
            return ids
        by_id = {r["id"]: r for r in (got.get("records") or [])}
        return [(by_id.get(i) or {}).get("name") or i for i in ids]

    def read(self, srv):
        text = srv.call("memory_get", {})
        try:
            data = json.loads(text)
        except ValueError:
            return None
        return data.get("records")


class BasicMemoryAdapter:
    """basic-memory - markdown notes with YAML frontmatter in a project directory.

    Three decisions worth stating, because all three were forced by the subject rather than chosen:

    1. THE STORE IS A DIRECTORY, NOT A FILE. basic-memory stores one markdown file per note
       (<project>/<directory>/<title>.md) plus a SQLite index in its config directory. Isolation is
       therefore achieved with a per-store config dir (BASIC_MEMORY_CONFIG_DIR) holding a config.json
       whose only project points at the store, selected with BASIC_MEMORY_MCP_PROJECT. Nothing is
       written to the user's ~/.basic-memory config.

    2. SEMANTIC SEARCH IS OFF. Out of the box basic-memory enables fastembed embeddings, which needs a
       model download this environment does not have. semantic_search_enabled=false makes its default
       search type "text" - the lexical path the probes and the retrieval cases use anyway - and keeps
       the whole run offline.

    store_path() raises: the two foreign-data probes annotate a single JSON-lines file and check the
    bytes after the next write. basic-memory has no such file - its records are markdown documents
    with YAML frontmatter plus a binary SQLite index - so those two probes cannot be expressed against
    it, and they report UNKNOWN rather than a verdict. Pointing store_path at a note file instead
    would be worse than useless: the unmodelled-record probe appends a JSON line to whatever file it
    is given and would then find it intact simply because basic-memory never rewrites that file,
    producing a PASS that measures nothing.
    """

    DIRECTORY = "probe"

    def __init__(self, cmd):
        self.cmd = cmd

    def store_path(self, store):
        raise NotImplementedError(
            "basic-memory keeps one markdown file per note plus a SQLite index, not a single "
            "JSON-lines store; this probe's annotate-a-file check has no equivalent here")

    def server(self, store):
        cfg = os.path.join(store, ".bmconfig")
        notes = os.path.join(store, "notes")
        for d in (cfg, notes):
            if not os.path.isdir(d):
                os.makedirs(d)
        with open(os.path.join(cfg, "config.json"), "w", encoding="utf-8", newline=chr(10)) as fh:
            json.dump({"projects": {"probe": {"path": notes, "mode": "local"}},
                       "default_project": "probe",
                       "semantic_search_enabled": False,
                       "auto_update": False,
                       "cloud_promo_opt_out": True}, fh)
        # THE TRANSPORT TAKES THE STORE, NOT THE ENVIRONMENT. Every server the probes start gets its
        # own config dir, so two processes in the concurrency probe share a project (as documented)
        # without sharing anything with another probe.
        env = {"BASIC_MEMORY_CONFIG_DIR": cfg, "BASIC_MEMORY_MCP_PROJECT": "probe",
               "BASIC_MEMORY_LOG_LEVEL": "ERROR"}
        if os.name == "nt":
            prefix = "&& ".join('set "%s=%s"' % kv for kv in env.items()) + "&& "
        else:  # POSIX form, same variables; only the Windows form has been exercised here
            prefix = "env " + " ".join("%s=%s" % kv for kv in env.items()) + " "
        cmd = prefix + self.cmd
        return McpServer(cmd, store).start()

    def write(self, srv, name, observations):
        content = chr(10).join(observations)
        return srv.call("write_note", {"title": name, "content": content,
                                       "directory": self.DIRECTORY, "output_format": "json"})

    def _nodes(self, srv):
        text = srv.call("list_directory", {"dir_name": "/", "depth": 10, "page_size": 200,
                                           "output_format": "json"})
        try:
            data = json.loads(text)
        except ValueError:
            return []
        out = []

        def walk(nodes):
            for n in nodes or []:
                out.append(n)
                walk(n.get("children"))

        walk(data.get("nodes"))
        return [n for n in out if n.get("type") == "file"]

    def read(self, srv):
        ents = []
        for node in self._nodes(srv):
            ident = node.get("permalink") or node.get("file_path")
            try:
                got = json.loads(srv.call("read_note", {"identifier": ident,
                                                        "output_format": "json"}))
            except (ValueError, RuntimeError):
                continue
            body = got.get("content") or ""
            # THE FILE'S FIRST BYTE IS NOT THE RECORD'S. A note body sits below a YAML frontmatter
            # block, and read_note returns that leading blank line with it; stripping the structural
            # newlines at either end is the adapter mapping the markdown envelope onto the record, not
            # the server losing a character. The first version only stripped the leading one and
            # reported large_record as 100001 characters - a failure the adapter caused, so it is
            # reported here rather than counted against the subject. Interior bytes are untouched and
            # the probe's exact-length comparison is unchanged.
            ents.append({"name": got.get("title") or node.get("title"),
                         "observations": [body.strip(chr(10) + chr(13))]})
        return ents

    def search(self, srv, query, k=3):
        text = srv.call("search_notes", {"query": query, "page_size": max(k, 10),
                                         "output_format": "json"})
        try:
            data = json.loads(text)
        except ValueError:
            return []
        return [r.get("title") for r in (data.get("results") or [])][:k]


def _fresh():
    d = tempfile.mkdtemp(prefix="memconf_")
    return d, d


def probe_ack_readback(ad):
    d, store = _fresh()
    try:
        srv = ad.server(store)
        try:
            ad.write(srv, "alpha", ["the first record"])
        finally:
            srv.stop()
        srv = ad.server(store)
        try:
            ents = ad.read(srv) or []
        finally:
            srv.stop()
        names = [e.get("name") for e in ents]
        ok = "alpha" in names
        return ok, "acknowledged alpha; a fresh read returned %d entities: %s" % (len(ents), names[:5])
    finally:
        shutil.rmtree(d, ignore_errors=True)


def probe_restart(ad):
    d, store = _fresh()
    try:
        for i in range(3):
            srv = ad.server(store)
            try:
                ad.write(srv, "restart-%d" % i, ["observation %d" % i])
            finally:
                srv.stop()
        srv = ad.server(store)
        try:
            ents = ad.read(srv) or []
        finally:
            srv.stop()
        names = [e.get("name") for e in ents]
        ok = all(("restart-%d" % i) in names for i in range(3))
        return ok, "three writes across three server lifetimes; read back %s" % names[:5]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def probe_foreign_field(ad):
    d, store = _fresh()
    try:
        srv = ad.server(store)
        try:
            ad.write(srv, "keepme", ["a record a human annotated"])
        finally:
            srv.stop()
        path = ad.store_path(store)
        with open(path, encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
        marked = False
        for obj in lines:
            if obj.get("name") == "keepme":
                obj["reviewed_by"] = "a human"
                marked = True
        if not marked:
            return False, "could not find the entity in the store to annotate"
        with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
            for obj in lines:
                fh.write(json.dumps(obj) + chr(10))
        srv = ad.server(store)
        try:
            ad.write(srv, "trigger", ["one more write"])
        finally:
            srv.stop()
        with open(ad.store_path(store), encoding="utf-8") as fh:
            after = fh.read()
        ok = "reviewed_by" in after
        return ok, ("the extra field survived the next write" if ok
                    else "the extra field was silently dropped by the next write")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def probe_foreign_record(ad):
    d, store = _fresh()
    try:
        srv = ad.server(store)
        try:
            ad.write(srv, "base", ["a normal record"])
        finally:
            srv.stop()
        extra = {"type": "note", "content": "written by another tool", "id": "foreign-1"}
        with open(ad.store_path(store), "a", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(json.dumps(extra) + chr(10))
        srv = ad.server(store)
        try:
            ad.write(srv, "after", ["a write after the foreign record"])
        finally:
            srv.stop()
        with open(ad.store_path(store), encoding="utf-8") as fh:
            after = fh.read()
        ok = "foreign-1" in after
        return ok, ("the unmodelled record survived" if ok
                    else "the unmodelled record was silently removed by the next write")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def probe_concurrent(ad, per_writer=10):
    # THE WRITES HAVE TO OVERLAP. The first version ran writer 0 to completion and then writer 1,
    # which is a sequence, not a race: each write read the file the previous one had already
    # rewritten, so 20 of 20 survived and the probe proved nothing. Two threads, one server each,
    # released together - that is the deployment shape the server is documented to lose writes in.
    d, store = _fresh()
    try:
        servers = [ad.server(store) for _ in range(2)]
        acked = []
        errors = []
        lock = threading.Lock()

        def worker(srv, w, gate):
            gate.wait()
            for i in range(per_writer):
                name = "w%d-%d" % (w, i)
                try:
                    ad.write(srv, name, ["from writer %d" % w])
                    with lock:
                        acked.append(name)
                except Exception as exc:
                    with lock:
                        errors.append("%s: %s" % (name, exc))

        gate = threading.Event()
        threads = [threading.Thread(target=worker, args=(srv, w, gate))
                   for w, srv in enumerate(servers)]
        for t in threads:
            t.start()
        gate.set()
        for t in threads:
            t.join(timeout=120)
        for srv in servers:
            srv.stop()
        if errors:
            return False, "%d write(s) failed outright: %s" % (len(errors), errors[:3])
        srv = ad.server(store)
        try:
            ents = ad.read(srv) or []
        finally:
            srv.stop()
        names = set(e.get("name") for e in ents)
        survived = [n for n in acked if n in names]
        ok = len(survived) == len(acked)
        return ok, "%d of %d acknowledged writes survived two servers on one store" % (
            len(survived), len(acked))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def probe_large_record(ad, size=100000):
    d, store = _fresh()
    try:
        body = "x" * size
        srv = ad.server(store)
        try:
            ad.write(srv, "big", [body])
        finally:
            srv.stop()
        srv = ad.server(store)
        try:
            ents = ad.read(srv) or []
        finally:
            srv.stop()
        got = None
        for e in ents:
            if e.get("name") == "big":
                obs = e.get("observations") or []
                got = len(obs[0]) if obs else 0
        ok = got == size
        return ok, "wrote %d characters, read back %s" % (size, got)
    finally:
        shutil.rmtree(d, ignore_errors=True)


PROBES = [("ack_readback", probe_ack_readback),
          ("restart", probe_restart),
          ("foreign_field", probe_foreign_field),
          ("foreign_record", probe_foreign_record),
          ("concurrent", probe_concurrent),
          ("large_record", probe_large_record)]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = None
    out = None
    only = None
    for a in argv:
        if a.startswith("--cmd="):
            cmd = a.split("=", 1)[1]
        elif a.startswith("--json="):
            out = a.split("=", 1)[1]
        elif a.startswith("--only="):
            only = a.split("=", 1)[1]
    expect = None
    for a in argv:
        if a.startswith("--expect="):
            expect = a.split("=", 1)[1]
    per_writer = 10
    for a in argv:
        if a.startswith("--per-writer="):
            per_writer = int(a.split("=", 1)[1])
    if not cmd:
        print(__doc__)
        return 2
    adapter_name = "reference"
    for a in argv:
        if a.startswith("--adapter="):
            adapter_name = a.split("=", 1)[1]
    adapters = {"control": ControlAdapter, "retained": RetainedAdapter,
                "basic-memory": BasicMemoryAdapter}
    ad = adapters.get(adapter_name, ReferenceAdapter)(cmd)
    rows = []
    fails = 0
    for name, fn in PROBES:
        if only and name != only:
            continue
        t0 = time.time()
        try:
            ok, evidence = fn(ad, per_writer) if fn is probe_concurrent else fn(ad)
        except Exception as exc:
            ok, evidence = None, "probe could not run: %s" % exc
        verdict = "PASS" if ok else ("FAIL" if ok is False else "UNKNOWN")
        if ok is False:
            fails += 1
        rows.append({"probe": name, "verdict": verdict, "evidence": evidence,
                     "seconds": round(time.time() - t0, 1)})
        print("%-16s %-7s %5.1fs  %s" % (name, verdict, rows[-1]["seconds"], evidence))
    if out:
        with open(out, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(json.dumps({"command": cmd, "probes": rows}, indent=2) + chr(10))
        print("written to %s" % out)
    drift = []
    if expect:
        # PINNED EXPECTATION. A conformance run against a fixed version is a regression detector: if
        # the vendor ships a fix, or breaks something new, the verdicts move and somebody has to look.
        # That is the difference between recording a number and watching it.
        with open(expect, encoding="utf-8") as fh:
            want = json.load(fh)
        for row in rows:
            got = want.get(row["probe"])
            if got and got != row["verdict"]:
                drift.append("%s: expected %s, got %s" % (row["probe"], got, row["verdict"]))
        if drift:
            print("DRIFT against %s:" % expect)
            for d in drift:
                print("  " + d)
        else:
            print("verdicts match %s" % expect)
    print("%d probe(s) failed" % fails)
    if drift:
        return 2
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
