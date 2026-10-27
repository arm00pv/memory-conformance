# What it costs

Moved here from `README.md` unchanged, so that page can stay an argument rather
than an archive. The numbers are the same numbers; the generated reports they quote are still
at the top of the repository.

## Cost: the third axis

```
$ python matrix.py --cost-only        # timings taken in a quiet pass of their own

subject                  startup  lst write write p50 search p50 resp B   amp     vary
control 1.0.0               0.23s    0.01s    0.009s    0.001s     4175     x72      0%
server-memory 1.0.0         0.89s    0.05s    0.021s    0.005s       39      x1     62%
server-memory 2.0.0         0.80s    0.03s    0.013s    0.005s       39      x1     69%
memento 0.7.0               1.42s    4.54s    0.111s    0.045s     1497     x26    293%
memdb 1.4.0                 0.42s    0.01s    0.001s    0.002s     1027     x18      0%
memory-lean 1.5.0           0.12s    0.01s    0.004s    0.002s      164      x3      0%
mcp-knowledge-graph 1.3.2   0.13s    0.01s    0.005s    0.003s       39      x1      0%
zenbrain 0.3.0              0.43s    0.01s    0.001s    0.002s      663     x11      0%
memory-mcp-1file 0.9.2      0.51s    1.56s    0.036s    0.055s     1969     x34     11%
```

`resp` is the median bytes a server sends back for one question, and `amp` is that divided by the size
of the correct record — so answering by returning the whole store shows up as a multiplier.

`vary` is how far the worst steady-state measurement moved across three passes, as a fraction of its
own median, and it is not a rounding detail. **memento's first write ranged from 2.3 s to 14.4 s**
across three passes on the same machine — the 4.54 s is a median of a six-fold spread, so an agent
runtime capping a tool call at 10 s faces a coin flip rather than a budget. `memory-mcp-1file`'s
response size moved 11% between passes: the byte count is exact for one response, and the response is
the subject's choice, which is why byte counts are repeated too.

**Read this table with the retrieval one, or the cheapest memory looks like the best.** The two
subjects that cost 39 bytes per question return *nothing*; efficiency achieved by silence is not
efficiency. The highest retriever (`memory-mcp-1file`, 42/60 as written and 42 as keywords) is also
among the most expensive per question at 34× the size of the answer. And one marketing claim survives
measurement intact:
`memory-lean` is genuinely lean — 164 bytes, 3×, and the fastest startup in the set.

**`store B/rec` is marginal, not average**, measured between two batches so the preallocation floor
cancels. Dividing total size by record count reported memento at 350,549 bytes per record; its true
marginal cost is **zero**, because its 4.3 MB store is allocated once and then holds anything.

The `ceil` column is the per-call ceiling each subject was given, and it changes verdicts. memento
passes `concurrent` at 180 s and fails it at 60 s on the same machine on the same day. A verdict is
only meaningful together with the ceiling it was measured under.

