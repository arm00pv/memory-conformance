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
  verbatim         the record comes back as the record that was written, character for character
  restart          the same write survives the server being stopped and started
  forget           a record can be made to stop being kept, and the others are still there after
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
  --adapter=mutant      control/memory_server.py with one promise broken (see mutants.py)
  --manifest=x.json     any server, with its store declared instead of coded

Options
  --only=NAME           run one probe
  --mutant=NAME         which promise the mutant adapter breaks; ignored by the other adapters
  --timeout=SECONDS     per-call ceiling; raise it for a slow subject rather than believing a timeout
  --json=PATH           write the full report
  --expect=PATH         compare against a pinned report: exit 2 on drift, 2 also when the run
                        could not produce verdicts, 0 when the verdicts match - a pin may describe a
                        known failure and the job should stay green while it is still that
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

    def delete(self, srv, name):
        """Ask the subject to forget one record, if it publishes a way to be asked.

        THE TOOL LIST IS THE SUBJECT'S OWN ANSWER. Assuming a server has delete_entities because the
        reference implementation does is how a probe reports a subject defect for a tool that was never
        there - and a subject with no way to forget is not broken, it is a subject this question cannot
        be put to. Asking first turns that into UNKNOWN, which is what it is.
        """
        tools = [t.get("name") for t in (srv.request("tools/list", {}).get("tools") or [])]
        for tool, args in (("delete_entities", {"entityNames": [name]}),
                           ("forget", {"name": name}), ("delete", {"name": name})):
            if tool in tools:
                return srv.call(tool, args)
        raise ToolRefused("this subject publishes no tool that can be asked to forget a record")

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


