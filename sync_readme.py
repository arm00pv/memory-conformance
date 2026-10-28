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


# THE TOOLS WHOSE OUTPUT IS A TRANSCRIPT OF COMMITTED RESULTS. matrix.py re-renders the tables and
# compare.py re-runs one paired test; both read results/ and neither launches a subject. The pages
# also show commands that DO launch one - harness.py against a node_modules path - and those cannot
# be regenerated at all, which is said plainly rather than faked by leaving them out of a list that
# looks exhaustive.
TOOLS = ("matrix.py", "compare.py")


def names_a_report(first):
    """Whether a fenced block is a transcript of a command this repository can re-run offline."""
    parts = first.split("#", 1)[0].split()
    return (len(parts) > 2 and parts[0] == "$" and parts[1] == "python"
            and parts[2] in TOOLS)


def find_blocks(text):
    """Every fenced block whose first line runs the matrix report - both of them, in every page.

    ONE BLOCK WAS ALL THIS TOOL COULD FILL, and the page that showed the cost table kept a copy of it
    instead: a table of nine subjects and seven columns with nothing connecting it to the timings that
    produced it. A transcript is a claim about what a command prints, so the block names the command and
    the block is regenerated from it - all of them, not the first one found.
    """
    out, pos = [], 0
    while True:
        i = text.find(FENCE, pos)
        if i < 0:
            return out
        j = text.find(FENCE, i + len(FENCE))
        if j < 0:
            return out
        body = text[i + len(FENCE):j].strip(NL)
        first = (body.split(NL)[0] if body else "").strip()
        if names_a_report(first):
            # THE FENCE'S OWN INDENTATION IS PART OF THE MARKDOWN. A transcript inside a bullet is
            # indented, and re-rendering it flush left moves it out of the bullet it belongs to -
            # which is what the first version of this did to the README.
            line_start = text.rfind(NL, 0, i) + 1
            out.append((i, j + len(FENCE), first, text[line_start:i]))
        pos = j + len(FENCE)


def report_only_args(command):
    """The flags a block's command names, with --report-only forced on.

    THE PAGE'S COMMAND IS THE GUARD'S COMMAND. A block that says --cost-only must not be filled by a
    full run, and a block that says nothing must not be filled by a run that launches eleven servers:
    both are asked for the same rendering, and the difference between them is which flags are kept.
    """
    parts = command.split("#", 1)[0].split()
    flags = [p for p in parts[3:] if p != "--report-only"]
    # ONLY THE MATRIX TOOL HAS A REPORT-ONLY MODE. compare.py reads the saved rows already and takes
    # two subject names; passing it a flag it does not know would be a guard that runs a different
    # command from the one the page names.
    return flags + (["--report-only"] if parts[2] == "matrix.py" else [])


def render(command):
    """What the command in the block prints, with the progress chatter removed."""
    parts = command.split("#", 1)[0].split()
    out = subprocess.run([sys.executable, parts[2]] + report_only_args(command), cwd=HERE,
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise SystemExit("%s failed:" % command + NL + (out.stderr or out.stdout)[-800:])
    body = [l for l in out.stdout.splitlines() if not l.startswith("written to ")]
    while body and not body[-1].strip():
        body.pop()
    while body and not body[0].strip():
        body.pop(0)
    return body


def main():
    filled = 0
    for page in PAGES:
        path = page if os.path.isabs(page) else os.path.join(HERE, page)
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding="utf-8", newline="") as fh:
            # LINE ENDINGS ARE THE CHECKOUT'S BUSINESS, NOT THE PARSER'S. A page checked out with
            # CRLF made every block's first line read as a carriage return, so no block was found,
            # the tool exited 0 having filled nothing, and the one page that carried a stale
            # transcript was skipped in silence. Normalising on read costs nothing and removes a
            # way for this to lie.
            text = fh.read().replace(chr(13) + NL, NL)
        blocks = find_blocks(text)
        if not blocks:
            continue
        # FROM THE LAST BLOCK BACKWARDS, so replacing one does not move the offsets of the next.
        for start, end, command, indent in reversed(blocks):
            body = render(command)
            lines = [FENCE, command, ""] + body + [FENCE]
            rendered = (NL + indent).join(lines)
            text = text[:start] + rendered + text[end:]
            filled += 1
            print("%s: %d lines of live matrix output from %s"
                  % (os.path.relpath(path, HERE), len(body), command.split("#")[0].strip()))
        with io.open(path, "w", encoding="utf-8", newline=NL) as fh:
            fh.write(text)

    if not filled:
        print("no page has a fenced matrix block")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
