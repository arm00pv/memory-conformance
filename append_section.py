"""_append.py - append a staged file to a target, without reading the target.

The read-modify-write pattern has silently truncated two large files in this project. Appending
touches nothing that already exists, so it cannot lose any of it.
"""
import io
import sys

staged, target = sys.argv[1], sys.argv[2]
with io.open(staged, encoding="utf-8") as fh:
    text = fh.read()
before = 0
with io.open(target, encoding="utf-8") as fh:
    before = len(fh.read())
with io.open(target, "a", encoding="utf-8", newline="\n") as fh:
    fh.write(text)
with io.open(target, encoding="utf-8") as fh:
    after = len(fh.read())
print("appended %d chars: %d -> %d" % (len(text), before, after))
if after != before + len(text):
    print("MISMATCH - check the target")
    sys.exit(1)
