# Quickstart

Two commands to see what this does, then one of your own.

Nothing here imports a package outside the Python standard library, so there is no install step for the
instrument itself. Node is only needed because the servers being measured are Node programs.

```
git clone https://github.com/arm00pv/memory-conformance
cd memory-conformance
npm ci --omit=optional      # the reference server, nothing that needs a compiler
```

`npm ci` without that flag also installs the seventeen optional subjects this repository measures. Several
build native extensions and one of them does not build under Python 3.12 at all, so the CI here installs
only what it needs and leaves the rest to whoever wants to measure them.

## 1. Does a memory server keep what it said it kept

```
python harness.py --adapter=auto \
  --cmd="node node_modules/@modelcontextprotocol/server-memory/dist/index.js"
```

```
probe            verdict                  time  evidence
---------------- ---------------------- ------  ----------------------------------------
isolation        PASS                     0.8s  store A's record was not visible from store B
ack_readback     PASS                     0.8s  acknowledged alpha; a fresh read returned 1 entities: ['alpha']
verbatim         UNKNOWN                  0.7s  a plain ASCII record written the same way does not come back either - not over the wire, and not from a store this harness can read - so this probe cannot see this subject's record bodies at all
restart          PASS                     1.4s  three writes across three server lifetimes; read back ['restart-0', 'restart-1', 'restart-2']
forget           PASS                     0.7s  asked to forget plinth-obsidian and the subject answered 'Entities deleted successfully'; after a restart the other two came back and it did not
findable         PASS                     1.0s  all 8 acknowledged records came back in the top 3 for a search on their own name
foreign_field    UNKNOWN                  0.5s  no store is declared for this subject, so the probe had nothing to inspect; add a manifest (see manifests/) to make it answerable
foreign_record   UNKNOWN                  0.5s  no store is declared for this subject, so the probe had nothing to inspect; add a manifest (see manifests/) to make it answerable
concurrent       PASS                     1.9s  20 of 20 acknowledged writes survived two servers on one store
large_record     UNKNOWN                  0.0s  adapter cannot measure record content; probe not applicable
0 probe(s) failed
```

**PASS, FAIL and UNKNOWN are three answers, and the third one is real.** UNKNOWN means the probe could not
be expressed against this server - not that the server is broken, and not that it is fine. Four of the ten
are UNKNOWN here for two different reasons, and both are printed rather than hidden: two probes need to
read bytes on disk and this subject's store is not declared, and two need to see a record's body and this
server's tools do not return one.

**`isolation` is a precondition, not a feature.** If it fails, every other verdict describes leaked state
and the run says so in a warning you cannot miss.

## 2. Your own server

```
python harness.py --adapter=auto --cmd="node /path/to/your-server.js"
```

`--adapter=auto` reads the tools your server publishes, builds an argument mapping from each tool's own
JSON schema, and **proves it by round-tripping a unique token before a probe runs**. A guess that is not
tested is a benchmark that lies, so a mapping that cannot be proven comes back UNKNOWN with the reason.

If your server's store is somewhere a human can read, declare it instead of letting the harness guess:

```
python harness.py --manifest=manifests/memdb.json --cmd="node node_modules/@j0hanz/memdb/dist/index.js"
```

The six manifests in `manifests/` are the shape to copy: a glob for the store files, how a record is
spelled inside one, and which field holds the body. With a manifest, `foreign_field`, `foreign_record`
and `verbatim` become answerable instead of UNKNOWN.

## 3. Does it find what it kept

Retention is not retrieval. This asks sixty questions at the same server, in four bands - easy,
paraphrased, adversarial, and twelve whose answer is not in the store:

```
python retrieval.py --adapter=auto --cmd="node node_modules/@modelcontextprotocol/server-memory/dist/index.js"
```

```
   MISS  easy     account locks five failed sign in attempts    want auth-lockout     got nothing
   ...
   MISS  adversarial How fast must ninety five percent of requests want latency-slo      got nothing
48 question(s) with an answer were missed at k=3; 0 of 12 questions with no answer were answered anyway
```

That is the reference server behaving exactly as its documentation implies: `search_nodes` matches a
literal substring, so a paraphrased question returns nothing. It keeps everything and finds almost
nothing, which is the distinction this whole repository is about.

## Exit codes

| code | meaning |
|---|---|
| 0 | no probe returned FAIL (UNKNOWN is not a failure) |
| 1 | at least one probe returned FAIL |
| 2 | `--expect=` was given and a pinned verdict moved |

`--expect=expected.json` turns a run into a regression detector: the pinned verdicts are the expectation,
a subject with a known defect stays green while it stays that way, and the job goes red the moment a vendor
fixes or breaks something. Three subjects are pinned this way in the CI for this repository, one of them
with a known refusal.

## Where the numbers are

This page is how to run it. The measurements are in [README.md](README.md) and in one generated report per
question:

| report | the question it answers |
|---|---|
| [RESOLUTION.md](RESOLUTION.md) | which pairs of subjects this corpus can and cannot separate |
| [BAND.md](BAND.md) | how many questions a near-tie would need, and what kinds of tie there are |
| [AGENT.md](AGENT.md) | what a caller with a token budget reads, against what the score counts |
| [MATRIX.md](MATRIX.md) | every probe against every subject, with the phrasing pair |
| [CLAIMS.md](CLAIMS.md) | every claim this repository has published, re-checked |
| [PRECISION.md](PRECISION.md) | what comes back besides the answer, and what it costs to read |
| [GROWTH.md](GROWTH.md) | what a write and a search cost at 5,000 records |

All of them are written by the tool named at the top of the file, from results committed under
`results/`. None is maintained by hand, and the CI regenerates every one of them on every push.
