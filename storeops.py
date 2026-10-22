#!/usr/bin/env python3
"""storeops.py - out-of-band edits to a subject's own store.

Two probes need to act as "some other tool that also writes here":

  foreign_field    attach a field the server does not model to a record it wrote
  foreign_record   add a record type the server does not model

How that is done depends on the backend, so both backends live here and the probes stay
backend-agnostic. Every method returns False rather than raising when it cannot do the thing, so a
probe reports UNKNOWN ("we could not test this") instead of FAIL ("it failed").

WHY THE STORE AND NOT THE WIRE. A server's answer is a rendering of what it kept; the store is what
it actually kept. Asking the file is the only way to distinguish "kept it and did not show it" from
"never kept it", and only the second one loses data when a second tool writes.

Both backends are deliberately small. Anything that needs to understand a schema more deeply than
"one row per record, found by this predicate" is not a store backend, it is a hand-written adapter,
and pretending otherwise would produce passes that measure nothing.
"""


def ident(name):
    """Column and table names are interpolated into SQL, so they are whitelisted, never escaped."""
    return "".join(ch for ch in str(name) if ch.isalnum() or ch == "_")


class Store:
    """The interface the probes see. A backend that cannot answer returns False."""

    kind = None

    def annotate_field(self, store, name, key, value):
        raise NotImplementedError

    def field_survived(self, store, name, key):
        raise NotImplementedError

    def inject_record(self, store, record):
        raise NotImplementedError

    def record_survived(self, store, needle):
        raise NotImplementedError

    def content_length(self, store, name):
        """How many characters of the body are still on disk, or None if this backend cannot say."""
        return None


class JsonlStore(Store):
    """One JSON object per line, rewritten whole by every write.

    The classic read-modify-write store: any field the server's own model does not include is dropped
    the moment it serialises the record back out. That is the defect the foreign_field probe exists
    to find, and it is invisible over the wire because the server never promises to keep it.
    """

    kind = "jsonl"

    def __init__(self, path, id_key="name", content_key="observations"):
        self.path = path
        self.id_key = id_key
        self.content_key = content_key

    def exists(self):
        import os
        return os.path.isfile(self.path)

    def _load(self):
        import json
        try:
            with open(self.path, encoding="utf-8") as fh:
                return [json.loads(line) for line in fh if line.strip()]
        except (OSError, ValueError):
            return None

    def _dump(self, rows):
        import json
        try:
            with open(self.path, "w", encoding="utf-8", newline=chr(10)) as fh:
                for obj in rows:
                    fh.write(json.dumps(obj) + chr(10))
        except OSError:
            return False
        return True

    def _mine(self, rows, name):
        return [o for o in rows if o.get(self.id_key) == name]

    def annotate_field(self, store, name, key, value):
        rows = self._load()
        if rows is None:
            return False
        hits = self._mine(rows, name)
        if not hits:
            return False
        for obj in hits:
            obj[key] = value
        return self._dump(rows)

    def field_survived(self, store, name, key):
        import json
        rows = self._load()
        if rows is None:
            return False
        hits = self._mine(rows, name)
        # the field has to be on the record that carried it, at the value that was written; a key
        # somewhere else in the file is not survival
        return bool(hits) and any(obj.get(key) is not None for obj in hits)

    def inject_record(self, store, record):
        import json
        try:
            with open(self.path, "a", encoding="utf-8", newline=chr(10)) as fh:
                fh.write(json.dumps(record) + chr(10))
        except OSError:
            return False
        return True

    def record_survived(self, store, needle):
        rows = self._load()
        if rows is None:
            return False
        return any(str(o.get("id")) == str(needle) for o in rows)

    def content_length(self, store, name):
        rows = self._load()
        if rows is None:
            return None
        hits = self._mine(rows, name)
        if not hits:
            return None
        body = hits[0].get(self.content_key)
        if isinstance(body, list):
            body = body[0] if body else ""
        return len(body) if isinstance(body, str) else None


