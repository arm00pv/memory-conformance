# memory-conformance

**Memory systems claim to remember. This measures whether they keep what they acknowledged.**

A memory server answers `ok` and you move on. That answer is a promise about bytes, and almost
nobody tests it: the write is accepted, the record is gone, and the failure is discovered weeks later
by someone who trusted it. These are conformance probes for that promise, run against a server's own
public tools over its own transport - no internals, no mocks, no source reading.

```
$ python harness.py --cmd="node node_modules/@modelcontextprotocol/server-memory/dist/index.js"
ack_readback     PASS      0.7s  acknowledged alpha; a fresh read returned 1 entities: ['alpha']
restart          PASS      1.9s  three writes across three server lifetimes; read back [restart-0, ...]
foreign_field    FAIL      1.2s  the extra field was silently dropped by the next write
foreign_record   PASS      1.1s  the unmodelled record survived
concurrent       PASS      1.6s  20 of 20 acknowledged writes survived two servers on one store
large_record     PASS      0.7s  wrote 100000 characters, read back 100000
1 probe(s) failed
```

## The six probes

| probe | the promise it tests |
|---|---|
| `ack_readback` | a write that returned success is returned by a fresh read |
| `restart` | the write survives the server being stopped and started |
| `foreign_field` | a field the server does not model survives the next write |
| `foreign_record` | a record type the server does not model survives the next write |
| `concurrent` | two servers on one store keep every acknowledged write (threads, one server each, released together) |
| `large_record` | a 100,000-character record comes back whole |

Every probe drives the server through MCP `tools/call` and then checks both the answers over the
wire and the bytes on disk. Each runs against a fresh store in a temporary directory, so probes
cannot contaminate each other.

## Result: `@modelcontextprotocol/server-memory@1.0.0`

**1 of 6 failed.** Node 24.19.0, Python 3.14.7, Windows, 2026-10-19.

`foreign_field`, reproduced:

1. the server acknowledges an entity,
2. a human (or another tool) adds a field to that entity in the JSONL store - `"reviewed_by": "a human"`,
3. the server is restarted and accepts one more write,
4. the annotated field is **gone**, and nothing in any reply said so.

The store is rewritten from the server's own parsed model on every mutation, so anything the model
does not represent is discarded at the next write. A tool that writes to the same store - a script,
another MCP client, a person with an editor - cannot tell that its data was dropped.

The record-level probe passes: a whole line whose `type` the server does not model did survive the
next write in this version. So the loss is **field-level**, not line-level, and the two should not be
confused when reading bug reports.

## Two probe-design errors this harness caught in itself

- **The concurrency probe was not a race.** The first version ran writer 0 to completion and then
  writer 1, which is a sequence: each write read the file the previous one had already rewritten, so
  "20 of 20 survived" proved nothing. Fixed with two threads released together.
- **It still passes at 100 writes** ("100 of 100 survived", 3.5 s). A widely reported lost-update
  pattern for this server does not reproduce here in this version, and saying so is part of the job:
  a conformance suite that only ever confirms the folklore is not measuring anything.

## The positive control: the probes can pass

A suite that only ever fails measures nothing. `control/memory_server.py` is the smallest MCP memory
server built so that all six probes pass, and it is the opposite decision from the server that fails:
**append-only, never rewrite**, with an OS lock around the append and a read-back before the write is
acknowledged. Unknown fields, unknown record types and concurrent writers survive by construction
rather than by care.

```
$ python harness.py --adapter=control --cmd="python control/memory_server.py"
ack_readback     PASS   acknowledged alpha; a fresh read returned 1 entities
restart          PASS   three writes across three server lifetimes; all read back
foreign_field    PASS   the extra field survived the next write
foreign_record   PASS   the unmodelled record survived
concurrent       PASS   50 of 50 acknowledged writes survived two servers on one store
large_record     PASS   100,000 characters written, 100,000 read back
0 probe(s) failed
```

**The control lost 4 of 20 concurrent writes on its first version.** It relied on `O_APPEND` alone,
and on Windows the write position is fixed when the file is opened, so two processes appending at once
write to the same offset and clobber each other. Adding an OS lock (`msvcrt.locking` on Windows,
`flock` on POSIX) took it to 0 losses in 5 consecutive runs of 50 concurrent writes. That is the same
failure the reference server is reported to have, reproduced on demand - and it is why the concurrency
probe is worth running.

## The three subjects measured so far

| subject | adapter | result |
|---|---|---|
| `@modelcontextprotocol/server-memory@1.0.0` | `reference` | 5/6 - fails `foreign_field` |
| `control/memory_server.py` | `control` | 6/6 |
| [retained](https://github.com/arm00pv/retained) | `retained` | **6/6** - including 50/50 concurrent writes across two processes |

`retained` is the answer to the probe that fails: append-only, hash-chained, read-back verified before
the write is acknowledged, so a field the server does not model cannot be lost by it.

## Adding a system

The harness talks MCP over stdio, so any MCP server can be probed by changing `--cmd`. A system with
a different tool vocabulary needs a small adapter: implement `server()`, `write()`, `read()` and pass
it to the probes - `ReferenceAdapter` in `harness.py` is 20 lines and is the template.

## Why this exists

It comes out of [silentfail](https://github.com/arm00pv/silentfail): the same doctrine, that a system
reporting success while doing nothing is the defect class worth engineering against, pointed at the
one place where it is least examined. The failure this probe found is silent by construction - the
success reply is honest about the write and silent about the loss.

## Limits, stated

- **One server, one version.** Numbers above are `@modelcontextprotocol/server-memory@1.0.0` on
  2026-10-19, and a different version can pass or fail differently.
- **Six probes are not a spec.** They cover retention and concurrency, not retrieval quality, latency
  or token cost.
- **Probes are deterministic, not sampled.** There is no confidence interval to quote; a probe either
  reproduces or it does not, and each one prints what it saw.

MIT licensed.
