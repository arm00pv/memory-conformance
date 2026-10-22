#!/usr/bin/env python3
"""harness.py - conformance probes for any MCP memory server.

The claim under test is not "does it retrieve well" but "does it keep what it said it kept". Every
probe is falsifiable: it drives the server through its own public tools and then checks the bytes on
disk and the answers over the wire. A probe that cannot fail is not a probe.

  python harness.py --cmd "node node_modules/@modelcontextprotocol/server-memory/dist/index.js"
  python harness.py --cmd "..." --json report.json

Probes, each independent and each run against a fresh store:
  isolation        a record written into one store is not visible from another store
  ack_readback     a write that returned success is returned by a fresh read
  restart          the same write survives the server being stopped and started
  findable         a record can be found again by the name it was stored under
  foreign_field    a field the server does not model survives the next write
  foreign_record   a record type the server does not model survives the next write
  concurrent       two servers on one store keep every acknowledged write
  large_record     a write near the host-imposed size limit comes back whole

isolation runs first and is a precondition, not a feature: verdicts measured on a subject that
carries state between stores describe leaked state, so they are printed with a warning and must not
be published. A probe answers PASS, FAIL, or UNKNOWN, and UNKNOWN is a real answer - it means the
probe could not be expressed against this subject, which is not the same thing as a defect.

Subjects
  --adapter=reference   @modelcontextprotocol/server-memory         hand-bound
  --adapter=memento     @iachilles/memento                           hand-bound
  --adapter=control     control/memory_server.py                    hand-bound
  --adapter=retained    retained.py                                 hand-bound
  --adapter=basic-memory                                            hand-bound
  --adapter=auto        any server: the binding is discovered and proven
  --manifest=x.json     any server, with its store declared instead of coded

Options
  --only=NAME           run one probe
  --timeout=SECONDS     per-call ceiling; raise it for a slow subject rather than believing a timeout
  --json=PATH           write the full report
  --expect=PATH         compare verdicts against a pinned report and exit 2 on drift
  --repeat=N            run the repeat-prone probes N times (default 1)
  --repeat-probes=a,b   narrow which probes repeat (--repeat-probes=all by default, which is
                        every one: a probe not repeated is a probe whose stability is assumed)
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


PROBE_TIMEOUT = 30.0


class ToolRefused(RuntimeError):
    """A tool call that came back as a normal result while reporting that it did not do the work.

    MCP servers signal a rejected argument with isError:true on an ordinary result, not with a
    JSON-RPC error, so a client that only concatenates the content text records a refusal as an
    acknowledgement. memdb answers a 100,000-character record with "Too big: expected string to have
    <=100000 characters" and the first version of this client took that for a successful write.
    """


class McpServer:
    """A minimal MCP stdio client: newline-delimited JSON-RPC, one process."""

    def __init__(self, cmd, store, log=None, cwd=None):
        self.cmd = cmd
        self.store = store
        self.log = log
        # OPT-IN, because changing the working directory breaks a relative command
        # ("node node_modules/...") that resolved fine from the original one.
        self.cwd = cwd
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
        # SQLITE-BACKED SUBJECTS read their own variable. memento uses MEMORY_DB_PATH; without a
        # per-store path it falls back to a shared default database and state leaks between probes.
        env["MEMORY_DB_PATH"] = os.path.join(self.store, "memory.db")
        # UTF-8, NOT THE LOCALE. Popen(text=True) decodes with the console codepage, which on Windows
        # is cp1252; a server that emits any non-ASCII character (an em dash in a tool description is
        # enough) kills the stdout reader thread with UnicodeDecodeError and every later request times
        # out as if the server had hung. JSON-RPC over stdio is UTF-8 by specification, so decode it as
        # such. ASCII subjects are unaffected: ASCII is a subset of UTF-8.
        # CWD IS ISOLATION TOO. A subject with no store-path variable typically writes relative to
        # the working directory (memdb creates .memdb/ wherever it is started). Opt-in, because a
        # relative command resolves against the original cwd and would stop starting here.
        self.proc = subprocess.Popen(self.cmd, shell=True, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", errors="replace",
                                     bufsize=1, env=env, cwd=self.cwd)
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()
        # THE SAME CEILING GOVERNS STARTUP. initialize was left on the original fixed 30 s while every
        # other call honoured --timeout, so a slow subject was reported as "initialize did not answer"
        # even when the operator had explicitly raised the limit - the S3 defect, one layer down.
        self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "memory-conformance", "version": "0.1"}},
                     timeout=PROBE_TIMEOUT)
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

    def call(self, tool, args, timeout=None):
        # A SLOW SUBJECT IS STILL A VERDICT. memento's first write blocks for 13 s and its startup for
        # 3 s, so a fixed 30 s ceiling turns a working server into a row of UNKNOWNs. The ceiling is
        # therefore a parameter of the run, and whatever it is gets recorded with the result.
        if timeout is None:
            timeout = PROBE_TIMEOUT
        res = self.request("tools/call", {"name": tool, "arguments": args}, timeout=timeout)
        text = ""
        for part in res.get("content") or []:
            if part.get("type") == "text":
                text += part.get("text") or ""
        if res.get("isError"):
            raise ToolRefused("%s refused: %s" % (tool, " ".join(text.split())[:200]))
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

    def search_text(self, srv, query, k=3):
        """Everything the adapter had to fetch over the wire to answer one question.

        Bytes are the caller's cost and they are measurable exactly, unlike a token estimate. A
        search that answers with the whole store is not cheap merely because it is quick, and the
        only way to say so with a number is to count what came back.
        """
        return srv.call("search_nodes", {"query": query})

    def search(self, srv, query, k=3):
        text = self.search_text(srv, query, k)
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

    # --- out-of-band store edits -------------------------------------------------
    # The two store probes need to act as "another tool" writing to the same store. How that is done
    # depends on the backend, so it lives behind storeops.py and the probes stay backend-agnostic. An
    # adapter that cannot answer returns False and the probe reports UNKNOWN, never FAIL.
    store_kind = "jsonl"

    def _ops(self, store):
        import storeops
        return storeops.JsonlStore(self.store_path(store))

    def annotate_field(self, store, name, key, value):
        """Attach a field the server does not model to one record."""
        return self._ops(store).annotate_field(store, name, key, value)

    def field_survived(self, store, name, key):
        return self._ops(store).field_survived(store, name, key)

    def inject_foreign_record(self, store, record):
        return self._ops(store).inject_record(store, record)

    def foreign_record_survived(self, store, needle):
        return self._ops(store).record_survived(store, needle)


class MementoAdapter(ReferenceAdapter):
    """@iachilles/memento - the reference tool names over a SQLite store.

    The tool surface is identical to the reference server, so only the store differs. Schema:
    entities(id, name UNIQUE, entityType, ...) and observations(entity_id -> entities.id), plus
    sqlite-vec tables. A SQL store needs different out-of-band edits than a JSON Lines file, which
    is exactly why the probes ask the adapter instead of opening the file themselves - and why both
    backends now live in storeops.py instead of being written twice.
    """

    store_kind = "sqlite"

    def store_path(self, store):
        return os.path.join(store, "memory.db")

    def _ops(self, store):
        import storeops
        return storeops.SqliteStore(self.store_path(store), table="entities",
                                    match={"column": "name", "op": "eq"})


class AutoAdapter:
    """A subject with no hand-written adapter: the binding is discovered and then proven.

    Nothing is assumed about tool names. The adapter lists what the server publishes, proposes a
    write tool, then tries each plausible reader until one returns a token that was just written.
    A binding that has not been proven is never used.

    Store semantics are unknown by construction, so the two out-of-band probes report UNKNOWN
    rather than guessing at a schema this adapter has never seen.
    """

    store_kind = None

    @staticmethod
    def _absolutize(cmd):
        """Make a "node <relative path>" command survive a change of working directory."""
        parts = cmd.split()
        if len(parts) >= 2 and os.path.basename(parts[0]).split(".")[0] in ("node", "python",
                                                                           "python3", "npx"):
            p = parts[1]
            if not os.path.isabs(p) and not p.startswith("-"):
                parts[1] = os.path.abspath(p)
        return " ".join(parts)

    def __init__(self, cmd):
        self.cmd = self._absolutize(cmd)
        self.written = set()
        self._binding = None
        # what was actually sent under each name, so a later on-disk measurement compares against
        # the bytes that left here rather than against the bytes the probe asked for
        self._sent = {}

    # No declared store semantics: the out-of-band probes report UNKNOWN with a reason rather than
    # raising, so "we could not test this" stays distinguishable from "it failed".
    measures_content = False

    def store_path(self, store):
        return os.path.join(store, "store")

    def annotate_field(self, store, name, key, value):
        return False

    def field_survived(self, store, name, key):
        return False

    def inject_foreign_record(self, store, record):
        return False

    def foreign_record_survived(self, store, needle):
        return False

    def server(self, store):
        return McpServer(self.cmd, store, cwd=store).start()

    def reset(self):
        """Forget what was discovered, so the next pass discovers it again.

        A REPEAT THAT KEEPS THE BINDING IS NOT A REPEAT FOR THIS KIND OF SUBJECT. The one thing most
        likely to differ between two runs of a discovery-bound adapter is which of a server's several
        plausible search tools it ended up binding - and that choice was cached on the adapter
        instance, so three passes inside one run shared it and came out identical while separate runs
        differed. Measured on memory-mcp-1file: 4,838 response bytes on one invocation, 1,969 on
        another, and 1,766-1,974 across three passes that shared a binding. The instrument was
        repeating the experiment and holding the conclusion fixed.
        """
        self._binding = None
        self.written = set()
        self._sent = {}
        self._tools = []

    def _discover(self, srv):
        if self._binding is not None:
            return
        import autodetect as ad
        tools = srv.request("tools/list", {}).get("tools") or []
        self._tools = tools
        w = ad.pick_write(tools)
        if w is None:
            raise RuntimeError("no write tool among %d tools" % len(tools))
        for i, r in enumerate(ad.read_candidates(tools, w)):
            tok = "discovery-token-%d" % (i + 1)
            srv.call(w["name"], ad.build_write_args(w, tok, ["discovery"]), timeout=PROBE_TIMEOUT)
            try:
                got = srv.call(r["name"], ad.build_read_args(r), timeout=PROBE_TIMEOUT)
            except Exception:
                continue
            if tok in got:
                self._binding = (w, r, None)
                return
        for i, s in enumerate(ad.search_candidates(tools, w)):
            tok = "discovery-search-%d" % (i + 1)
            srv.call(w["name"], ad.build_write_args(w, tok, ["discovery"]), timeout=PROBE_TIMEOUT)
            try:
                got = srv.call(s["name"], ad.build_search_args(s, tok), timeout=PROBE_TIMEOUT)
            except Exception:
                continue
            if tok in got:
                self._binding = (w, None, s)
                return
        raise RuntimeError("no reader recovered the discovery token")

    def write(self, srv, name, observations):
        import autodetect as ad
        self._discover(srv)
        w, _r, _s = self._binding
        args = ad.build_write_args(w, name, observations)
        self.written.add(name)
        self._sent[name] = _longest_string(args)
        return srv.call(w["name"], args, timeout=PROBE_TIMEOUT)

    def search_text(self, srv, query, k=3):
        """The raw response from the subject's own search, or from its reader when it has none."""
        import autodetect as ad
        self._discover(srv)
        w, r, s = self._binding
        if s is None:
            cands = ad.search_candidates(getattr(self, "_tools", []), w)
            s = cands[0] if cands else None
        if s is None:
            raise NotImplementedError(
                "this subject publishes no search tool, so a query cannot be asked of it")
        return srv.call(s["name"], ad.build_search_args(s, query), timeout=PROBE_TIMEOUT)

    def search(self, srv, query, k=3):
        """Ask the subject's own search, and keep only names this adapter wrote.

        A discovery-bound adapter cannot know what shape a hit comes back in, so rank is taken from
        where the response mentions each name. That is an approximation of the subject's ordering,
        and it is stated rather than hidden - for a hit@3 floor it is enough, for a ranking study it
        would not be.
        """
        import autodetect as ad
        self._discover(srv)
        w, r, s = self._binding
        # A QUERY NEEDS A SEARCH TOOL, NOT A READER. The reader is bound first because five of the
        # probes only need "give me everything", and read_graph wins that race on every subject that
        # has it. Falling back to the reader here silently discarded the query, returned the whole
        # graph in file order, and reported memory-lean as unable to find five of its own records -
        # when its search_nodes answers "1 match" perfectly. Only a search tool can rank.
        if s is None:
            cands = ad.search_candidates(getattr(self, "_tools", []), w)
            s = cands[0] if cands else None
        if s is None:
            raise NotImplementedError(
                "this subject publishes no search tool, so a query cannot be asked of it")
        text = self.search_text(srv, query, k)
        hits = [(text.find(n), n) for n in self.written if n in text]
        hits = [(p, n) for p, n in hits if p >= 0]
        hits.sort()
        return [n for _p, n in hits][:k]

    def read(self, srv):
        import autodetect as ad
        self._discover(srv)
        _w, r, s = self._binding
        text = ""
        if r is not None:
            text = srv.call(r["name"], ad.build_read_args(r), timeout=PROBE_TIMEOUT)
        else:
            for n in sorted(self.written):
                try:
                    text += srv.call(s["name"], ad.build_search_args(s, n),
                                     timeout=PROBE_TIMEOUT)
                except Exception:
                    pass
        # only the names this adapter was asked to store; a discovery token still lives in the
        # store and must not be counted as a probe result
        return [{"name": n} for n in sorted(self.written) if n in text]