class SqliteStore(Store):
    """Rows in a table, found by a declared predicate.

    The predicate is declared because identity differs between subjects and guessing it is how a
    benchmark reports its own confusion as a subject's defect: memento has a name column, memdb has
    no name at all and folds the name into the text of the row.

      match = {"column": "name",    "op": "eq"}        one row per name
      match = {"column": "content", "op": "contains"}  the name is somewhere in this column
    """

    kind = "sqlite"

    def __init__(self, path, table="entities", match=None, content_column=None):
        self.path = path
        self.table = ident(table)
        self.match = match or {"column": "name", "op": "eq"}
        self.content_column = ident(content_column) if content_column else None

    def exists(self):
        import os
        return os.path.isfile(self.path)

    def _connect(self):
        import sqlite3
        if not self.exists():
            # sqlite3.connect CREATES the file. A manifest that points at the wrong path would then
            # "succeed" by making an empty database, alter nothing, and report UNKNOWN for a reason
            # that has nothing to do with the subject. Refuse before touching the disk.
            return None
        try:
            return sqlite3.connect(self.path)
        except sqlite3.Error:
            return None

    def _where(self, value):
        col = ident(self.match.get("column") or "name")
        if self.match.get("op") == "contains":
            return "%s LIKE ?" % col, ("%" + str(value) + "%",)
        return "%s = ?" % col, (value,)

    def annotate_field(self, store, name, key, value):
        """Add a column the server does not model and set it on the matching row.

        This is the relational form of "a human adds a field in an editor": the column exists in the
        schema and the row carries it. If the server rewrites the row without that column, the value
        is gone - the same defect the JSONL probe looks for.
        """
        col = ident(key)
        if not col:
            return False
        con = self._connect()
        if con is None:
            return False
        try:
            try:
                con.execute("ALTER TABLE %s ADD COLUMN %s TEXT" % (self.table, col))
            except Exception:
                pass  # already added by an earlier run
            clause, params = self._where(name)
            cur = con.execute("UPDATE %s SET %s=? WHERE %s" % (self.table, col, clause),
                              (value,) + params)
            con.commit()
            return cur.rowcount > 0
        except Exception:
            return False
        finally:
            con.close()

    def field_survived(self, store, name, key):
        col = ident(key)
        if not col:
            return False
        con = self._connect()
        if con is None:
            return False
        try:
            clause, params = self._where(name)
            row = con.execute("SELECT %s FROM %s WHERE %s" % (col, self.table, clause),
                              params).fetchone()
            return bool(row and row[0])
        except Exception:
            return False
        finally:
            con.close()

    def inject_record(self, store, record):
        """A table another tool owns, in the same database.

        The relational analogue of a record type the server does not model. The question is whether a
        server sharing a store destroys data it never read.
        """
        con = self._connect()
        if con is None:
            return False
        try:
            con.execute("CREATE TABLE IF NOT EXISTS foreign_tool_data (id TEXT, payload TEXT)")
            con.execute("INSERT INTO foreign_tool_data VALUES (?, ?)",
                        (str(record.get("id")), str(record.get("content"))))
            con.commit()
            return True
        except Exception:
            return False
        finally:
            con.close()

    def record_survived(self, store, needle):
        con = self._connect()
        if con is None:
            return False
        try:
            row = con.execute("SELECT id FROM foreign_tool_data WHERE id=?",
                              (str(needle),)).fetchone()
            return bool(row)
        except Exception:
            return False
        finally:
            con.close()

    def content_length(self, store, name):
        if not self.content_column:
            return None
        con = self._connect()
        if con is None:
            return None
        try:
            clause, params = self._where(name)
            row = con.execute("SELECT MAX(LENGTH(%s)) FROM %s WHERE %s"
                              % (self.content_column, self.table, clause), params).fetchone()
            return int(row[0]) if row and row[0] is not None else None
        except Exception:
            return None
        finally:
            con.close()
