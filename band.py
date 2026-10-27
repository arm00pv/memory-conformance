#!/usr/bin/env python3
"""band.py - a tie is three different things, and only one of them gets better with more questions.

THE TABLE HAS A TIE AT THE TOP AND THE WORD TIE IS DOING FOUR JOBS AT ONCE. resolution.py says which
pairs the corpus cannot separate; it does not say what kind of thing it failed to separate. Those are
different questions with different answers, and the difference is the one a reader choosing between two
servers actually needs:

  IDENTICAL      the two produce the same outcome on every question. No corpus separates them, because
                 there is nothing to separate.
  NO DIRECTION   they disagree on questions, but about equally in both directions. More questions do not
                 help: the win rate is a coin, and a larger coin is still a coin. Neither is better.
  SMALL BUT REAL one of them wins the disagreements consistently, and the corpus is too short to say so.
                 This is the only kind a bigger corpus fixes cheaply, and the price can be computed.
  OUT OF REACH   a margin exists, and separating it would take a corpus nobody would write. It is not a
                 limitation of this exam; it is a difference too small to spend a thousand questions on.

So this tool does two things resolution.py does not. It reports the DIVERGENCE behind each near-tie -
how many of the questions the two actually answered differently, which is the number a tie hides - and
it computes the PRICE of breaking one: how many questions would be needed, at the disagreement rate
that was observed, for the exact McNemar test to separate a split of that shape at 80% power.

The price is the useful part. A pair that disagrees on two questions out of sixty and a pair that
disagrees on twenty-eight of sixty can carry the same p value and have completely different futures:
the first is settled forever by being unimportant, the second just needs a longer exam.

  python band.py
"""
import itertools
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

import compare
import resolution

CORPORA = [("A", ""), ("B", "-b"), ("C", "-c")]
SHAPES = ("written", "keywords")
# FOUR QUESTIONS. The score and hits both credit the top three; hit1 asks only about the first record
# and top is what an agent with a token budget actually reads. They are not refinements of each other -
# retrieval_mutants.py measured that the score does not move when an answer moves from first to third.
METRICS = ("score", "hits", "hit1", "top")
TARGET_POWER = 0.80
CAP = 40000         # disagreements; above this, no question count separates a split this even
# A CORPUS NOBODY WILL WRITE IS NOT A MEASUREMENT PLAN. Past a thousand questions the honest report is
# not "ask more" but "this margin is real and not worth seeing", and the two deserve different words
# because one is a limitation of the exam and the other is a finding about the two subjects.
OUT_OF_REACH = 1000


def cell(pairs, corpus, shape, metric):
    """One ruler's pair table, looked up by name.

    A THREE-PART KEY AGAINST A FOUR-PART DICT IS THE BUG THIS REPOSITORY HAS WRITTEN THREE TIMES: in
    resolution.py it printed 0 of 0 for three phases, in the first draft of this file it printed three
    empty tables, and in claims.py it returned unmeasured for a corpus comparison that had already been
    computed. Each time a lookup returned an empty dict and each time the empty dict was formatted as a
    result. The key is not an interface just because it is in a variable.
    """
    suffix = dict(CORPORA)[corpus]
    return pairs.get((corpus, suffix, shape, metric)) or {}


def rulers():
    """Every way this repository orders the subjects: three corpora, two phrasings, two metrics."""
    return [(c, suffix, shape, metric)
            for c, suffix in CORPORA for shape in SHAPES for metric in METRICS]


_TOTALS = {}


def totals(suffix, shape, metric):
    """Every subject total on one ruler, read from the saved rows."""
    if (suffix, shape, metric) in _TOTALS:
        return _TOTALS[(suffix, shape, metric)]
    out = []
    for s in resolution.subjects():
        rs = resolution.rows_of(s["slug"], suffix)
        if not rs:
            continue
        vals = [resolution.outcome(r, shape, metric) for r in rs]
        vals = [v for v in vals if v is not None]
        if vals:
            out.append((sum(1 for v in vals if v), len(vals), s["label"], s["slug"]))
    _TOTALS[(suffix, shape, metric)] = out
    return out


_CRITICAL = {}


