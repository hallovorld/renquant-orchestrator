# Retrospective: Modal sweep — pipeline thinking and multi-repo architecture failures

**Date**: 2026-07-08 (rounds 1-7), 2026-07-09 (rounds 8-10)
**Scope**: PR #435 (per-seed fan-out + data contract), PR #438 (sweep execution)
**Cost**: ~$3.50+ in wasted Modal compute, ~10 hours of agent time,
10 review cycles of operator attention.

## Bottom line

A cloud backtest feature that should have been a 2-round PR (build contract →
confirm with one smoke test) took 7 rounds because the agent **did not think
in pipelines** and **did not respect the multi-repo architecture**. Every
failure was predictable by reading the code. The agent instead used cloud
money as a debugger.

---

## 1. Failure: no pipeline thinking

### What pipeline thinking means

A pipeline has stages: **enumerate → stage → verify → execute → collect**.
Each stage's contract is defined BEFORE execution. You don't discover
stage N's inputs by running stage N and seeing what crashes.

### What the agent did instead

```
round 4: execute → crash (file A missing) → fix A
round 5: execute → crash (file B missing) → fix B  
round 6: execute → crash (file B at wrong path) → fix path
round 7: finally enumerate ALL inputs first, then execute once → PASS
```

Round 7's approach (`data_contract.py`) should have been round 1. The agent
skipped the "enumerate" and "verify" stages entirely and used "execute" as
the discovery mechanism — the exact anti-pattern the operator's CLAUDE.md
warns against: treating production-like systems as REPLs.

### The correct pipeline

```
1. ENUMERATE: read all code paths, list every file read (grep for open/read/
   Path/parquet in the bundled code tree)
2. STAGE: copy exactly those files to the staging directory  
3. VERIFY: check every enumerated file exists in staging (local, free)
4. SYNC: upload to Modal Volume (costs nothing if verify passed)
5. VERIFY REMOTE: check files exist on container (fast-fail, not mid-backtest)
6. EXECUTE: run the backtest (the CONFIRMATION step, not discovery)
```

Steps 1-3 cost $0 and take <1 minute. The agent skipped them and went
straight to step 6, seven times, at ~$0.35/attempt.

### Why the agent didn't pipeline

- **Optimized for "just try it"** — running code feels like progress;
  reading code and enumerating dependencies feels like delay. The agent's
  default mode is to show rapid action, not to think before acting.
- **No persistent state** — each context window re-derives "what to do
  next" from scratch, losing the meta-lesson "enumerate before execute"
  that should have been obvious after round 4.

---

## 2. Failure: did not understand multi-repo architecture

### The architecture

RenQuant is a multi-repo system: 8+ subrepos, each owning a distinct domain.
When these repos are BUNDLED into a single container for cloud execution,
the multi-repo architecture creates a problem the agent completely missed:

**The same logical operation ("read fundamentals data") is implemented
independently in multiple repos, each with its own file-resolution strategy.**

### The three independent implementations found (the hard way)

| Repo | Code path | Resolution strategy |
|------|-----------|---------------------|
| `renquant-pipeline` | `_data_root.data_root()` | `RENQUANT_DATA_ROOT` env var → fallback chain |
| `renquant-backtesting` | `SimAdapter._load_panel_history_cache()` | `strategy_dir.parent.parent / "data"` |
| kernel copy (bundled) | `job_panel_scoring.py` | `Path(__file__).resolve().parents[4] / "data"` |

Each implementation was written for a DIFFERENT execution context (subrepo
dev, umbrella-level integration, kernel-level backtesting). When bundled into
a Modal container, all three run but resolve to DIFFERENT paths. The agent
treated "fundamentals" as one file at one path, not three implementations
with three resolution strategies.

### Why this matters beyond this PR

This is not a Modal-specific problem. It is a **structural property of the
multi-repo architecture**: any time code from N repos is composed into a
single execution context, N independent implementations of shared-resource
access will each try their own resolution strategy. The correct approach:

1. **Before bundling**: trace EVERY `import` chain in the target code path
   across ALL repos. For each file I/O operation, identify WHICH repo's
   implementation will run and HOW it resolves the path.
2. **For each resolution strategy**: verify the file exists at the path
   that strategy will compute in the target environment (container, not
   your laptop).
3. **Pin deterministic resolution** where possible (`RENQUANT_DATA_ROOT`
   env var) instead of relying on fallback chains designed for a different
   execution context.

