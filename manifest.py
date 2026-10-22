#!/usr/bin/env python3
"""manifest.py - a subject's store, declared instead of coded.

A hand-written adapter is 40 to 200 lines whose only real content is "where the bytes are and how a
record is identified". Everything else is the same in every adapter. A manifest says those two
things in JSON:

  {
    "subject": "@j0hanz/memdb 1.4.0",
    "command_must_contain": ["memdb"],
    "why": "one row per memory; the name the caller passes is part of the row text",
    "store": {
      "kind": "sqlite",
      "path": ".memdb/memory.db",
      "table": "memories",
      "match": {"column": "content", "op": "contains"},
      "content_column": "content"
    }
  }

A DECLARATION IS A CLAIM, AND CLAIMS ARE CHECKED. The probe never trusts the manifest with the
verdict: it writes a record first, then asks the declared path for it. If the path does not exist,
or the predicate finds no row, the probe reports UNKNOWN with the reason - which is the difference
between "the subject dropped my field" and "I was looking at the wrong file".

TWO GUARDS, because a wrong manifest is worse than no manifest:

  command_must_contain  one of these must appear in the command being run. Applying a memento
                        manifest to memdb would produce confident, meaningless verdicts.
  no silent creation     a SQLite connect on a missing path CREATES the file. The store backends
                        refuse to connect until the path exists, so a typo cannot manufacture an
                        empty database and call it a store.
"""
import json
import os
import sys

import storeops


class ManifestError(Exception):
    """The declaration is malformed. This is a bug in the manifest, not a subject defect."""


KINDS = {"jsonl": storeops.JsonlStore, "sqlite": storeops.SqliteStore}


class Manifest:
    def __init__(self, doc, origin="<memory>"):
        self.doc = doc
        self.origin = origin
        self.subject = doc.get("subject") or origin
        self.why = doc.get("why") or ""
        self.command_must_contain = doc.get("command_must_contain") or []
        spec = doc.get("store")
        if not isinstance(spec, dict):
            raise ManifestError("%s: no 'store' object" % origin)
        self.spec = spec
        kind = spec.get("kind")
        if kind not in KINDS:
            raise ManifestError("%s: store kind %r is not one of %s"
                                % (origin, kind, sorted(KINDS)))
        if not spec.get("path") and not spec.get("glob"):
            raise ManifestError("%s: store needs 'path' (or 'glob')" % origin)

    def describes(self, cmd):
        """Does this manifest claim to describe this command?"""
        if not self.command_must_contain:
            return True
        low = (cmd or "").lower()
        return any(token.lower() in low for token in self.command_must_contain)

    def resolve(self, store_dir):
        """The store file inside this run's directory, or None if the declaration does not hold."""
        import glob as globmod
        rel = self.spec.get("path")
        if rel:
            p = rel if os.path.isabs(rel) else os.path.join(store_dir, rel)
            return p if os.path.isfile(p) else None
        pattern = os.path.join(store_dir, self.spec["glob"])
        hits = sorted(globmod.glob(pattern, recursive=True))
        # ONE FILE OR NOTHING. Two matches means the manifest does not know which store it means,
        # and picking the first would make the run depend on directory order.
        return hits[0] if len(hits) == 1 else None

    def store_for(self, store_dir):
        """A backend bound to this run's store, or (None, reason) when the declaration fails."""
        path = self.resolve(store_dir)
        if path is None:
            return None, ("manifest declares %r but the run's store holds no such file (%s)"
                          % (self.spec.get("path") or self.spec.get("glob"), store_dir))
        spec = self.spec
        kind = spec["kind"]
        if kind == "jsonl":
            return storeops.JsonlStore(path, id_key=spec.get("id_key") or "name",
                                       content_key=spec.get("content_key") or "observations"), None
        return storeops.SqliteStore(path, table=spec.get("table") or "entities",
                                    match=spec.get("match"),
                                    content_column=spec.get("content_column")), None


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError as exc:
        raise ManifestError("cannot read %s: %s" % (path, exc))
    except ValueError as exc:
        raise ManifestError("%s is not valid JSON: %s" % (path, exc))
    if not isinstance(doc, dict):
        raise ManifestError("%s must contain a JSON object" % path)
    return Manifest(doc, origin=path)

def check(manifest_path, cmd):
    """Prove a manifest before anyone publishes a verdict that depends on it.

    A manifest is two claims: this file is the store, and this predicate finds a record. Both are
    cheap to check and expensive to get wrong - a manifest pointing at the wrong file yields
    confident, meaningless PASSes, which is the failure mode the whole project exists to avoid. So the
    check writes a record through the server and then asks the declared store to find it.

    usage: manifest.py manifests/memdb.json "node node_modules/@j0hanz/memdb/dist/index.js"
    """
    import tempfile
    import shutil
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import harness

    try:
        mf = load(manifest_path)
    except ManifestError as exc:
        print("FAIL  %s" % exc)
        return 2
    print("subject  : %s" % mf.subject)
    if not mf.describes(cmd):
        print("FAIL  the manifest does not describe this command; it would grade the wrong subject")
        return 2
    if mf.why:
        print("why      : %s" % mf.why)

    ad = harness.ManifestAdapter(cmd, mf)
    store = tempfile.mkdtemp(prefix="manifest_check_")
    token = "manifest-check-token"
    try:
        srv = ad.server(store)
        try:
            ad.write(srv, token, ["a record written to prove the declaration"])
        finally:
            srv.stop()
        path = mf.resolve(store)
        if path is None:
            print("FAIL  wrote a record but %r holds no %s"
                  % (store, mf.spec.get("path") or mf.spec.get("glob")))
            print("      the subject is writing somewhere the manifest does not name")
            return 1
        print("store    : %s" % path)
        ops = mf.store_for(store)[0]
        # annotate_field reports False when no row matched, so it doubles as the predicate test:
        # it only touches a row it found by the declared predicate.
        if not ops.annotate_field(store, token, "manifest_check", "1"):
            print("FAIL  the store is there but the declared predicate found no record for %r" % token)
            print("      check store.match: %s" % json.dumps(mf.spec.get("match") or {}))
            return 1
        print("predicate: %s  ->  matched the record that was just written"
              % json.dumps(mf.spec.get("match") or {"column": "name", "op": "eq"}))
        if ops.content_length(store, token) is None:
            print("note     : no content column declared; the size probe will not measure bodies")
        print("OK        this manifest describes this subject")
        return 0
    finally:
        shutil.rmtree(store, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(check(sys.argv[1], sys.argv[2]))
