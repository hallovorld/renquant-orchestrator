# GOAL-5 — five detectors merged in one night, invoked by nothing; three now run

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-5 (P0)

## The finding, about my own output

Measured `[本次实测 2026-08-01]` — `git grep` over `ops/*.sh`, `ops/*.json`, `scripts/`,
`Makefile` and every installed plist, for each detector merged on 2026-07-31:

| detector | on main | invoked by |
|---|---:|---|
| `renquant104/gate_stamp_parity.py` | yes | **nothing** |
| `bundle_producer_key_audit.py` | yes | **nothing** |
| `renquant104/wf_corpus_coverage.py` | yes | **nothing** |
| `renquant104/booster_identity_census.py` | yes | **nothing** |
| `strategy_config_primary_parity.py` | yes | **nothing** |

**Five for five.** `ops/ops_audit.py` exists precisely for this — it was built after
issue #649 measured that 17 of 24 `ops/` tools were unscheduled, including GOAL-5's AC5
detector that had **never run**. I then merged five more into the same condition on the
same night. *Deployed and dark* is a rule this repo already has; I broke it five times.

## Why they were dark — a design mismatch, not an oversight

Every existing member is invoked with **no arguments** and resolves its own paths. Four of
my five **require** `--root` / `--config`, so scheduling them would mean baking an absolute
path into the reviewed `MEMBERS` tuple — the *"tests that measure the operator's disk"*
failure, in the one file whose whole job is to be portable.

So the fix is in the tools, not the tuple.

## What this change does

**Three detectors join**, each argument-free or carrying only a portable glob:

- `gate_stamp_parity` and `booster_identity_census` gain a resolved default root. The
  first attempt used `runtime_paths.default_data_root()` — the repo's canonical answer —
  and returned **nothing**, because `ops/` scripts run as plain files and
  `renquant_orchestrator` is not importable without `PYTHONPATH`. The chain now tries
  `RENQUANT_DATA_ROOT`, then the package, then derives the umbrella root from the file's
  own location.
- `bundle_producer_key_audit` needed no change.

**An unresolvable root returns `""` deliberately**, so each tool's own *"no subjects"*
guard exits **non-zero**. An empty scan must never read as a clean one — and that is what
the failed first attempt did correctly, which is how the `PYTHONPATH` gap was found.

**Two are recorded as blocked, not silently omitted** — `UNSCHEDULABLE_YET`, with a test
asserting both that the list is exactly those two and that a blocker cannot also be a
member. *"The audit covers the detectors"* must not be readable off a list that quietly
excludes two of them.

Finding contracts are cited **to the line**, matching the standard the existing six are
held to.

## Verified

`python ops/ops_audit.py` with no arguments, aggregate **exit 1**:

```
[findings] gate-stamp-parity      exit=1  30 artifact(s) scanned — 15 carry BOTH copies …
[findings] booster-identity       exit=1  30 artifact(s) under prod/panel-ltr…
[findings] bundle-producer-keys   exit=1  shared schema declares : […]
```

Suite: **5081 passed, 2 skipped**.

## Two exit codes I misread getting here

1. I reported `rc=0` for both new members after adding the default root, and nearly filed
   a silent regression against my own change. The `0` was from
   `echo "rc=$?  |  $(grep …)"` — the command substitution ran first and clobbered `$?`.
   Captured on its own line, both are **rc=1** with identical findings. **Third time
   tonight**; the rule is to capture `$?` immediately, on its own line, before anything
   else runs.
2. The suite then failed on `test_the_cited_contract_is_the_one_in_force` — the
   **provenance pin**, working exactly as designed: adding members must appear as a diff
   there. Updated deliberately rather than loosened.

## Not done

This still requires the `com.renquant.ops-audit` job to be installed for the detectors to
run on a schedule — a machine landing, not taken here. The change makes them *runnable by
one command*; it does not make them *scheduled*.