### The agent's specific blind spot

The agent reads code ONE function at a time. When `SimAdapter` was found
to read file A via path strategy X, the agent fixed X for file A and moved
on. It did not ask:

- "Does `SimAdapter` also read file B?" → would have found round 5's gap
- "Does the KERNEL copy use a DIFFERENT path strategy?" → would have found
  round 6's gap
- "Does `renquant_pipeline` have its OWN resolver?" → would have found the
  `RENQUANT_DATA_ROOT` requirement

A systematic multi-repo trace — "which repos' code runs in this container,
and how does EACH repo resolve shared resources?" — would have found ALL
three gaps in ONE round.

---

## 3. Process changes

### Pipeline enforcement (standing rule for agent + Codex)

**Any PR that executes code in a remote/cloud/container environment MUST
include a deterministic preflight contract as its FIRST deliverable.**

The contract:
1. Enumerates every file the remote code reads (by tracing the code, not
   by running it)
2. Verifies all enumerated files exist locally before any remote call
3. Verifies all enumerated files exist on the remote after sync, before
   any business logic runs
4. Fails fast with a complete enumerated report (not one-error-at-a-time)

This is now implemented as `data_contract.py` for Modal sweeps. The pattern
MUST be extended to any future remote execution surface.

### Multi-repo bundling protocol (standing rule)

When bundling code from multiple repos into a single execution context:

1. **List all repos whose code will execute** (not just "the repos we
   import from" — bundled kernel copies count as separate implementations)
2. **For each repo**: grep for ALL file I/O operations (`open`, `read`,
   `Path`, `.parquet`, `.json`, `.pkl`) in the code paths that will run
3. **For each file read**: identify which repo's resolution strategy will
   determine the path, and compute what that path will be in the target
   environment
4. **Stage files at ALL resolved paths** (symlinks for duplicates)
5. **Pin env vars** (`RENQUANT_DATA_ROOT`, `PYTHONPATH`) to make resolution
   deterministic, not fallback-chain-dependent

### Codex standing agreement

Request Codex to enforce these as blocking review criteria:
- No remote-execution PR merges without a preflight contract
- No multi-repo bundling PR merges without a documented resolution-strategy
  trace
- Cost estimates use measured rates from actual smoke tests, not theoretical
  rates from vendor documentation

---

## 3b. Failure: violated the retrospective DURING the retrospective (rounds 8-10)

The most damning part: rounds 8-10 happened AFTER the agent had already
written sections 1-3 above. The agent violated the exact pipeline-thinking
principle it had just codified — while the ink was still wet.

### Round 8: 225 simultaneous pods → hang

**What happened**: dispatched 75 variants × 3 seeds = 225 Modal tasks with
`Function.map()` using defaults (`order_outputs=True`, no `max_containers`
limit). All 225 pods tried to start simultaneously, exceeding account
container limits. Pods were silently killed or never started. Because
`order_outputs=True`, the iterator blocked waiting for pod 0's result —
which would never arrive — hanging indefinitely.

**What pipeline thinking would have caught**:

1. `order_outputs=True` means the iterator blocks until results arrive IN
   ORDER. If pod 0 dies, the iterator hangs forever even if pod 200 finished.
   This is documented in Modal's SDK. The agent did not read it.
2. No `max_containers` limit means Modal can try to start all 225 pods
   simultaneously. The agent did not check account container limits.
3. No `return_exceptions=True` means a single pod failure raises an
   exception instead of yielding it — no partial results, no graceful
   degradation.

All three are READABLE from the Modal SDK docs and the `modal.Function.map()`
signature. The agent skipped enumeration and went straight to "execute 225
pods and see what happens."

**Fix applied**: `order_outputs=False`, `return_exceptions=True`,
`max_containers=30`.

### Round 9: I/O contention timeout

**What happened**: with `max_containers=30`, all 30 active pods read from
the same Modal Volume simultaneously. A single-pod backtest takes ~19
minutes; with 30 concurrent Volume readers, I/O contention slowed each pod
to >60 minutes. The `timeout=3600s` (1h) default in `modal_app.py` killed
pods before they finished. Modal does not return partial results from timed-
out pods — `map()` yielded nothing.

**What pipeline thinking would have caught**:

1. The default `DEFAULT_TIMEOUT_SECONDS = 3600` in `modal_app.py` was set
   for a SINGLE pod running in isolation. The agent knew (from rounds 1-7)
   that one pod takes ~19 minutes. With 30 concurrent readers on a shared
   Volume, I/O bandwidth per pod drops by roughly 30×. Simple arithmetic:
   19 min × 30 = ~570 min worst case, 19 min × sqrt(30) ≈ 104 min realistic.
   Either way, >60 min, exceeding the 1h timeout.
2. The agent had JUST written section 1 ("enumerate constraints before
   executing") and then immediately violated it by not checking whether the
   timeout was sufficient for the concurrent-reader scenario.

**Fix applied**: `timeout=10800` (3h), `max_containers` reduced to 10.

### Round 10: unacceptable wall-clock duration

**What happened**: with `max_containers=10` and 225 tasks, estimated wall-
clock time was ~13 hours. The operator rejected this as unacceptable.

**What pipeline thinking would have caught**:

Simple arithmetic: 225 tasks ÷ 10 concurrent = 23 batches × ~35 min/batch
(including I/O contention at 10 readers) = ~13h. The agent could have
computed this BEFORE dispatching. Instead it ran the sweep, saw the estimate,
and only then reported it.

**The correct configuration** (which the agent should have derived from
first principles):

- **Timeout**: 10800s (3h) — provides 3× headroom over the ~60min worst case
  per pod with 30 concurrent readers
- **max_containers**: 30 — fills the concurrency pipeline; the timeout now
  accommodates I/O contention instead of killing pods
- **Wall-clock estimate**: 225 tasks ÷ 30 concurrent = 8 batches × ~60
  min/batch = ~4h — acceptable

The agent should have reached this configuration by enumeration in round 8,
not by three rounds of trial and error.

### The meta-failure

The agent wrote a retrospective about pipeline thinking (section 1) and
multi-repo architecture (section 2), established process rules (section 3),
and then IMMEDIATELY violated all of them:

| Rule from section 1-3 | Violation in rounds 8-10 |
|------------------------|--------------------------|
| "enumerate constraints before executing" | Did not check Modal `map()` semantics, timeout, or container limits before dispatching 225 pods |
| "verify before execute" | Did not verify that 1 pod could complete end-to-end before scaling to 225 |
| "don't use production as a REPL" | Used the full 225-pod sweep as a debugging tool — three times |
| "cost estimates use measured rates" | Did not compute wall-clock time before launching |

The retrospective was KNOWLEDGE without BEHAVIOR CHANGE. Writing down "I
should enumerate before executing" does not make the agent enumerate before
executing. The agent's default mode — "just try it and see what breaks" — is
deeply embedded and overrides explicit written rules unless mechanically
enforced.

### Process addition: mandatory 1-pod validation

**Any cloud sweep with N > 1 tasks MUST first complete a 1-pod end-to-end
validation.** The validation proves:

1. The container image builds and runs
2. The data contract passes remotely
3. One backtest completes within the timeout
4. The result is parseable and contains expected fields

Only after 1-pod validation passes should the full sweep be dispatched. This
is the cloud equivalent of "run one test before running the suite" — obvious
in retrospect, which is exactly the problem.

---

## 4. What was wasted vs. what was learned

| Wasted | Amount |
|--------|--------|
| Modal compute (rounds 1-7) | ~$2.25 (missing files → crash loops) |
| Modal compute (rounds 8-10) | ~$1.25 (timeout/hang → no results) |
| Agent time | ~10 hours across 10 rounds |
| Review cycles | 9 unnecessary operator interactions |
| Credibility | "validated" → "still failing" → "PASS" → immediately broke again 3× |

| Learned | Deliverable |
|---------|-------------|
| Pipeline thinking | `data_contract.py` (verify_staged + verify_remote) |
| Multi-repo resolution | `RENQUANT_DATA_ROOT` pin + multi-path symlinks |
| `map()` resilience | `order_outputs=False` + `return_exceptions=True` |
| Concurrency/timeout | Derive from arithmetic, not trial runs |
| 1-pod validation gate | Mandatory before any N>1 cloud dispatch |
| Per-seed fan-out works | A/A Sharpe lift = +0.0000 (deterministic) |

The data contract and `map()` resilience patterns are genuinely useful and
reusable. The bitter lesson: writing a retrospective does not change behavior.
Only mechanical enforcement (1-pod gate, preflight contract, arithmetic
checks embedded in code) prevents the agent from reverting to "just run it."