# A SENTINEL, NOT None. "not looked for yet" and "looked for and not there" are different answers,
# and collapsing them would re-run the proof on every call or never run it at all.
_UNSET = object()


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
        # A SENTINEL, NOT None, and it belongs in __init__ as well as reset(). "not looked for yet"
        # and "looked for and not there" are different answers, and the first version of this set it
        # only in reset() - so every discovery-bound subject raised AttributeError on the new probe
        # while the hand-written adapters answered it, which is the harness reporting its own bug as
        # the subject's silence.
        self._deleter = _UNSET
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
        self._deleter = _UNSET
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

    def delete(self, srv, name):
        """Forget one record through the subject's own delete tool, proven before it is used."""
        import autodetect as ad
        self._discover(srv)
        if self._deleter is _UNSET:
            self._deleter = self._bind_delete(srv)
        if not self._deleter:
            raise ToolRefused("this subject publishes no delete tool whose effect could be proven")
        return srv.call(self._deleter["name"], ad.build_delete_args(self._deleter, name),
                        timeout=PROBE_TIMEOUT)

    def _bind_delete(self, srv):
        """Prove a delete tool the way every binding here is proven: by doing it and reading back.

        A name that looks like deletion is not a deletion. The candidate is called on a token this
        adapter wrote, and the binding is kept only if the token is gone from the next read.
        """
        import autodetect as ad
        w, r, _s = self._binding
        for i, cand in enumerate(ad.delete_candidates(getattr(self, "_tools", []), w)):
            tok = "delete-token-%d" % (i + 1)
            args = ad.build_delete_args(cand, tok)
            if not args:
                continue
            try:
                srv.call(w["name"], ad.build_write_args(w, tok, ["deletion probe"]),
                         timeout=PROBE_TIMEOUT)
                srv.call(cand["name"], args, timeout=PROBE_TIMEOUT)
            except Exception:
                continue
            if r is None:
                continue
            try:
                got = srv.call(r["name"], ad.build_read_args(r), timeout=PROBE_TIMEOUT)
            except Exception:
                continue
            if tok not in got:
                return cand
        return None

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

    def body_text(self, store, name):
        """The record's body as characters, for the probes that compare text and not lengths.

        This is the surface for a subject that answers a read with the record's name and keeps the
        body where only the store can see it - six of the eleven measured here do exactly that.
        """
        self.store_reason = None
        try:
            return self._ops_for(store).content_text(store, name)
        except LookupError:
            return None
        except Exception:
            return None


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

    def delete(self, srv, name):
        """The control forgets by appending a tombstone, because it never rewrites its store."""
        return srv.call("memory_forget", {"name": name})

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

    def _need(self, terms):
        """How many of the question's terms a record must match to count as an answer.

        HALF OF THEM, AND THIS NUMBER IS THE WHOLE DIFFERENCE between a memory that declines an
        unanswerable question and one that answers it with something plausible. It is a method rather
        than a local so the retrieval mutants can move it without copying the search.
        """
        return max(1, (len(terms) + 1) // 2)

    def search(self, srv, query, k=3):
        """Term overlap over the observations, which is all this control claims to do."""
        low = query.lower()
        for ch in "?!.,;:()[]'\"":
            low = low.replace(ch, " ")
        terms = [t for t in low.split() if t and t not in self.STOPWORDS]
        if not terms:
            return []
        need = self._need(terms)
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


class MutantAdapter(ControlAdapter):
    """The control with one promise broken, so the probe that watches it has something to fail on.

    WHY THIS EXISTS. A control proves the probes can pass. It says nothing about whether they can
    fail, and a probe that has never returned FAIL on any subject in the table is indistinguishable
    from a probe with a bug that always says PASS - which is not hypothetical here: the forget probe
    was published with six PASSes, five "cannot be asked" and no FAIL at all, so nothing in the
    published results showed the probe had teeth.

    Two mutations cannot be expressed in the server at all. "The search does not search" is a
    property of what the caller gets back, not of what the process does, so blind-search and
    mute-search are broken here. Every other mutation is server-side and selected by MEMORY_MUTANT,
    which the child inherits; this class only has to know which of them it is.
    """

    MUTANT = ""
    # where the answer key lives, for the one control that is allowed to cheat
    CASES = ""
    _ORACLE = None

    def _answers(self):
        """question or keyword form -> the record the corpus says answers it."""
        if MutantAdapter._ORACLE is None:
            import words
            index = {}
            with open(self.CASES, encoding="utf-8") as fh:
                doc = json.load(fh)
            for q in doc.get("queries") or []:
                if not q.get("expect"):
                    continue
                index[q["query"].strip().lower()] = q["expect"]
                index[words.keyword_form(q["query"]).strip().lower()] = q["expect"]
            MutantAdapter._ORACLE = index
        return MutantAdapter._ORACLE

    def _need(self, terms):
        if self.MUTANT == "greedy-match":
            # ONE TERM IS ENOUGH. Every question gets an answer, including the twelve that have none,
            # which is what a memory does when it optimises for the caller never going away empty.
            return 1
        if self.MUTANT == "strict-match":
            # EVERY TERM IS REQUIRED. The opposite defect: a correct record that shares one word with
            # the question's phrasing is no longer an answer, so recall falls and refusals rise.
            return len(terms)
        return ControlAdapter._need(self, terms)

    def search(self, srv, query, k=3):
        if self.MUTANT == "one-result":
            # THE CALLER READS ONE ANSWER. Not a ranking defect - the same search with k lowered - so
            # this lever moves hit@3 and leaves hit@1 alone, which is the direction the score does
            # notice.
            return ControlAdapter.search(self, srv, query, 1)
        if self.MUTANT == "reverse-rank":
            # THE WORST MATCH FIRST. The set is unchanged, so hit@3 cannot see this at all and the
            # score built on it cannot either; hit@1 collapses. It exists to find out whether that is
            # true, because a benchmark blind to ordering is a benchmark an agent's top hit can fail.
            return list(reversed(ControlAdapter.search(self, srv, query, k)))
        if self.MUTANT == "oracle-search":
            # THE CEILING, AND IT CHEATS ON PURPOSE. This is not a subject; it is the answer key wired
            # to a search tool, so the top of the retrieval scale can be stated rather than assumed.
            # Without it, "42 out of 60" describes a subject and says nothing about how much of the
            # scale 42 is - a scale whose maximum nobody has ever measured is a scale that might have
            # been full at 45.
            found = self._answers().get(query.strip().lower())
            return [found] if found else []
        if self.MUTANT == "mute-search":
            # Nothing is ever found. A memory that stores perfectly and answers nothing.
            return []
        if self.MUTANT == "blind-search":
            # Something is always found, and it is the same something whatever was asked.
            ents = self.read(srv) or []
            return sorted(str(e.get("name")) for e in ents if e.get("name"))[:k]
        return ControlAdapter.search(self, srv, query, k)


class RetainedAdapter(ReferenceAdapter):
    """retained.py - append-only, hash-chained, read-back verified. Same probe surface.

    Inherits ReferenceAdapter for the out-of-band store edits, and that inheritance is a bug fix
    rather than a convenience. When the foreign-data probes were moved behind adapter methods so a
    SQLite subject could answer them, this adapter was left behind: it still only provided
    store_path, so both probes raised AttributeError and were reported as harness errors instead of
    verdicts. The old probes had opened records.jsonl themselves and needed nothing else, which is
    why the breakage was invisible on the machine where it happened and only surfaced in CI, three
    phases later, against a subject that is not installed locally.
    """

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
        """Answer the question, in two calls.

        NOT BUILT ON search_text. That method concatenates both wire responses so the cost of
        answering can be measured, and concatenated JSON is not JSON: parsing it here made every
        search return nothing, and made this adapter look like a server that cannot find its own
        records. The measurement view and the answering view are different things and this is the
        adapter that proves it, because it is the only one that has to make two calls.
        """
        first = srv.call("memory_search", {"query": query, "k": k})
        try:
            data = json.loads(first)
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


# ONE STRING PER LAYER OF THE ENCODING STACK, because they fail independently and a store that
# mangles one usually handles another correctly. Escapes rather than literal characters so the source
# file stays ASCII and the code points being claimed are unambiguous on inspection.
VERBATIM = [
    "ascii: the quick brown fox",
    "latin: caf\u00e9, na\u00efve, \u00e5\u00e4\u00f6",
    "cjk: \u65e5\u672c\u8a9e\u306e\u30c6\u30ad\u30b9\u30c8",
    "astral: \U0001f9ea\U0001f52c",
    "combining: e\u0301 against \u00e9",
    "rtl: \u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645",
    "escapes: back\\slash, \"quote\", tab\there",
    "zero-width: a\u200bb",
    "newline:\nsecond line",
]
# The name carries non-ASCII too: a store can keep the body and lose the handle it was filed under.
VERBATIM_NAME = "verbatim-caf\u00e9-\u65e5\u672c"

# A CONTROL RECORD INSIDE THE PROBE. A subject that answers a read with the record's name and keeps
# the body where nothing here can reach it would otherwise be reported as having mangled nine strings
# it never showed. So a plain ASCII record is written through the same path: if that does not come
# back either, the probe cannot see this subject's bodies at all and says so instead of inventing a
# defect. "I cannot see it" and "it is gone" are different answers and only one of them is a verdict.
VERBATIM_CANARY = "verbatim-canary"
VERBATIM_CANARY_BODY = "canary-marker-0123456789"


def _visible(text):
    """Escape a string so a difference between two of them is visible in a terminal."""
    out = []
    for ch in text:
        code = ord(ch)
        if ch == chr(10):
            out.append("\\n")
        elif ch == chr(9):
            out.append("\\t")
        elif ch == "\\":
            out.append("\\\\")
        elif 32 <= code < 127:
            out.append(ch)
        elif code > 0xFFFF:
            out.append("\\U%08x" % code)
        else:
            out.append("\\u%04x" % code)
    return "".join(out)[:150]


def _strings_of(obj, out=None):
    """Every string anywhere inside a returned record, whatever shape the subject uses.

    THE SHAPE IS THE SUBJECT'S BUSINESS, NOT THE PROBE'S. The first version of this probe required a
    field called observations holding a list, which is the reference server's model; seven of eleven
    subjects keep the body some other way and every one of them came back UNKNOWN. The promise being
    tested is that the characters survive, and where the subject puts them is its own choice.
    """
    if out is None:
        out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            _strings_of(value, out)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _strings_of(value, out)
    return out


def _closest(want, candidates):
    """The returned string that agrees with the written one for the longest prefix, and how far.

    A count of shared leading characters is the useful diagnosis: it says where the two part company
    without asking the reader to diff two escaped strings by eye.
    """
    best, score = "", -1
    for cand in candidates:
        n = 0
        for a, b in zip(want, cand):
            if a != b:
                break
            n += 1
        if n > score:
            best, score = cand, n
    return best, max(score, 0)


def probe_verbatim(ad):
    """Does a record come back as the record you stored, character for character?

    THE NARROWEST FORM OF THE ENTIRE PROMISE, and the one most likely to break without anybody
    noticing. Every other probe checks that the record is THERE; none checks that it is the SAME.
    A store that re-encodes text into the machine's codepage, normalises composed characters,
    strips zero-width joiners, escapes an embedded newline or rejoins the lines answers every other
    probe in this suite and still hands back something the caller never wrote.

    IT IS ALSO THIS SUITE'S OWN HISTORY. The harness once decoded a subject's stdout as cp1252,
    because Popen(text=True) uses the console codepage on Windows, and an em dash in a tool
    description killed the reader thread and made every later call time out as if the server had
    hung. The control server lost a phase to the same family - no O_BINARY, so every byte it wrote
    was rewritten on the way out. Neither was a memory defect; both were text going through a
    boundary and not coming back. This asks the subject the same question directly.

    NINE STRINGS, each aimed at a different layer: 2, 3 and 4-byte UTF-8, a combining pair against
    its precomposed twin, right-to-left text, JSON escapes, a zero-width space, and a newline
    embedded in the body of a newline-delimited transport. The name is non-ASCII too, because the
    handle can be lost while the body survives.

    TWO SURFACES, BECAUSE SIX OF ELEVEN SUBJECTS KEEP THE BODY WHERE ONLY THE STORE CAN SEE IT. The
    first version demanded a field called observations holding a list - the reference server's model -
    and seven of eleven subjects came back UNKNOWN. The promise is that the characters survive, and
    where a subject puts them is its own choice: the returned record is searched first, and the
    adapter's declared store is searched when the answer to a read is the record's name alone.

    A CANARY DECIDES WHETHER THE PROBE CAN SEE AT ALL. Writing nine strings and reporting nine
    defects when the subject never returns a body would be inventing a result, so a plain ASCII
    record goes through the same path first. If that does not come back either, there is nothing to
    compare and the verdict is UNKNOWN with the reason - "I cannot see it" and "it is gone" are
    different answers and only one of them is a verdict.

    ORDER IS REPORTED, NOT JUDGED. memento returns the observations of a record sorted, so the nine
    lines come back with every character intact and none of their original sequence. Calling that a
    verbatim failure would tell a reader the text was mangled, which is false, and passing without a
    word would hide that a sequence you stored as a sequence comes back alphabetical. So the verdict
    is about the characters - the one thing this probe does not have to interpret - and the evidence
    says which order the subject chose.
    """
    d, store = _fresh()
    try:
        srv = ad.server(store)
        try:
            ad.write(srv, VERBATIM_NAME, list(VERBATIM))
            ad.write(srv, VERBATIM_CANARY, [VERBATIM_CANARY_BODY])
        finally:
            srv.stop()
        # A COLD PROCESS: nothing that formatted this text is still in memory to reformat it back.
        srv = ad.server(store)
        try:
            ents = ad.read(srv) or []
        finally:
            srv.stop()
        hit = [e for e in ents if isinstance(e, dict) and e.get("name") == VERBATIM_NAME]
        if not hit:
            near = [e.get("name") for e in ents if isinstance(e, dict) and e.get("name")]
            looked = [n for n in near if str(n).startswith("verbatim")] or near[:3]
            return False, ("the record did not come back under the name it was written with, so there"
                           " is nothing to compare: asked for %s, the store answered with %s"
                           % (_visible(VERBATIM_NAME), [_visible(str(n)) for n in looked][:3]))
        # WHEREVER THE SUBJECT PUT THEM, ON WHICHEVER SURFACE IT OFFERS THEM. Every string in the
        # returned record is a candidate; when the subject answers a read with the name alone, the
        # store's own copy of the body is asked instead. Six of the eleven measured subjects need the
        # second surface, and without it this probe reports UNKNOWN for all six.
        reader = getattr(ad, "body_text", None)

        def strings_of(name):
            for ent in ents:
                if isinstance(ent, dict) and ent.get("name") == name:
                    return _strings_of(ent)
            return []

        def store_text(name):
            return reader(store, name) if callable(reader) else None

        body = strings_of(VERBATIM_NAME)
        stored = store_text(VERBATIM_NAME)
        canary_store = store_text(VERBATIM_CANARY)
        canary_seen = (any(VERBATIM_CANARY_BODY in s for s in strings_of(VERBATIM_CANARY))
                       or (isinstance(canary_store, str)
                           and VERBATIM_CANARY_BODY in canary_store))
        if not canary_seen:
            return None, ("a plain ASCII record written the same way does not come back either - not"
                          " over the wire, and not from a store this harness can read - so this probe"
                          " cannot see this subject's record bodies at all. That is a gap in the"
                          " probe against this subject, not a verdict about its text")

        def survived(text):
            if any(text in got for got in body):
                return "wire"
            if isinstance(stored, str) and text in stored:
                return "store"
            return ""

        found = dict((s, survived(s)) for s in VERBATIM)
        missing = [s for s in VERBATIM if not found[s]]
        tail = ("2, 3 and 4-byte UTF-8, a combining pair, right-to-left text, JSON escapes, a"
                " zero-width space and an embedded newline, under a non-ASCII name")
        if not missing:
            where = set(found[s] for s in VERBATIM)
            how = ("over the wire" if where == set(["wire"]) else
                   "in the store, which this subject does not return over the wire"
                   if where == set(["store"]) else "over the wire and in the store")
            order = ""
            obs = hit[0].get("observations") if isinstance(hit[0], dict) else None
            if isinstance(obs, list) and list(obs) != list(VERBATIM):
                if sorted(obs) == sorted(VERBATIM):
                    order = (" - in an order of the subject's own choosing, so every character"
                             " survived and the sequence did not")
            return True, ("all %d strings came back byte for byte, %s: %s%s"
                          % (len(VERBATIM), how, tail, order))
        want = missing[0]
        near, shared = _closest(want, body + ([stored] if isinstance(stored, str) else []))
        return False, ("%d of %d strings did not come back intact. Wrote %s; the nearest thing found"
                       " is %s, which agrees with it for its first %d characters"
                       % (len(missing), len(VERBATIM), _visible(want), _visible(near),
                          min(shared, len(want))))
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


def probe_forget(ad):
    """Can the subject be asked to forget, and does the record actually go?

    THE ONE PROMISE THE SUITE NEVER TESTED. Every other probe asks what the subject kept; none asked
    whether it can be made to stop keeping it. Deletion is the operation that matters most to anyone
    with a wrong fact, a private record or a mistake in their memory, and it is the one that fails in
    the same direction as the write: the caller is told "ok" and believes it either way.

    THREE STATES. PASS when the forgotten record is gone after a restart AND the two records nobody
    asked about are still there - the second half is what makes the first meaningful, because a store
    that drops everything looks identical to a store that forgot exactly what it was told to. FAIL
    when the record is still readable. UNKNOWN when the subject publishes no way to ask, which is a
    subject this question cannot be put to rather than a broken one.

    THE THREE NAMES SHARE NO TOKEN, for the reason findable's do not: a reading that returns
    "everything" would otherwise be indistinguishable from one that honours the request.
    """
    forget = getattr(ad, "delete", None)
    if not callable(forget):
        return None, ("this adapter has no way to ask the subject to forget, so the probe cannot be"
                      " expressed against it; that is a gap in the harness, not a defect in the subject")
    names = ["tundra-halcyon", "plinth-obsidian", "ember-thistle"]
    d, store = _fresh()
    try:
        srv = ad.server(store)
        try:
            for nm in names:
                ad.write(srv, nm, ["observation about %s" % nm])
            try:
                answer = forget(srv, names[1])
            except ToolRefused as exc:
                # A SUBJECT THAT CANNOT BE ASKED IS NOT A SUBJECT THAT FAILED. "This memory has no way
                # to forget" is a capability gap and a real thing for a user to know, but it is not the
                # promise broken - the promise is broken when the caller is told the record is gone and
                # it is not. So: UNKNOWN with the reason, and the reason is printed.
                return None, ("this subject publishes no way to be asked to forget, so the promise"
                              " cannot be tested: %s" % str(exc)[:160])
        finally:
            srv.stop()
        # A COLD READ, on a server that never saw the write or the deletion.
        srv = ad.server(store)
        try:
            ents = ad.read(srv) or []
        finally:
            srv.stop()
        have = [e.get("name") for e in ents if isinstance(e, dict)]
        kept = [n for n in (names[0], names[2]) if n in have]
        if len(kept) != 2:
            return None, ("the two records nobody asked to forget did not both come back (%d of 2), so"
                          " a successful deletion cannot be told from a store that lost everything;"
                          " read back %s" % (len(kept), have[:5]))
        gone = names[1] not in have
        said = " ".join(str(answer).split())[:80] if answer else "no answer"
        return gone, ("asked to forget %s and the subject answered %r; after a restart the other two"
                      " came back and it %s" % (names[1], said,
                                               "did not" if gone else "STILL DID"))
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


# THE ONE LIST. Four files used to keep their own copy of this - harness, matrix, check and mutants -
# and every copy was a place to forget. check.py was already one short: it had never heard of forget,
# added a phase earlier, and had been silently skipping it ever since. The others import PROBE_NAMES
# from here; a table, a runner and a runner of mutants cannot disagree about what the probes are.
PROBES = [("isolation", probe_isolation),
          ("ack_readback", probe_ack_readback),
          ("verbatim", probe_verbatim),
          ("restart", probe_restart),
          ("forget", probe_forget),
          ("findable", probe_findable),
          ("foreign_field", probe_foreign_field),
          ("foreign_record", probe_foreign_record),
          ("concurrent", probe_concurrent),
          ("large_record", probe_large_record)]

PROBE_NAMES = [name for name, _fn in PROBES]


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

    MutantAdapter.MUTANT = (opt("mutant") or "").strip()
    adapters = {"control": ControlAdapter, "retained": RetainedAdapter,
                "basic-memory": BasicMemoryAdapter, "memento": MementoAdapter,
                "auto": AutoAdapter, "mutant": MutantAdapter}
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
    # WITH A PIN, THE PIN IS THE EXPECTATION. A subject can legitimately be pinned with a known
    # failure - "this one refuses a foreign record, and we know" - and the job should stay green
    # while that remains true and go red the moment it changes. Reporting absolute failures here
    # made a pinned expectation unusable for anything that is not all green.
    if expect:
        return 2 if drift else 0
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())