def _longest_string(value):
    """The longest string sent to a server in one call.

    Used only to compare against what is on disk later, and only for the size probe, where one
    argument dominates by five orders of magnitude.
    """
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return max([_longest_string(v) for v in value] or [0])
    if isinstance(value, dict):
        return max([_longest_string(v) for v in value.values()] or [0])
    return 0


class ManifestAdapter(AutoAdapter):
    """A discovery-bound subject whose store has been declared in a manifest file.

    Tool binding is identical to AutoAdapter - nothing is assumed about tool names - plus the one
    thing a manifest adds: where the bytes are. That turns the two store probes and the on-disk
    measurement from UNKNOWN into verdicts, without a hand-written adapter.

    The declaration is checked, never trusted. Every call resolves the declared path inside the
    run's own directory, and when the declaration does not hold - the file is not there, or no row
    matches the predicate - the probe reports UNKNOWN and quotes the path it looked at. That is the
    difference between "the subject dropped my field" and "I was reading the wrong file".
    """

    def __init__(self, cmd, manifest):
        AutoAdapter.__init__(self, cmd)
        self.manifest = manifest
        self.store_kind = manifest.spec.get("kind")
        # Names are proven over the wire; bodies are measured on disk. Never claim the wire proved a
        # body it never returned.
        self.measures_content = False
        self.store_reason = None

    def _ops_for(self, store):
        ops, reason = self.manifest.store_for(store)
        if ops is None:
            self.store_reason = reason
            raise LookupError(reason)
        return ops

    def _quiet(self, fn, store, *args):
        self.store_reason = None
        try:
            return fn(self._ops_for(store), store, *args)
        except LookupError:
            return False
        except Exception as exc:
            self.store_reason = "store edit failed: %s" % exc
            return False

    def store_path(self, store):
        self.store_reason = None
        return self.manifest.resolve(store) or os.path.join(store, "<declared store absent>")

    def annotate_field(self, store, name, key, value):
        return self._quiet(lambda ops, s, n, k, v: ops.annotate_field(s, n, k, v),
                           store, name, key, value)

    def field_survived(self, store, name, key):
        return self._quiet(lambda ops, s, n, k: ops.field_survived(s, n, k), store, name, key)

    def inject_foreign_record(self, store, record):
        return self._quiet(lambda ops, s, r: ops.inject_record(s, r), store, record)

    def foreign_record_survived(self, store, needle):
        return self._quiet(lambda ops, s, n: ops.record_survived(s, n), store, needle)

    def body_on_disk(self, store, name, body):
        """How much of the body sent under this name is still in the store, or None if unknowable.

        A subject is free to store the name and the body in one column; memdb does, and the column
        then holds name + " " + body. Comparing the column length against the raw body length would
        report a two-character loss that never happened, so the comparison is against what was
        actually sent.
        """
        self.store_reason = None
        try:
            got = self._ops_for(store).content_length(store, name)
        except LookupError:
            return None
        except Exception:
            return None
        sent = self._sent.get(name)
        if got is None or sent is None:
            return None
        if got >= sent:
            return len(body)
        return max(0, got - (sent - len(body)))


