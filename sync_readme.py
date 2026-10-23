#!/usr/bin/env python3
"""sync_readme.py - put the live matrix output into README.md.

The README shows what "python matrix.py --report-only" prints. Keeping that in step by hand did not
work: the tables were already a subject behind when this was written, and doubling the retrieval
corpus falsified three more numbers stated in prose. So the block is regenerated from the tool that
produces it, and any number that could go stale is read from the thing it describes.

  python sync_readme.py
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NL = chr(10)
FENCE = chr(96) * 3


def main():
    readme = os.path.join(HERE, "README.md")
    with io.open(readme, encoding="utf-8") as fh:
        text = fh.read()
    out = subprocess.run([sys.executable, "matrix.py", "--report-only"], cwd=HERE,
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    body = [l for l in out.splitlines() if not l.startswith("written to ")]
    while body and not body[-1].strip():
        body.pop()
    while body and not body[0].strip():
        body.pop(0)
    rendered = "$ python matrix.py" + NL + NL + NL.join(body)

    anchor = text.find("python matrix.py")
    if anchor < 0:
        print("README has no matrix block to fill")
        return 1
    open_fence = text.rfind(FENCE, 0, anchor)
    close_fence = text.find(NL + FENCE, anchor)
    if open_fence < 0 or close_fence < 0:
        print("the matrix block is not fenced")
        return 2
    new = text[:open_fence] + FENCE + NL + rendered + text[close_fence:]
    with io.open(readme, "w", encoding="utf-8", newline=NL) as fh:
        fh.write(new)
    print("README table block: %d lines of live output" % len(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
