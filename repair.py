#!/usr/bin/env python3
"""repair.py - make a model-written corpus satisfy the validator, by regenerating only what fails.

A MODEL CAN WRITE A CORPUS; IT CANNOT CHECK ONE. The first corpus a model wrote here failed the
validator five different ways: thirteen records answering two questions, six unanswerable questions
that a single record actually covered, an adversarial question with nothing to compete against, and a
paraphrase that turned out to be a keyword match. None of those are reasons to throw the corpus away -
they are the validator doing exactly what it exists for, one band at a time.

So: validate, categorise, regenerate the failures from the same model, repeat until clean. The rules
are read from validate_corpus rather than restated here, because two copies of a rule is how this
repository has recorded the same defect three times.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

import author  # noqa: E402
import validate_corpus  # noqa: E402

COUNTS = {'easy': 16, 'hard': 16, 'adversarial': 16, 'absent': 12}


def check_in_memory(doc, tmp='.repair-check.json'):
    with open(tmp, 'w', encoding='utf-8', newline=chr(10)) as fh:
        fh.write(json.dumps(doc) + chr(10))
    try:
        return validate_corpus.check(tmp)
    finally:
        os.unlink(tmp)


def coverage(text, question):
    """The share of the question content words a single record covers."""
    q = set(validate_corpus.tokens(question))
    if not q:
        return 1.0
    return len(q & set(validate_corpus.tokens(text))) / float(len(q))


def tokens(text):
    return set(validate_corpus.tokens(text))


def unused_records(doc, taken):
    return [r for r in doc["records"] if r["id"] not in taken]


def repair(doc, model, rounds=8):
    for round_no in range(rounds):
        errors, _warn, _facts = check_in_memory(doc)
        if not errors:
            print("clean after %d round(s)" % round_no)
            return True
        texts = dict((r['id'], r['text']) for r in doc['records'])
        by_band = dict((b, [q for q in doc['queries'] if q['difficulty'] == b]) for b in COUNTS)
        changed = False

        # 1. one question per record
        seen = set()
        keep = []
        for q in doc['queries']:
            want = q.get('expect')
            if want and want in seen:
                changed = True
                continue
            if want:
                seen.add(want)
            keep.append(q)
        doc['queries'] = keep

        # 2. absent questions a single record covers
        fixed = []
        for q in doc['queries']:
            if q['difficulty'] != 'absent':
                fixed.append(q)
                continue
            worst = max([coverage(t, q['query']) for t in texts.values()] or [0.0])
            if worst >= validate_corpus.__dict__.get('ABSENT_COVER', 0.5):
                print('  drop absent (covered %.2f): %s' % (worst, q['query'][:60]))
                changed = True
                continue
            fixed.append(q)
        doc['queries'] = fixed

        # 3. adversarial questions with nothing competing
        fixed = []
        for q in doc['queries']:
            if q['difficulty'] != 'adversarial':
                fixed.append(q)
                continue
            target = texts.get(q.get('expect'), '')
            core = tokens(q['query']) & tokens(target)
            rivals = [rid for rid, t in texts.items()
                      if rid != q.get('expect') and (core & tokens(t))]
            if rivals:
                fixed.append(q)
            else:
                print('  drop adversarial (no rival): %s' % q['query'][:60])
                changed = True
        doc['queries'] = fixed

        # 4. hard questions that share more than the allowed words
        fixed = []
        for q in doc['queries']:
            if q['difficulty'] != 'hard':
                fixed.append(q)
                continue
            target = texts.get(q.get('expect'), '')
            if len(tokens(q['query']) & tokens(target)) <= 1:
                fixed.append(q)
            else:
                print('  drop hard (keyword match): %s' % q['query'][:60])
                changed = True
        doc['queries'] = fixed

        # 5. top every band back up
        taken = set(q.get('expect') for q in doc['queries'] if q.get('expect'))
        for band, want in COUNTS.items():
            have = sum(1 for q in doc['queries'] if q['difficulty'] == band)
            need = want - have
            if need <= 0:
                continue
            print("  topping up %s: %d" % (band, need))
            if band == 'absent':
                doc['queries'].extend(fill_absent(doc, model, need))
            else:
                pool = unused_records(doc, taken)
                for rec in pool[:need]:
                    rival = best_rival(doc, rec['id'])
                    q = author.one_question(model, band, rec['id'], rec['text'], rival)
                    if not q:
                        continue
                    if band == 'hard' and len(tokens(q) & tokens(rec['text'])) > 1:
                        continue
                    if band == 'adversarial':
                        core = tokens(q) & tokens(rec['text'])
                        if not any(core & tokens(t) for rid, t in texts.items() if rid != rec['id']):
                            continue
                    doc['queries'].append({'query': q, 'expect': rec['id'], 'difficulty': band})
                    taken.add(rec['id'])
            changed = True
        if not changed:
            print("  no fix applied; stopping")
            return False
    errors, _warn, _facts = check_in_memory(doc)
    return not errors


def best_rival(doc, target_id):
    """A record that already shares words with the target, so the model has something to build a trap on."""
    texts = dict((r['id'], r['text']) for r in doc['records'])
    target = tokens(texts[target_id])
    best, score = None, 0
    for rid, text in texts.items():
        if rid == target_id:
            continue
        n = len(target & tokens(text))
        if n > score:
            best, score = rid, n
    return (best, texts[best]) if best else None


def fill_absent(doc, model, need):
    texts = [r["text"] for r in doc["records"]]
    out = []
    for _ in range(need * 3):
        if len(out) >= need:
            break
        q = author.one_question(model, 'absent-question', '', '', None)
        if not q:
            continue
        if max([coverage(t, q) for t in texts] or [0.0]) >= 0.5:
            continue
        out.append({'query': q, 'expect': None, 'difficulty': 'absent'})
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    path = "retrieval_corpus_c.json"
    model = "glm-5.3:cloud"
    for a in argv:
        if a.startswith("--path="):
            path = a.split("=", 1)[1]
        elif a.startswith("--model="):
            model = a.split("=", 1)[1]
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    ok = repair(doc, model)
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + chr(10))
    errors, warn, facts = validate_corpus.check(path)
    print("errors %d, warnings %d, bands %s" % (len(errors), len(warn), facts.get("bands")))
    for e in errors[:8]:
        print("   " + e[:150])
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())