class ControlAdapter(ReferenceAdapter):
    """control/memory_server.py - the append-only positive control, same probe surface.

    Inherits ReferenceAdapter for the out-of-band store edits only: the control keeps JSON Lines too,
    so the two foreign-data probes have something to inspect. Without that inheritance it had no
    annotate_field, every store probe came back as a harness error, and a control that cannot answer
    is not a control - it is a subject with a good reputation.
    """

    def __init__(self, cmd):
        self.cmd = cmd

    def store_path(self, store):
        return os.path.join(store, "memory.json")

    def server(self, store):
        return McpServer(self.cmd, store).start()

    def write(self, srv, name, observations):
        return srv.call("memory_write", {"name": name, "observations": observations})

    # A control has to demonstrate correct behaviour, and "answer every question with something" is
    # not correct. Stopwords are dropped and a record has to match at least half of what is left,
    # which is what lets an unanswerable question come back empty instead of plausible.
    STOPWORDS = frozenset((
        "what is the a an of in on at to for does do how many much when which who why can could are "
        "be was were it its we our with and or by from that this there i you they them he she my your "
        "should would will shall may might must not no").split())

    def search_text(self, srv, query, k=3):
        """The control has no server-side search: it reads the whole store and filters locally, so
        the wire cost of one question is the entire store. Reported as measured, not excused."""
        return srv.call("memory_read", {})

    def search(self, srv, query, k=3):
        """Term overlap over the observations, which is all this control claims to do."""
        low = query.lower()
        for ch in "?!.,;:()[]'\"":
            low = low.replace(ch, " ")
        terms = [t for t in low.split() if t and t not in self.STOPWORDS]
        if not terms:
            return []
        need = max(1, (len(terms) + 1) // 2)
        ents = self.read(srv) or []
        scored = []
        for e in ents:
            body = " ".join(e.get("observations") or []).lower()
            n = sum(1 for t in terms if t in body)
            if n >= need:
                scored.append((-n, e.get("name")))
        scored.sort()
        return [nm for _s, nm in scored][:k]

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

    def search_text(self, srv, query, k=3):
        """Both calls count. The store answers with record ids, so the adapter pays for a search and
        then for the fetch that turns those ids into names - that second call is part of what it
        costs to answer one question and hiding it would flatter this adapter.
        """
        first = srv.call("memory_search", {"query": query, "k": k})
        try:
            data = json.loads(first)
        except ValueError:
            return first
        ids = [h.get("id") for h in (data.get("hits") or [])][:k]
        if not ids:
            return first
        try:
            return first + chr(10) + srv.call("memory_get", {"ids": ids})
        except Exception:
            return first

    def search(self, srv, query, k=3):
        text = self.search_text(srv, query, k)
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

    def search_text(self, srv, query, k=3):
        return srv.call("search_notes", {"query": query, "page_size": max(k, 10),
                                         "output_format": "json"})

    def search(self, srv, query, k=3):
        text = self.search_text(srv, query, k)
        try:
            data = json.loads(text)
        except ValueError:
            return []
        return [r.get("title") for r in (data.get("results") or [])][:k]


def _no_store(ad, what):
    """Why an out-of-band probe could not run, in words that do not leak an internal name.

    "store kind None could not be annotated" states a fact about this harness and tells the reader
    nothing. The actionable sentence is that no store was declared and how to declare one.
    """
    reason = getattr(ad, "store_reason", None)
    if reason:
        return reason
    if not getattr(ad, "store_kind", None):
        return ("no store is declared for this subject, so the probe had nothing to inspect; "
                "add a manifest (see manifests/) to make it answerable")
    return "the %s store could not %s" % (ad.store_kind, what)


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


# No word appears twice: a query for one name must identify one record.
NAMES = ["zephyr-quartz", "ember-lattice", "cobalt-thistle", "marlin-obsidian",
         "tundra-figment", "halcyon-basalt", "quiver-nectar", "plinth-zodiac"]


def probe_findable(ad, n=8, k=3):
    """Can the subject find a record by the handle it was given?

    RETENTION IS NOT RETRIEVAL, AND THIS IS THE FLOOR UNDER THAT DISTINCTION. Every other probe asks
    what the subject kept; nothing asked whether it can be reached again, so a system that stored
    every byte perfectly and answered no query would have scored every probe but this one. The question here is
    the weakest possible one - the handle the caller used, unchanged - because failing it is not a
    ranking disagreement, it is a memory that cannot be read back by name.

    The search runs on a server that never saw the writes, so a hit cannot come from anything cached
    in the process that wrote it.
    """
    searcher = getattr(ad, "search", None)
    if not callable(searcher):
        return None, ("this adapter exposes no search surface, so 'findable' cannot be asked of it; "
                      "that is a gap in the harness, not a defect in the subject")
    d, store = _fresh()
    try:
        # THE NAMES MUST NOT SHARE A TOKEN. The first version used findable-0 .. findable-7, which any
        # tokeniser splits into "findable" plus a digit; every record matched every query, only three
        # fit in the top three, and memdb was reported as unable to find any of its own records when
        # the probe had simply asked an ambiguous question. Eight disjoint word pairs instead.
        names = NAMES[:n]
        srv = ad.server(store)
        try:
            for i, nm in enumerate(names):
                ad.write(srv, nm, ["observation number %d about %s" % (i, nm)])
        finally:
            srv.stop()
        srv = ad.server(store)
        missed = []
        answers = []
        try:
            for nm in names:
                try:
                    got = searcher(srv, nm, k) or []
                except NotImplementedError as exc:
                    return None, str(exc)
                except Exception:
                    got = []
                answers.append(tuple(got))
                if nm not in got[:k]:
                    missed.append(nm)
            # THE SAME ANSWER TO EIGHT DIFFERENT QUESTIONS IS ITS OWN DEFECT, and naming it is more
            # useful than counting misses. Found on memento, whose search returns the first three
            # entities alphabetically for a matching name, a nonsense string and the empty query
            # alike - a search that does not search, wearing the shape of one.
            identical = len(answers) > 1 and len(set(answers)) == 1 and any(answers)
            silent = all(not a for a in answers)
        finally:
            srv.stop()
        if not missed:
            return True, ("all %d acknowledged records came back in the top %d for a search on their "
                          "own name" % (n, k))
        if silent:
            why = "every query returned nothing at all, whatever was asked"
        elif identical:
            why = ("every query returned the same %d records regardless of what was asked - the "
                   "search does not discriminate" % len(answers[0]))
        else:
            why = ""
        return False, ("%d of %d acknowledged records were not returned by a search for their own "
                       "name: %s%s" % (len(missed), n, missed[:4], ("; " + why) if why else ""))
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
        if not ad.annotate_field(store, "keepme", "reviewed_by", "a human"):
            return None, _no_store(ad, "be annotated out of band")
        srv = ad.server(store)
        try:
            ad.write(srv, "trigger", ["one more write"])
        finally:
            srv.stop()
        ok = ad.field_survived(store, "keepme", "reviewed_by")
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
        if not ad.inject_foreign_record(store, extra):
            return None, _no_store(ad, "accept a foreign record")
        srv = ad.server(store)
        try:
            ad.write(srv, "after", ["a write after the foreign record"])
        finally:
            srv.stop()
        ok = ad.foreign_record_survived(store, "foreign-1")
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


# A refusal that names a size is a declared limit, not a defect. A refusal that names anything else
# is a defect, and the probe reports UNKNOWN rather than pretending to have measured durability.
SIZE_WORDS = ("too big", "too long", "too large", "too many", "exceed", "maximum", "max ", "limit",
              "length", "size", "capacity", "overflow", "payload", "char", "byte", "kb", "mb")
# HOW FAR DOWN TO WALK. A subject may cap observations at 300 characters while another accepts a
# million; stopping at an eighth of the requested size would report the tighter one as a failure to
# store anything. Ten halvings reaches roughly 1/1000, which covers the ranges seen so far.
LADDER_FLOOR = 1024


def _write_body(ad, store, chars):
    srv = ad.server(store)
    try:
        ad.write(srv, "big", ["x" * chars])
    finally:
        srv.stop()


def probe_large_record(ad, size=100000):
    """A record near the subject's own limit comes back whole.

    THE LIMIT MOVES THE TEST, IT DOES NOT CANCEL IT. memdb refuses a 100,000-character record outright
    and says so, so the question "did this survive" can only be asked at a size the subject accepted -
    otherwise a documented limit is reported as data loss. The probe therefore halves the body until
    the subject takes it and reports the size it actually measured, which is the number a reader needs
    and the number a bare PASS would hide.
    """
    wire = getattr(ad, "measures_content", True)
    disk = callable(getattr(ad, "body_on_disk", None))
    if not wire and not disk:
        return None, "adapter cannot measure record content; probe not applicable"
    d, store = _fresh()
    try:
        n = size
        while True:
            try:
                _write_body(ad, store, n)
                break
            except Exception as exc:
                msg = " ".join(str(exc).split())
                # ONLY A REFUSAL THAT NAMES A SIZE IS A LIMIT. Anything else - a hang, a crash, a
                # refusal for some other reason - is a fact about the subject and is re-raised so the
                # run classifies it. Swallowing these into UNKNOWN was the last place where a subject
                # that simply does not answer was reported as "we could not measure it".
                if not any(w in msg.lower() for w in SIZE_WORDS):
                    raise
                if n <= size // LADDER_FLOOR:
                    return None, "refused even at %d characters: %s" % (n, msg[:150])
                n //= 2
        asked = "" if n == size else "; refused at %d by its own limit, so %d was measured" % (size, n)
        body = "x" * n
        got = None
        if wire:
            srv = ad.server(store)
            try:
                ents = ad.read(srv) or []
            finally:
                srv.stop()
            for e in ents:
                if e.get("name") == "big":
                    obs = e.get("observations") or []
                    got = len(obs[0]) if obs else 0
        if disk:
            kept = ad.body_on_disk(store, "big", body)
            if kept is None:
                if wire:
                    ok = got == n
                    return ok, "wrote %d characters, read back %s%s" % (n, got, asked)
                # nothing measured: the store could not confirm and this adapter never sees bodies
                return None, ("wrote %d characters%s, but the declared store held no measurable body"
                              % (n, asked))
            if wire and got != kept:
                return None, ("the store holds %d characters and the server returns %s; they disagree "
                              "about what was kept" % (kept, got))
            return kept == n, ("wrote %d characters; %d are still in the store%s%s"
                               % (n, kept, " and were read back" if wire else "", asked))
        ok = got == n
        return ok, "wrote %d characters, read back %s%s" % (n, got, asked)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def probe_isolation(ad):
    """Does a record written into one store show up in a different store?

    This runs FIRST and it exists because a verdict from a subject that leaks state is worthless
    even when it reads PASS. memory-mcp-1file returned one probe's record from the next probe's
    read, in a different temporary directory - so its PASSes describe leaked state, not stored
    state. A suite that cannot detect that is grading itself.
    """
    store_a, path_a = _fresh()
    store_b, path_b = _fresh()
    marker = "isolation-marker-alpha"
    try:
        srv = ad.server(path_a)
        try:
            ad.write(srv, marker, ["a marker that must never cross into another store"])
        finally:
            srv.stop()
        srv = ad.server(path_b)
        try:
            ents = ad.read(srv) or []
        finally:
            srv.stop()
        names = [e.get("name") for e in ents]
        if marker in names:
            return False, ("a record written into store A was visible from store B; "
                           "verdicts for this subject describe leaked state")
        return True, "store A's record was not visible from store B"
    finally:
        shutil.rmtree(store_a, ignore_errors=True)
        shutil.rmtree(store_b, ignore_errors=True)


PROBES = [("isolation", probe_isolation),
          ("ack_readback", probe_ack_readback),
          ("restart", probe_restart),
          ("findable", probe_findable),
          ("foreign_field", probe_foreign_field),
          ("foreign_record", probe_foreign_record),
          ("concurrent", probe_concurrent),
          ("large_record", probe_large_record)]


# FAIL sorts before UNKNOWN before PASS: a tie is broken toward the worse outcome, so an unstable
# subject is never rounded up.
WORSE = {"FAIL": 0, "UNKNOWN": 1, "PASS": 2}

# Kinds that change what a verdict means, and are therefore printed rather than left in the report.
NOTABLE_KINDS = {"no-ack", "refused", "subject-error", "harness-error", "mixed"}


def _run_probe(fn, ad, per_writer):
    """Run one probe and report both how it ended and why.

    THE THREE-STATE VERDICT IS RIGHT AND TOO COARSE ON ITS OWN. "The subject answered and the answer
    was wrong" and "the subject never answered" are both failures, but only one of them is a broken
    promise; the other is a subject that could not be driven at all. Collapsing them into UNKNOWN
    understated a real defect, and collapsing them into a bare FAIL overstated what had been shown.
    So the verdict stays one of three and every row also carries a machine-readable kind.
    """
    t0 = time.time()
    kind = "failed"
    try:
        ok, evidence = fn(ad, per_writer) if fn is probe_concurrent else fn(ad)
    except TimeoutError as exc:
        # the ceiling is part of the claim, and it is in the message on purpose
        ok, kind, evidence = False, "no-ack", str(exc)
    except ToolRefused as exc:
        ok, kind, evidence = False, "refused", str(exc)
    except RuntimeError as exc:
        # THE SUBJECT ANSWERED, AND THE ANSWER WAS AN ERROR. McpServer.request raises RuntimeError
        # for a JSON-RPC error response, which is the subject failing to serve a call the probe was
        # entitled to make. That is a defect, not a limitation of the probe - reporting UNKNOWN here
        # understated it, which is how mcp-knowledge-graph's refusal to tolerate a foreign record
        # first came out as "we could not test this".
        ok, kind, evidence = False, "subject-error", str(exc)
    except Exception as exc:
        ok, kind, evidence = None, "harness-error", "probe could not run: %s" % exc
    if ok is True:
        verdict, kind = "PASS", "kept"
    elif ok is False:
        verdict = "FAIL"
    else:
        verdict, kind = "UNKNOWN", ("not-applicable" if kind == "failed" else kind)
    return {"verdict": verdict, "kind": kind, "evidence": evidence,
            "seconds": round(time.time() - t0, 1)}


def _settle(runs):
    """One verdict from N attempts of the same probe on the same subject.

    A race does not have a verdict, it has a distribution. Reporting one coin flip as the verdict is
    how a flaky subject gets published as either clean or broken depending on the afternoon, so the
    verdict is the modal one, the evidence carries the tally, and any disagreement is recorded
    rather than averaged away. The single-run path returns exactly what it always did.
    """
    tally = {}
    for r in runs:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    best = sorted(tally.items(), key=lambda kv: (-kv[1], WORSE[kv[0]]))[0][0]
    chosen = [r for r in runs if r["verdict"] == best]
    kinds = set(r.get("kind") or "failed" for r in chosen)
    kind = kinds.pop() if len(kinds) == 1 else "mixed"
    evidence = "; ".join(sorted(set(r["evidence"] for r in chosen)))[:400]
    if len(tally) > 1:
        spread = ", ".join("%s %d" % (k, tally[k]) for k in sorted(tally, key=WORSE.get))
        evidence = "%s  [unstable: %s of %d runs]" % (evidence, spread, len(runs))
    return best, kind, evidence, tally


def main(argv=None):
    global PROBE_TIMEOUT
    argv = list(sys.argv[1:] if argv is None else argv)

    def opt(key, default=None):
        pref = "--" + key + "="
        for a in argv:
            if a.startswith(pref):
                return a.split("=", 1)[1]
        return default

    PROBE_TIMEOUT = float(opt("timeout", PROBE_TIMEOUT))
    cmd = opt("cmd")
    out = opt("json")
    only = opt("only")
    expect = opt("expect")
    per_writer = int(opt("per-writer", "10"))
    adapter_name = opt("adapter", "reference")
    repeat = max(1, int(opt("repeat", "1")))
    # EVERY PROBE BY DEFAULT. The list used to name only the probes that had been SEEN to flake -
    # concurrent and isolation - which is the same assumption that cost the cost table and the
    # retrieval table a correction each: that a measurement which looked stable once will be stable.
    # Asking for repeats and then not repeating most of the probes is a way of believing a number
    # rather than checking it. Narrow it with --repeat-probes= only to save time, deliberately.
    raw_probes = (opt("repeat-probes", "all") or "").strip()
    repeat_probes = None if raw_probes.lower() == "all" else set(
        p for p in raw_probes.split(",") if p)
    manifest_path = opt("manifest")
    if not cmd:
        print(__doc__)
        return 2

    adapters = {"control": ControlAdapter, "retained": RetainedAdapter,
                "basic-memory": BasicMemoryAdapter, "memento": MementoAdapter,
                "auto": AutoAdapter}
    if manifest_path:
        import manifest as manifestmod
        try:
            mf = manifestmod.load(manifest_path)
        except Exception as exc:
            print("manifest error: %s" % exc)
            return 2
        if not mf.describes(cmd):
            # A MANIFEST THAT DOES NOT DESCRIBE THIS COMMAND PRODUCES CONFIDENT NONSENSE. Refusing is
            # the whole point of declaring which subject it is for.
            print("manifest %s describes %s, not this command; refusing to guess"
                  % (manifest_path, mf.subject))
            return 2
        ad = ManifestAdapter(cmd, mf)
        print("subject  : %s" % mf.subject)
        print("store    : %s (%s)" % (mf.spec.get("path") or mf.spec.get("glob"),
                                      mf.spec.get("kind")))
        if mf.spec.get("content_column"):
            print("measures : record bodies, out of band")
        print()
    else:
        ad = adapters.get(adapter_name, ReferenceAdapter)(cmd)

    rows = []
    fails = 0
    no_ack = []
    other_kinds = []
    for name, fn in PROBES:
        if only and name != only:
            continue
        attempts = repeat if (repeat_probes is None or name in repeat_probes) else 1
        runs = [_run_probe(fn, ad, per_writer) for _ in range(attempts)]
        verdict, kind, evidence, tally = _settle(runs)
        row = {"probe": name, "verdict": verdict, "kind": kind, "evidence": evidence,
               "seconds": round(sum(r["seconds"] for r in runs), 1)}
        if attempts > 1:
            row["runs"] = attempts
            row["tally"] = tally
            row["unstable"] = len(tally) > 1
        if verdict == "FAIL":
            fails += 1
        if kind == "no-ack":
            no_ack.append(name)
        elif kind in NOTABLE_KINDS:
            other_kinds.append("%s: %s" % (name, kind))
        rows.append(row)
        # the kind is printed only when it changes what the verdict means. UNKNOWN already says
        # "not applicable"; a plain PASS or FAIL already says the rest.
        label = "%s(%s)" % (verdict, kind) if kind in NOTABLE_KINDS else verdict
        print("%-16s %-22s %5.1fs  %s" % (name, label, row["seconds"], evidence))
    if out:
        with open(out, "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(json.dumps({"command": cmd, "ceiling_seconds": PROBE_TIMEOUT,
                                 "repeat": repeat, "probes": rows}, indent=2) + chr(10))
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
    isolation = [r for r in rows if r["probe"] == "isolation"]
    if isolation and isolation[0]["verdict"] == "FAIL":
        print()
        print("!! NOT ISOLATABLE: this subject kept state across separate stores.")
        print("!! Every other verdict above is qualified by that and must not be published")
        print("!! as a statement about the subject alone.")
    if no_ack:
        print()
        print("!! %d verdict(s) are 'the subject did not answer within the ceiling', not 'it answered"
              " wrongly'." % len(no_ack))
        print("!! The ceiling is part of the claim. If this subject is merely slow, re-run with a"
              " larger --timeout= before quoting any of it.")
    if other_kinds:
        print()
        print("!! a verdict was reached through an unusual path: %s" % ", ".join(other_kinds))
    print("%d probe(s) failed" % fails)
    if drift:
        return 2
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())