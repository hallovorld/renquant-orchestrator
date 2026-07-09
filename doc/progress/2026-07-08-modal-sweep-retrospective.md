# Retrospective: Modal sweep — pipeline thinking and multi-repo architecture failures

**Date**: 2026-07-08
**Scope**: PR #435 (per-seed fan-out + data contract)
**Cost**: ~$2.25 in wasted Modal compute, ~6 hours of agent time,
7 review cycles of operator attention.

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

## 4. What was wasted vs. what was learned

| Wasted | Amount |
|--------|--------|
| Modal compute | ~$2.25 (structurally guaranteed to fail) |
| Agent time | ~6 hours across 7 rounds |
| Review cycles | 6 unnecessary operator interactions |
| Credibility | PR title: "validated" → "pending" → "still failing" → "PASS" |

| Learned | Deliverable |
|---------|-------------|
| Pipeline thinking | `data_contract.py` (verify_staged + verify_remote) |
| Multi-repo resolution | `RENQUANT_DATA_ROOT` pin + multi-path symlinks |
| Per-seed fan-out works | A/A Sharpe lift = +0.0000 (deterministic) |
| Cost-effective infra | $0.30 for a full smoke test once it works |

The data contract pattern is genuinely useful and reusable. The lesson is
that it should have been the FIRST thing built, not the last.