def logcomb(n, k):
    """binomial coefficient in log space, because 2**4000 does not fit in a float."""
    return math.lgamma(n + 1.0) - math.lgamma(k + 1.0) - math.lgamma(n - k + 1.0)


def critical(d):
    """The largest minority count the exact McNemar test still calls surprising, out of d.

    LOG SPACE, BECAUSE THE PRICE IS A BIG NUMBER. compare.exact_mcnemar divides math.comb(d, k) by 2**d,
    which is exact for the sixty questions this repository asks and raises OverflowError for the hundreds
    of questions a price search has to visit. Same test, same answer, no overflow.
    """
    if d in _CRITICAL:
        return _CRITICAL[d]
    base = d * math.log(2.0)
    total = 0.0
    best = -1
    for i in range(0, d // 2 + 1):
        total += math.exp(logcomb(d, i) - base)
        if 2.0 * total < 0.05:
            best = i
        else:
            break
    _CRITICAL[d] = best
    return best


def tail(d, q, k):
    """P(at most k wins out of d tries), in log space, for k small against d."""
    if k < 0:
        return 0.0
    if k >= d:
        return 1.0
    if q <= 0.0:
        return 1.0
    if q >= 1.0:
        return 0.0
    lq, l1q = math.log(q), math.log1p(-q)
    total = 0.0
    for i in range(0, k + 1):
        total += math.exp(logcomb(d, i) + i * lq + (d - i) * l1q)
    return min(1.0, total)


def power(d, q):
    """Chance of separating a split that favours one side with probability q, across d disagreements.

    BOTH TAILS, because the test is two-sided: a split is surprising when either side is rarely outvoted,
    so the power is the chance the winner is rarely outvoted plus the chance the loser rarely wins.
    """
    k = critical(d)
    if k < 0:
        return 0.0
    return min(1.0, tail(d, q, k) + tail(d, 1.0 - q, k))


def required_discordant(q, target=TARGET_POWER):
    """How many disagreements are needed, when one side wins them with probability q.

    NO DIRECTION IS NOT A SMALL SAMPLE. If q is a half, the power of the test never reaches the target at
    any number of questions - it converges to the false-positive rate - so the answer for a balanced split
    is not a bigger number, it is a different sentence. That distinction is why this returns None instead
    of a very large integer.

    BISECTION, BECAUSE A WALK IS NOT A CALCULATION ANYONE WILL WAIT FOR. Power rises with the number of
    disagreements, so the answer can be bisected - but the search has to be bounded somewhere, because
    a split of 51 to 49 needs about twenty thousand disagreements and a split of 50.5 to 49.5 needs two
    million. The bound is where the honest answer stops being a number and becomes a different problem.
    """
    if q is None or q <= 0.5:
        return None
    # the normal approximation is only used to place the upper bound of the search, never to report a
    # price - at a hundred disagreements the exact test and the approximation still differ by a few.
    est = ((1.959964 + 0.8416212) / (2.0 * q - 1.0)) ** 2
    hi = int(min(CAP, max(7, 4 * est + 100)))
    if power(hi, q) < target:
        return None
    lo = 6
    while lo < hi:
        mid = (lo + hi) // 2
        if power(mid, q) >= target:
            hi = mid
        else:
            lo = mid + 1
    # POWER IS NOT MONOTONE IN d, AND THE WAY IT FAILS IS WORTH KNOWING. The rejection threshold rises by
    # one minority vote every two disagreements, so a split that clears 80% at 149 disagreements drops
    # back to 78% at 153 and clears it again at 154 - a sawtooth, not a ramp. Bisection therefore lands
    # on a d that works rather than the first that works, so the window below it is walked back.
    for cand in range(max(6, lo - 200), lo):
        if power(cand, q) >= target:
            return cand
    return lo


def price(only_a, only_b, n, target=TARGET_POWER):
    """Total questions needed to separate this observed split, and how many more than were asked."""
    d = only_a + only_b
    if d == 0:
        return None, None, "identical"
    q = max(only_a, only_b) / float(d)
    need_d = required_discordant(q, target)
    if need_d is None:
        return None, None, "no-direction"
    rate = d / float(n)
    total = int(math.ceil(need_d / rate))
    return total, max(0, total - n), "real"


def kind(stats, need):
    """Which kind of tie this is, in the words a reader needs."""
    d = stats["only_a"] + stats["only_b"]
    if d == 0:
        return "IDENTICAL"
    if stats["separated"]:
        return "SEPARATED NOW"
    q = max(stats["only_a"], stats["only_b"]) / float(d)
    if q <= 0.5:
        return "NO DIRECTION"
    if need is not None and need > OUT_OF_REACH:
        return "OUT OF REACH"
    return "SMALL BUT REAL"


def stats_for(a_slug, b_slug, suffix, shape, metric):
    """One pair on one ruler: agreement, divergence, the paired verdict, and the price of a verdict."""
    ra, rb = resolution.rows_of(a_slug, suffix), resolution.rows_of(b_slug, suffix)
    if ra is None or rb is None:
        return None
    by = dict((r["query"], r) for r in rb)
    common = [r for r in ra if r["query"] in by]
    if not common:
        return None
    xa, xb = [], []
    for row in common:
        other = by[row["query"]]
        va, vb = resolution.outcome(row, shape, metric), resolution.outcome(other, shape, metric)
        if va is None or vb is None:
            continue
        xa.append(va)
        xb.append(vb)
    n = len(xa)
    if not n:
        return None
    stats = {"n": n,
             "both_ok": sum(1 for p, q in zip(xa, xb) if p and q),
             "both_no": sum(1 for p, q in zip(xa, xb) if not p and not q),
             "only_a": sum(1 for p, q in zip(xa, xb) if p and not q),
             "only_b": sum(1 for p, q in zip(xa, xb) if not p and q)}
    stats["a_slug"], stats["b_slug"] = a_slug, b_slug
    stats["p"] = compare.exact_mcnemar(stats["only_a"], stats["only_b"])
    stats["separated"] = stats["p"] < 0.05
    stats["differ"] = stats["only_a"] + stats["only_b"]
    need, more, which = price(stats["only_a"], stats["only_b"], n)
    stats["need"] = need
    stats["more"] = more
    stats["which"] = which
    stats["kind"] = kind(stats, need)
    return stats


def tops_of(ruler):
    """The subjects sharing the top of one ruler."""
    got = totals(ruler[1], ruler[2], ruler[3])
    if not got:
        return []
    got.sort(key=lambda t: (-t[0], t[2]))
    best = got[0][0]
    return [g[2] for g in got if g[0] == best]


def leaders_of(pairs_by_ruler):
    """Every subject that leads at least one ruler, and the rulers it leads."""
    out = {}
    for ruler in rulers():
        for name in tops_of(ruler):
            out.setdefault(name, []).append(ruler)
    return out


def contenders_of(pairs_by_ruler, leaders):
    """Every subject still in contention, which is a bigger set than the leaders.

    A SUBJECT CAN BE RUNNER-UP ON ALL TWELVE RULERS AND NEVER LEAD ONE. zenbrain leads no ruler here,
    and it is not separated from the leader on most of them, so calling it a non-contender would be a
    worse error than calling it a loser: it is in the same band, and the band is what is being
    described. Contention is defined from the separation relation rather than from the ordering.
    """
    out = set(leaders)
    for ruler in rulers():
        tops = set(tops_of(ruler))
        if not tops:
            continue
        for key, s in (pairs_by_ruler.get(ruler) or {}).items():
            if s["separated"]:
                continue
            for side, other in ((0, 1), (1, 0)):
                if key[side] in tops:
                    out.add(key[other])
    return sorted(out)


_ANALYSIS = {}


def analysis():
    """Every pair on every ruler, plus who leads and who is still in the band. Computed once.

    CACHED BECAUSE THE LEDGER USES IT TOO. claims.py asks this module the same question this module
    asks itself, and a claim that re-derived the whole table per corpus and phrasing would spend more
    time on arithmetic than the retrieval run it is judging.
    """
    if _ANALYSIS:
        return _ANALYSIS
    people = resolution.subjects()
    if len([s for s in people if resolution.rows_of(s["slug"], "")]) < 4:
        return {"people": people, "pairs": {}, "leaders": {}, "contenders": []}
    pairs = {}
    for ruler in rulers():
        cells = {}
        for a, b in itertools.combinations(people, 2):
            s = stats_for(a["slug"], b["slug"], ruler[1], ruler[2], ruler[3])
            if s:
                cells[tuple(sorted((a["label"], b["label"])))] = s
        pairs[ruler] = cells
    leaders = leaders_of(pairs)
    _ANALYSIS.update({"people": people, "pairs": pairs, "leaders": leaders,
                      "contenders": contenders_of(pairs, leaders)})
    return _ANALYSIS


def grounds(pairs, leaders, name):
    """The rulers that put a non-leading subject in contention, with the p that kept it there.

    A BAND WIDER THAN ITS LEADERS IS A FACT ABOUT THE DEFINITION, and a reader deserves to see which
    rulers admitted each member rather than being handed four names and no reason. One of these subjects
    is in contention on a single ruler, at p = 0.065, which is the "not separated is not similar" case
    admitted through the front door.
    """
    out = []
    for ruler in rulers():
        tops = tops_of(ruler)
        if name in tops:
            continue
        for key, s in (pairs.get(ruler) or {}).items():
            if s["separated"] or name not in key:
                continue
            if any(t in key for t in tops):
                out.append("%s %s %s at p = %.3f" % (ruler[0], ruler[2], ruler[3], s["p"]))
    return out


def main(argv=None):
    got = analysis()
    people = got["people"]
    if not got["pairs"]:
        print("not enough subjects with saved rows")
        return 1
    pairs = got["pairs"]
    for ruler in rulers():
        cells = pairs.get(ruler) or {}
        n_ties = sum(1 for s in cells.values() if not s["separated"])
        print("corpus %s, %-8s on %-5s: %2d of %2d pairs not separated by this ruler"
              % (ruler[0], ruler[2], ruler[3], n_ties, len(cells)))
    print()
    print("%d subjects lead a ruler, %d are within the band"
          % (len(got["leaders"]), len(got["contenders"])))
    write_md(os.path.join(HERE, "BAND.md"), people, got["leaders"], got["contenders"], pairs)
    return 0


def write_md(path, people, leaders, contenders, pairs):
    lines = []
    add = lines.append
    add("# What a tie means")
    add("")
    add("Generated by `band.py`. Do not edit by hand.")
    add("")
    add("`resolution.py` says which pairs this corpus cannot separate. This says what it failed to")
    add("separate, which is not the same question. A tie is one of four things, and only one of them is")
    add("fixed by asking more questions - another by asking different ones, and another by not asking.")
    add("")
    add("## Who is at the top, ruler by ruler")
    add("")
    add("A ruler is one corpus, in one phrasing, on one metric - twenty-four of them, and the answer is")
    add("not the same on all twenty-four. The four metrics are different questions: the score and the hit")
    add("count both credit the right record anywhere in the top three, hit@1 asks only about the first,")
    add("and the agent column is the first record back plus a correct silence.")
    add("")
    add("| corpus | phrasing | metric | top | at the top | margin over the next |")
    add("|---|---|---|---|---|---|")
    for ruler in rulers():
        got = totals(ruler[1], ruler[2], ruler[3])
        if not got:
            continue
        got.sort(key=lambda t: (-t[0], t[2]))
        best = got[0][0]
        at_top = [g[2] for g in got if g[0] == best]
        rest = [g for g in got if g[0] != best]
        margin = ("%d" % (best - rest[0][0])) if rest else "-"
        add("| %s | %s | %s | **%d of %d** | %s | %s |"
            % (ruler[0], ruler[2], ruler[3], best, got[0][1],
               ", ".join("`%s`" % n for n in at_top), margin))
    add("")
    add("### How many rulers each subject leads")
    add("")
    add("| subject | rulers at the top | of | rulers it leads |")
    add("|---|---|---|---|")
    total_rulers = len([r for r in rulers() if totals(r[1], r[2], r[3])])
    for name, rs in sorted(leaders.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        marks = ", ".join("%s %s %s" % (r[0], r[2], r[3]) for r in rs)
        add("| `%s` | **%d** | %d | %s |" % (name, len(rs), total_rulers, marks))
    add("")
    add("A subject that leads on some rulers and not others is not the leader of anything. It is the")
    add("answer to a question about which ruler was picked.")
    wider = [n for n in contenders if n not in leaders]
    if wider:
        add("")
        add("The band is wider than its leaders. These subjects lead nothing and are not separated from")
        add("someone who does, which is the whole of their claim to be in the tables below:")
        add("")
        for name in wider:
            add("- `%s` - %s" % (name, "; ".join(grounds(pairs, leaders, name)) or "no ground"))
    add("")
    counts = {}
    for ruler in rulers():
        for s in (pairs.get(ruler) or {}).values():
            counts[s["kind"]] = counts.get(s["kind"], 0) + 1
    add("## What kinds of tie there are")
    add("")
    add("Every pair on every ruler, classified by what the corpus failed to separate:")
    add("")
    add("| kind | pair-rulers | what it means |")
    add("|---|---|---|")
    add("| IDENTICAL | **%d** | the same outcome on every question, so nothing to separate |"
        % counts.get("IDENTICAL", 0))
    add("| NO DIRECTION | **%d** | they disagree, but evenly; no corpus separates a coin |"
        % counts.get("NO DIRECTION", 0))
    add("| SMALL BUT REAL | **%d** | one side wins the disagreements and the corpus is too short |"
        % counts.get("SMALL BUT REAL", 0))
    add("| OUT OF REACH | **%d** | a real margin, worth more than %d questions to resolve |"
        % (counts.get("OUT OF REACH", 0), OUT_OF_REACH))
    add("| SEPARATED NOW | **%d** | this ruler already separates them |"
        % counts.get("SEPARATED NOW", 0))
    add("")
    add("Only SMALL BUT REAL is a limitation of the question count. IDENTICAL needs no corpus, NO")
    add("DIRECTION needs a different corpus rather than a longer one because more questions of the same")
    add("kind raise both sides together, and OUT OF REACH is a margin that exists and does not matter")
    add("enough to pay %d questions for." % OUT_OF_REACH)
    add("")
    add("## The top of the table, pair by pair")
    add("")
    add("Every subject still in contention against every other, as written. **differ** is the number of")
    add("questions they answered differently - the divergence a tie hides - and the two numbers after it")
    add("say how the disagreements split between them. **would need** is the question count that would")
    add("separate a split of this shape at 80% power, so a price below the count asked means this corpus")
    add("was already long enough, and a price far above it means the tie is not a shortage of questions.")
    add("A price is an estimate from one observed split, and one split of thirteen gives a wide interval,")
    add("so it is a floor on the effort and not a guarantee of the outcome.")

    add("")
    add("### Corpus A, as written")
    add("")
    add("| pair | differ | split | p | kind | would need | asked |")
    add("|---|---|---|---|---|---|---|")
    by_label = dict((s["label"], s) for s in people)
    names = [n for n in contenders if n in by_label]
    for a, b in itertools.combinations(names, 2):
        key = tuple(sorted((a, b)))
        s = cell(pairs, "A", "written", "score").get(key)
        h = cell(pairs, "A", "written", "hits").get(key)
        if not s:
            continue
        first = s["only_a"] if s["a_slug"] == by_label[a]["slug"] else s["only_b"]
        second = s["differ"] - first
        extra = ""
        if h and h["kind"] != s["kind"]:
            extra = " (on hits: %s)" % h["kind"].lower()
        need = ("%d" % s["need"]) if s["need"] else "-"
        add("| `%s` vs `%s` | %d of %d | %d-%d | %.3f | **%s**%s | %s | %d |"
            % (a, b, s["differ"], s["n"], first, second, s["p"], s["kind"], extra, need, s["n"]))

    add("")
    add("### Corpus B, as written")
    add("")
    add("| pair | differ | split | p | kind | would need | asked |")
    add("|---|---|---|---|---|---|---|")
    by_label = dict((s["label"], s) for s in people)
    names = [n for n in contenders if n in by_label]
    for a, b in itertools.combinations(names, 2):
        key = tuple(sorted((a, b)))
        s = cell(pairs, "B", "written", "score").get(key)
        h = cell(pairs, "B", "written", "hits").get(key)
        if not s:
            continue
        first = s["only_a"] if s["a_slug"] == by_label[a]["slug"] else s["only_b"]
        second = s["differ"] - first
        extra = ""
        if h and h["kind"] != s["kind"]:
            extra = " (on hits: %s)" % h["kind"].lower()
        need = ("%d" % s["need"]) if s["need"] else "-"
        add("| `%s` vs `%s` | %d of %d | %d-%d | %.3f | **%s**%s | %s | %d |"
            % (a, b, s["differ"], s["n"], first, second, s["p"], s["kind"], extra, need, s["n"]))

    add("")
    add("### Corpus C, as written")
    add("")
    add("| pair | differ | split | p | kind | would need | asked |")
    add("|---|---|---|---|---|---|---|")
    by_label = dict((s["label"], s) for s in people)
    names = [n for n in contenders if n in by_label]
    for a, b in itertools.combinations(names, 2):
        key = tuple(sorted((a, b)))
        s = cell(pairs, "C", "written", "score").get(key)
        h = cell(pairs, "C", "written", "hits").get(key)
        if not s:
            continue
        first = s["only_a"] if s["a_slug"] == by_label[a]["slug"] else s["only_b"]
        second = s["differ"] - first
        extra = ""
        if h and h["kind"] != s["kind"]:
            extra = " (on hits: %s)" % h["kind"].lower()
        need = ("%d" % s["need"]) if s["need"] else "-"
        add("| `%s` vs `%s` | %d of %d | %d-%d | %.3f | **%s**%s | %s | %d |"
            % (a, b, s["differ"], s["n"], first, second, s["p"], s["kind"], extra, need, s["n"]))
    add("")
    add("## The honest reading")
    add("")
    add("A p value says whether a difference is visible. It does not say whether the difference is")
    add("worth seeing, and the two columns are where those come apart: two subjects that agree on")
    add("almost every question can carry the same p as two that agree on almost none, and only one of")
    add("those pairs is worth another corpus.")
    held = [(ruler, k, s) for ruler in rulers()
            for k, s in (pairs.get(ruler) or {}).items() if not s["separated"]]
    if held:
        widest = max(held, key=lambda t: t[2]["differ"])
        narrowest = min(held, key=lambda t: (t[2]["differ"], t[0][0], t[1]))
        apart = [t for t in held if t[2]["differ"] > 0]
        if apart:
            narrowest = min(apart, key=lambda t: (t[2]["differ"], t[0][0], t[1]))
        add("")
        add("The %d pair-rulers this instrument does not separate are not one population, and the" % len(held))
        add("distance between the two ends is what the word tie hides.")
        add("")
        add("**Almost the same subject.** `%s` vs `%s` on corpus %s %s %s: **%d of %d questions** were"
            % (narrowest[1][0], narrowest[1][1], narrowest[0][0], narrowest[0][2], narrowest[0][3],
               narrowest[2]["differ"], narrowest[2]["n"]))
        add("answered differently, p = %.3f. On almost every question these two are the same program,"
            % narrowest[2]["p"])
        add("and a corpus that separated them would have to be a corpus that asks something they do not")
        add("both already get right.")
        add("")
        add("**Two different programs, and no verdict.** `%s` vs `%s` on corpus %s %s %s:"
            % (widest[1][0], widest[1][1], widest[0][0], widest[0][2], widest[0][3]))
        add("**%d of %d questions** were answered differently, p = %.3f, and the totals differ by %d."
            % (widest[2]["differ"], widest[2]["n"], widest[2]["p"],
               abs(widest[2]["only_a"] - widest[2]["only_b"])))
        add("They fail different questions, and the instrument declines to rank them because the split")
        add("is near its line. Not separated is not the same as similar, and a reader choosing between")
        add("these two is choosing which failures to live with rather than which program is better.")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(chr(10).join(lines) + chr(10))
    print()
    print("written to %s" % path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))