#!/usr/bin/env python3
"""author.py - have a DIFFERENT model write a corpus, so the corpora stop sharing an author.

THE LONGEST-STANDING LIMIT IN THIS REPOSITORY. Both retrieval corpora were written by the same hand and
the same model family as the analysis that grades them, so 'corpus B replicates corpus A' is weaker than
it reads: a shared blind spot is indistinguishable from a finding. The only fix is a corpus written by
something that has never seen the analysis, and this file gets one from a local or cloud model.

WHAT THE MODEL IS GIVEN, AND WHAT IT IS NOT

  given:  the band definitions and the structural rules the validator enforces, because a corpus that
          does not parse is not a test of anything; and a one-paragraph brief for a new world.
  not given: corpus A, corpus B, any question from either, any result, any analysis, the name of any
          subject, or the fact that this is a benchmark at all.

The distinction is recorded in the output file: an author who knows the rules is still an independent
author, but an author who has read the answers is not.

  python author.py --model=glm-5.3:cloud --out=retrieval_corpus_c.json
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
API = "http://127.0.0.1:11434/api/chat"

WORLD = (
    'a municipal observatory: telescopes, a public archive of night-sky photographs, weather'
    ' instruments, a staff rota, a gift shop, a weather station on the roof, and a committee that'
    ' meets quarterly. Write about that. Do not write about software, servers, deployments, railways,'
    ' or anything that sounds like an IT department or a train operator.'
)

COUNTS = {"easy": 16, "hard": 16, "adversarial": 16, "absent": 12}
RECORDS = 72

RECORD_SHAPE = '''[
  {"id": "short-hyphenated-slug", "text": "the fact, in one or two sentences"}
]'''

BAND_RULES = {
    'easy': ('EASY: the question reuses the wording of its answer record. At least half of the',
             'question content words must appear in that record. It should be findable by a keyword',
             'search.'),
    'hard': ('HARD: the question is a paraphrase sharing AT MOST ONE content word with its answer',
             'record. Write it the way a person asks who does not remember the wording: use other',
             'words entirely, while keeping it answerable from that record alone.'),
    'adversarial': ('ADVERSARIAL: the question reaches its answer through a word that ALSO appears in a',
                    'different record, so a keyword search is drawn to the wrong one. Two records must',
                    'compete for it. It must still be answerable only from the record you name.'),
    'absent': ('ABSENT: the institution plausibly would know this, but NO record contains it and no',
               'record answers it. The right behaviour is to return nothing. Give no expect field.'),
}


def ask(model, prompt, num_predict=6000, temperature=0.9):
    # THINKING IS BILLED TO THE SAME BUDGET AS THE ANSWER. A reasoning model spent 1,700 of 2,200 tokens
    # deliberating and had its JSON cut off mid-array, which read as "the model produced nothing" until
    # done_reason said length. It is switched off here; the job is to write 24 records, not to reason
    # about them.
    body = json.dumps({
        "model": model, "stream": False, "think": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"num_predict": num_predict, "temperature": temperature},
    }).encode()
    req = urllib.request.Request(API, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        doc = json.load(r)
    return ((doc.get("message") or {}).get("content") or "").strip()


def json_of(text, want):
    """The LAST balanced JSON value of the wanted kind, scanned backwards.

    NOT THE FIRST '[' TO THE LAST ']'. A reasoning model echoes the output template back inside its own
    thinking before answering, so the reply contains a second, fake array - the shape example from the
    prompt - and slicing from the first opener to the last closer spans both and parses as neither. The
    real answer is the last one, so the scan runs from the end and takes the first thing that decodes.
    """
    dec = json.JSONDecoder()
    for i in range(len(text) - 1, -1, -1):
        if text[i] not in "[{":
            continue
        try:
            got, _end = dec.raw_decode(text[i:])
        except ValueError:
            continue
        if isinstance(got, want):
            return got
    return None


def records_pass(model, start, count, theme, tries=3):
    prompt = (
        WORLD + chr(10) + chr(10)
        + "Write %d short factual records, numbered %d to %d, for this institution. Each is one or two"
          " sentences a real institution would have written down: a fact, a figure, a name, a schedule,"
          " a rule. Theme for this batch: %s."
          + chr(10) + chr(10)
        + "Reply with ONLY a JSON array, no prose, shaped exactly like:"
          + chr(10) + RECORD_SHAPE + chr(10)
        + "Every id must be unique, lowercase and hyphenated, with no digits."
    ) % (count, start, start + count - 1, theme)
    for _ in range(tries):
        got = json_of(ask(model, prompt), list)
        rows = []
        for item in (got or []):
            if not isinstance(item, dict):
                continue
            rid = str(item.get("id") or "").strip()
            text = str(item.get("text") or "").strip()
            if rid and text:
                rows.append({"id": rid, "text": text})
        if len(rows) >= count:
            return rows[:count]
    return []


def band_prompt(band, records, count):
    listing = chr(10).join("- %s: %s" % (r["id"], r["text"]) for r in records)
    if band == 'absent':
        shape = '[{"query": "...", "difficulty": "absent"}]'
        expect = 'Do not include an expect field at all.'
    else:
        shape = '[{"query": "...", "expect": "record-id", "difficulty": "%s"}]' % band
        expect = 'expect is the id of the record that answers it.'
    return (
        WORLD + chr(10) + chr(10)
        + "Here are the records in the store:" + chr(10) + listing + chr(10) + chr(10)
        + " ".join(BAND_RULES[band])
        + chr(10) + chr(10)
        + "Write %d questions for the %s band. %s" % (count, band, expect)
        + chr(10) + chr(10)
        + "Reply with ONLY a JSON array, no prose, shaped exactly like:" + chr(10) + shape
        + chr(10)
        + "Every question is a full question or sentence in natural English, and no two questions are"
          " about the same fact."
    )


ONE_ASK = '''
Write ONE question for the %s band.

Record %s: %s
%s
%s

Reply with ONLY a JSON array containing one object, no prose:
[{"query": "...", "expect": "%s", "difficulty": "%s"}]
'''


ABSENT_ASK = '''
%s

Write ONE question about this institution that NO record in the store answers, and that no single
record mostly covers. It must be a plausible question a visitor would ask, phrased without the
distinctive words of anything the institution has actually written down.

Reply with ONLY a JSON array containing one object, no prose:
[{"query": "...", "difficulty": "absent"}]
'''


def one_question(model, band, target, text, rival=None, tries=2):
    """A single question per call.

    THE WHOLE BAND AT ONCE DOES NOT WORK FOR THIS MODEL. Asking for sixteen hard paraphrases makes it
    deliberate for thousands of tokens and truncate before writing anything; asking for one makes the
    task small enough to finish. The corpus still wants sixteen, so it is assembled sixteen times.
    """
    if band == 'absent-question':
        for _ in range(tries):
            got = json_of(ask(model, ABSENT_ASK % WORLD), list)
            for item in (got or []):
                if isinstance(item, dict) and str(item.get("query") or "").strip():
                    return str(item["query"]).strip()
        return ""
    if band == 'hard':
        rule = ('The question must share AT MOST ONE content word with the record: use other words'
                ' entirely, the way a person asks who cannot remember the wording, while keeping it'
                ' answerable from this record alone.')
        rival_line = ''
    else:
        rule = ('The question must reach the record through a word that ALSO appears in the competing'
                ' record below, so a keyword search is drawn to the wrong one - but it must be'
                ' answerable only from the record above.')
        rival_line = ('Competing record %s: %s' % rival) if rival else ''
    for _ in range(tries):
        got = json_of(ask(model, ONE_ASK % (band, target, text, rule, rival_line, target, band)), list)
        for item in (got or []):
            if isinstance(item, dict) and str(item.get("query") or "").strip():
                return str(item["query"]).strip()
    return ""


# HOW MANY QUESTIONS TO ASK FOR AT ONCE, BY BAND. The easy and absent bands come back in one reply of
# sixteen; the hard and adversarial bands make this model deliberate for thousands of tokens before it
# writes anything, and a large ask gets truncated mid-thought with no JSON at all. Small asks are
# accumulated instead - the constraint is the model's budget, not the corpus's requirement.
CHUNK = {"easy": 16, "hard": 3, "adversarial": 3, "absent": 12}


def questions_pass(model, band, records, count, attempts=14):
    ids = set(r["id"] for r in records)
    rows, seen = [], set()
    if band in ("hard", "adversarial"):
        # ONE AT A TIME, walking the store, so each answer is a small task the model can finish.
        for i, rec in enumerate(records):
            if len(rows) >= count:
                break
            rival = records[(i + 7) % len(records)] if band == "adversarial" else None
            q = one_question(model, band, rec["id"], rec["text"],
                             (rival["id"], rival["text"]) if rival else None)
            if q and q.lower() not in seen:
                seen.add(q.lower())
                rows.append({"query": q, "expect": rec["id"], "difficulty": band})
            print("   %s %d/%d" % (band, len(rows), count), flush=True)
        return rows[:count]
    chunk = CHUNK.get(band, 4)
    for _ in range(attempts):
        if len(rows) >= count:
            break
        need = min(chunk, count - len(rows))
        got = json_of(ask(model, band_prompt(band, records, need)), list)
        for item in (got or []):
            if not isinstance(item, dict):
                continue
            q = str(item.get("query") or "").strip()
            want = str(item.get("expect") or "").strip()
            if not q or q.lower() in seen:
                continue
            if band == 'absent':
                seen.add(q.lower())
                rows.append({"query": q, "expect": None, "difficulty": band})
            elif want in ids:
                seen.add(q.lower())
                rows.append({"query": q, "expect": want, "difficulty": band})
    return rows[:count]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    model = "glm-5.3:cloud"
    out = "retrieval_corpus_c.json"
    reuse = False
    for a in argv:
        if a == "--reuse":
            # KEEP THE RECORDS, REGENERATE THE QUESTIONS. The record batches are slow and were fine;
            # the question bands are the ones that needed a different shape of ask.
            reuse = True
        if a.startswith("--model="):
            model = a.split("=", 1)[1]
        elif a.startswith("--out="):
            out = a.split("=", 1)[1]
    # SMALLER BATCHES, because a truncated array is indistinguishable from a refusal and both look like
    # "the model produced nothing".
    themes = [
        "the telescopes and their instruments",
        "the domes, the clocks and the roof",
        "the public archive of night-sky photographs",
        "the weather station and its instruments",
        "staff, the rota and the volunteers",
        "the shop, the events and the committee",
    ]
    records = []
    if reuse and os.path.isfile(out):
        with open(out, encoding="utf-8") as fh:
            records = (json.load(fh).get("records") or [])
        print("reusing %d records from %s" % (len(records), out), flush=True)
    per = RECORDS // len(themes)
    for i, theme in enumerate(themes):
        if len(records) >= RECORDS:
            break
        got = records_pass(model, i * per, per, theme)
        print("records %d-%d: %d" % (i * per, i * per + per - 1, len(got)), flush=True)
        records.extend(got)
    # ONE BAD BATCH IS NOT A FAILED CORPUS. A model asked for twelve records returns none often enough
    # to matter, so the shortfall is filled by asking again rather than by giving up on seventy-two.
    for attempt in range(4):
        if len(records) >= RECORDS:
            break
        need = RECORDS - len(records)
        print("filling %d more records (attempt %d)" % (need, attempt + 1), flush=True)
        more = records_pass(model, len(records), min(need, 12),
                            "anything else about this institution not yet written down")
        records.extend(more)
    if len(records) < RECORDS:
        print("only %d records after filling; stopping" % len(records))
        return 1
    queries = []
    for band, count in COUNTS.items():
        got = questions_pass(model, band, records, count)
        print("%s: %d of %d" % (band, len(got), count), flush=True)
        queries.extend(got)
    doc = {
        "why": ("written by %s, which has never seen corpus A, corpus B, any question from either, or"
                " any result from this repository; it was given the band rules and a world brief,"
                " and nothing else" % model),
        "authored_by": model,
        "authored_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "records": records,
        "queries": queries,
    }
    with open(out, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + chr(10))
    print("wrote %s: %d records, %d questions" % (out, len(records), len(queries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())