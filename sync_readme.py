#!/usr/bin/env python3
"""sync_readme.py - put the live matrix output into the page that shows it.

The README showed what "python matrix.py --report-only" prints. Keeping that in step by hand did not
work: the tables were already a subject behind when this was written, and doubling the retrieval corpus
falsified three more numbers stated in prose. So the block is regenerated from the tool that produces
it, and any number that could go stale is read from the thing it describes.

WHERE THE BLOCK LIVES IS NOT THIS TOOL'S BUSINESS. It was in README.md; when the README was split into
pages the table moved to docs/subjects.md and this tool, which looked for the first command line it
could find, started failing with "the matrix block is not fenced" - a sync tool that only syncs one
location is a number waiting to go stale somewhere else. It now finds the fenced block by what the
block says, in any page, and reports which page it filled.

    python sync_readme.py
"""
import glob
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
FENCE = chr(96) * 3
PAGES = ["README.md"] + sorted(glob.glob(os.path.join(HERE, "docs", "*.md")))


def find_block(text):
    """The fenced block whose first line runs the matrix report, not the cost pass."""
    pos = 0
    while True:
        i = text.find(FENCE, pos)
        if i < 0:
            return None
        j = text.find(FENCE, i + len(FENCE))
        if j < 0:
            return None
        body = text[i + len(FENCE):j].strip(NL)
        first = (body.split(NL)[0] if body else "").strip()
        if first.startswith("$ python matrix.py") and "--cost-only" not in first:
            return (i, j + len(FENCE), first)
        pos = j + len(FENCE)


def main():
    with io.open(os.path.join(HERE, "matrix.py"), "rb") as fh:
        pass
    out = subprocess.run([sys.executable, "matrix.py", "--report-only"], cwd=HERE,
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    body = [l for l in out.splitlines() if not l.startswith("written to ")]
    while body and not body[-1].strip():
        body.pop()
    while body and not body[0].strip():
        body.pop(0)

    for page in PAGES:
        path = page if os.path.isabs(page) else os.path.join(HERE, page)
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        found = find_block(text)
        if not found:
            continue
        start, end, command = found
        rendered = FENCE + NL + command + NL + NL + NL.join(body) + NL + FENCE
        with io.open(path, "w", encoding="utf-8", newline=NL) as fh:
            fh.write(text[:start] + rendered + text[end:])
        print("%s: %d lines of live matrix output" % (os.path.relpath(path, HERE), len(body)))
        return 0

    print("no page has a fenced matrix block")
    return 1


if __name__ == "__main__":
    sys.exit(main())
