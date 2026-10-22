#!/usr/bin/env python3
"""triage.py - find out whether a package can be a subject, and what it takes to declare it.

A memory server becomes a subject only if three things are true: it starts over stdio, it accepts a
write, and it keeps that write somewhere a manifest can name. Two of those are cheap to check and the
third is the one that decides, because a subject whose store cannot be redirected cannot be isolated
and an isolated store is a precondition for every verdict in this project.

  python triage.py @zensation/mcp memory-lean ...

For each package it prints the tool surface, a proposed write, whether that write succeeded, and
every file the run left behind - with the tables of any SQLite store, since that is what a manifest
has to name. Nothing is written outside a temporary directory. A subject that needs an external
database fails here rather than halfway through a matrix run.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile

import harness
import autodetect as ad

INTERESTING = ("content", "text", "title", "name", "summary", "memory", "observation", "fact")


def entry_point(pkg):
    path = os.path.join("node_modules", pkg, "package.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:
        return None, "no package.json (%s)" % exc
    b = doc.get("bin")
    if isinstance(b, str):
        return {"entry": b, "name": doc.get("name"), "version": doc.get("version")}, None
    if isinstance(b, dict) and b:
        # A PACKAGE CAN SHIP A CLI AND A SERVER. @hasna/mementos exposes "mementos" (a CLI that does
        # not speak MCP) ahead of "mementos-mcp"; taking the first entry point started the CLI and
        # reported "initialize did not answer", which reads as a broken server. Prefer the name that
        # says mcp.
        keys = sorted(b, key=lambda k: ("mcp" not in k.lower(), k))
        return {"entry": b[keys[0]], "name": doc.get("name"),
                "version": doc.get("version")}, None
    if doc.get("main"):
        return {"entry": doc["main"], "name": doc.get("name"),
                "version": doc.get("version")}, None
    return None, "no bin or main"


def tables(path):
    out = []
    try:
        con = sqlite3.connect(path)
    except Exception as exc:
        return ["sqlite error: %s" % exc]
    try:
        for (t,) in con.execute("select name from sqlite_master where type='table' "
                                "and name not like 'sqlite_%' and name not like '%_data' "
                                "and name not like '%_idx' and name not like '%_docsize' "
                                "and name not like '%_config' and name not like '%_content'"):
            cols = [r[1] for r in con.execute('PRAGMA table_info("%s")' % t)]
            n = con.execute('select count(*) from "%s"' % t).fetchone()[0]
            hit = [c for c in cols if any(k in c.lower() for k in INTERESTING)]
            out.append("      %-26s rows=%-3d cols=%s%s"
                       % (t, n, cols[:6], ("  <- " + ",".join(hit)) if hit else ""))
    except Exception as exc:
        out.append("      sqlite error: %s" % exc)
    finally:
        con.close()
    return out


def triage(pkg):
    info, err = entry_point(pkg)
    print("=" * 78)
    if err:
        print("%-30s SKIP  %s" % (pkg, err))
        return
    print("%s %s" % (info["name"], info["version"]))
    entry = os.path.abspath(os.path.join("node_modules", pkg, info["entry"]))
    cmd = 'node "' + entry.replace(os.sep, "/") + '"'
    d = tempfile.mkdtemp(prefix="triage_")
    try:
        try:
            srv = harness.McpServer(cmd, d, cwd=d).start()
        except Exception as exc:
            print("  START FAILED: %s" % str(exc)[:160])
            return
        try:
            tools = srv.request("tools/list", {}, timeout=40).get("tools") or []
            print("  tools: %s" % ", ".join(t["name"] for t in tools)[:300])
            w = ad.pick_write(tools)
            if not w:
                print("  no write tool - this is not a memory server")
                return
            args = ad.build_write_args(w, "triage-token", ["a record written by triage"])
            print("  write: %s %s" % (w["name"], json.dumps(args)[:180]))
            try:
                out = srv.call(w["name"], args, timeout=60)
                print("  ack  : %s" % (" ".join(out.split())[:160] or "(empty)"))
            except Exception as exc:
                print("  REFUSED: %s" % str(exc)[:180])
        finally:
            srv.stop()
        for root, _dirs, files in os.walk(d):
            for f in sorted(files):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, d)
                print("  file %-34s %9d" % (rel, os.path.getsize(p)))
                if f.endswith(".db") or f.endswith(".sqlite3"):
                    for line in tables(p):
                        print(line)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    for pkg in argv:
        triage(pkg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