Two further subjects were measured before the current probe set and are not in the matrix:
[retained](https://github.com/arm00pv/retained) passed 6/6 including 50/50 concurrent writes across
two processes, and [basic-memory](https://github.com/basicmachines-co/basic-memory) 0.23.2 passed 4/6
with 2 unanswerable — `foreign_field` and `foreign_record` have no equivalent against a directory of
markdown notes. `retained` is the answer to the probe that fails: append-only, hash-chained,
read-back verified before the write is acknowledged.


## Cost is a function of depth, and every figure above was taken at the shallow end

The cost table times a write into an empty store and a search over the 72-record retrieval corpus.
Agents store thousands over months. `growth.py` takes each subject to **3000 records inside one server
lifetime** and times the writes and the searches as the store fills.

**Every subject costs more to search when the store is large, and memento costs enormously more.**

| subject | search at 100 records | at 2000 | growth |
|---|---|---|---|
| `memento` | 43-48 ms | **6.7-8.5 s** | **x140** |
| `control` | 1.3 ms | 20.1 ms | x61 |
| `mcp-duckdb-memory-server` | 20.3 ms | 594 ms | x54 |
| `memdb` | 7.8 ms | 62 ms | x25 |
| `statecore-mcp` | 2.3 ms | 11.7 ms | x6 |
| `memory-lean`, `mcp-knowledge-graph`, `zenbrain` | ~3 ms | 9-10 ms | x3 |
| `server-memory` 1.0.0 and 2.0.0 | 1.8-2.5 ms | 6.5-6.9 ms | x3 |

memento is the one that matters. On a 72-record store a search costs 5 ms and looks free; at 2000
records it costs **six to eight seconds**, in both runs, roughly doubling for every doubling past 500.
An agent with a ten-second tool budget loses it somewhere between five hundred and a thousand memories.

**The predictions were wrong in an instructive direction.** The rewrite-on-every-write server - the
architectural choice that loses fields, and the one predicted to make writes grow - shows no clear write
growth at all: rewriting a few hundred kilobytes is cheaper than the round trip carrying the write. What
did grow was the write cost of four subjects that are not rewriting anything wholesale, by 1.7x to 2.9x
at 2000 records, three of them reproducing in both runs.

So the honest reading of the cost table is that it is **not wrong, it is shallow**. Every figure in it
describes a memory holding under a hundred records, which is what the conformance and retrieval runs use.
The ledger's `search-is-flat` claim tests the obvious extrapolation and **FAILS**.

Full tables, both runs, in [`GROWTH.md`](../GROWTH.md).

## Cost is a function of depth, and the table now runs to five thousand

Every cost figure published here was once taken at a depth where the growth does not bite. The sweep now
reaches **5,000 records** for nine of the eleven subjects and 2,000 for the other two, with two to three
runs each. [`GROWTH.md`](../GROWTH.md)

| subject | write at 5 | at 2,000 | at 5,000 | **search at 5** | at 5,000 |
|---|---|---|---|---|---|
| `statecore-mcp` | 4.4 ms | 12.9 | **35.9** (×3.3 write) | 2.1 ms | **27.7 ms** |
| `mcp-duckdb-memory-server` | 14.5 ms | 21.5 | 44.0 | 8.3 ms | **2,187 ms** |
| `control` | 15.5 ms | 17.3 | 30.3 | 0.4 ms | **44.1 ms** |
| `memory-lean` | 5.6 ms | 10.4 | 14.1 | 2.1 ms | 13.8 ms |
| `mcp-knowledge-graph` | 7.2 ms | 12.9 | 15.9 | 3.7 ms | 14.1 ms |
| `memdb` / `zenbrain` | 1.5 ms | 1.0 / 0.9 | **0.5 / 0.7** | 1.8 / 1.5 ms | 70.6 / 9.9 ms |
| `memento` (to 2,000) | 157 ms | 81.6 | — | 105 ms | **8,454 ms** |
| `memory-mcp-1file` (to 2,000) | 57 ms | 44.9 | — | 113 ms | 98.8 ms |

**A search is not priced by the write table.** `duckdb` costs 8 ms at depth 5 and **2.2 seconds** at
5,000 — a factor of **264** — and five of eleven subjects grow their search by more than ten times in this
range. The write axis is the gentler one: the worst grower is `statecore-mcp` at ×3.3, and two subjects
get *cheaper* as the store fills.

**And the control is in the growing list, which it should not be.** Its write appends one line under a
lock — flat by construction — but it counts the records after every write to return a sequence number, and
counting means reading the whole store. At 500 records that read sat below the noise floor and the
prediction of flatness looked right; at 5,000 it is a fifth of the write cost. **The mechanism is mine, and
it is exactly the mistake every subject in this table is being measured for.**

Two subjects stop at 2,000 and both published why: `memento`'s search costs **8.5 seconds** at two thousand
records, and `1file` reads its whole store on every write. A curve that stops is more honest than one that
is extrapolated.
