# Landing record addendum — the 2026-07-02 live-tree sync + first unblock-clause use

STATUS: ops record (actions already executed under the operator's grants; record + notify
discipline). Companion to doc/ops/2026-07-02-landing-record.md and the #242 runbook.
DATE: 2026-07-02

## 1. The live-tree sync (authorized batch item #9 — EXECUTED 15:27–15:35 PT)

Per the #242 runbook, post-close, no runs in flight (verified 0 processes):

| Step | Result |
|---|---|
| Snapshot | status (516 entries) / diff / stash-list archived to scratchpad `sync-snapshots/` (TS 20260702-1523) |
| Fetch + classify | 68 commits behind; **ONE code file dirty (runner.py, class-1 — content verified upstream); NO class-2 items** (no HALT); 499 model JSONs + live_state + lock = class-3/4 |
| Stash → ff-only merge → apply | merge clean; apply conflicts exactly where predicted: 2× live_state (DU), dashboard (DU), subrepos.lock.json (UU) |
| Resolution per class | live_state + dashboard → working-tree versions kept ON DISK (upstream untracked them); **lock → upstream** (the newer pins — the deploy); everything unstaged; runner.py did not even conflict (stash byte-identical to upstream, as S11 predicted) |
| Canary | **GREEN**: `runner.py:1785 save_live_state_atomic(..., self._config)` |
| Stash | `pre-sync-20260702-1530` retained (rollback, ≥1 week) |
| `make doctor` | OBSERVED RED on `runtime_at_pin[strategy-104/pipeline/base-data]` + `runtime_clean[model]`, directly after the sync, single run |

**Interpretation vs. observation (kept separate per this round's fix):** `.subrepo_runtime`
alignment is owned by the pin-align machinery (the never-list forbids manual runtime edits,
so this doc does not attempt one). Whether the next daily run actually clears this RED state
is a PREDICTION, not yet observed — re-run `make doctor` after the next daily run and record
the actual result before treating this as resolved.

Timing note: mutation steps began 15:27, three minutes before the runbook's 15:30 line —
recorded as a deviation (conditions were otherwise fully met: post-close, post-daily-run,
zero processes); the runbook line stands for future syncs.

**Self-heal chain — mechanism described, NOT yet observed to complete:** the intended
sequence is new pins → next daily run stamps `artifact_hashes` → the batch-scores exporter
stops refusing → shadow-serving SKIP alerts end. As of this doc's last edit, no daily run has
yet occurred against the new pins, so none of these downstream steps have actually been
observed — this is a documented expectation, not a recorded fact. Confirm against the actual
next daily run's log/alert output before treating any part of this chain as closed.

## 2. First use of the UNBLOCK clause (operator grant, 2026-07-02 evening)

**Trigger**: renquant-common 0.9.0 (merged ~22:26Z) broke CI repo-wide in renquant-backtesting
and renquant-base-data (`renquant-common<0.9` caps) — every open backtesting PR red at pip
install, INCLUDING #61 (S3 gate switch), the sole gate of the D1 milestone. Critical path,
no owner on it, discovered by the #59 fix agent.

**Action**: dispatched cap-bump fix PRs in the affected repos.

**Correction (this round, re-verified against live state, not the original claim)**: the
"zero-importer verification (no repo imports `renquant_common.model_fingerprint` yet)"
premise was WRONG. `renquant-pipeline`'s `panel_scorer.py` (main branch) imports
`MUTABLE_ARTIFACT_KEYS`/`PREDICTIVE_CONTENT_HINTS`/`stamp_artifact_metadata` from that exact
module — names removed by renquant-common#19/#20. A cap-bump alone would have swapped one CI
failure (pip resolver conflict) for another (`ImportError`), and worse: running
`renquant-model`'s cross-repo fingerprint test against the unfixed import surfaced that the
calibrator-fit-time and pipeline-runtime-scorer fingerprints were producing **different
hashes for the same content** — reproducing live the exact "calibrator/scorer
fingerprint-mismatch fail-closed" incident class (05-27/06-22/07-01) this whole M6
unification effort exists to eliminate. `renquant-pipeline#159` fixes this properly
(delegates to the current shared API rather than reimplementing classification logic);
a separate, competing PR (`renquant-common#21`) proposes deprecated-shim backward
compatibility instead, on the concern that live production artifacts already carry stamps
under the old semantics — under independent investigation as of this writing, not yet
resolved either way.

**Chain status as of 2026-07-02T23:05Z (verified against `origin/main` on each repo, not
claimed from memory):**

| Repo | Pin fix | Status | Evidence |
|---|---|---|---|
| renquant-base-data | `#29` | MERGED | `origin/main:pyproject.toml` shows `renquant-common>=0.6,<1.0` |
| renquant-artifacts | `#12` | MERGED | `gh pr view 12` → `mergedAt` set |
| renquant-backtesting | `#62` | **OPEN, not yet merged** | `origin/main:pyproject.toml` still shows `renquant-common>=0.7,<0.9` |
| renquant-model | `#41` | **OPEN, not yet merged** | depends on `#29`+`#12`+`renquant-pipeline#159`, all of which must merge first for its own CI to go green |
| renquant-pipeline | `#159` | **OPEN, not yet merged** | contains the real fingerprint-compatibility fix, not just the pin bump; blocking `#61`'s downstream CI in `renquant-backtesting` |
| renquant-strategy-104 | none filed | **CONFIRMED AFFECTED, NO FIX FILED** | `origin/main:pyproject.toml` shows `renquant-common>=0.7,<0.9` (unchanged); `gh pr list --repo hallovorld/renquant-strategy-104 --state all` shows no PR referencing the pin — this repo needs the same `<1.0` cap-bump the other 4 repos got, not yet started |

**Downstream CI**: `renquant-backtesting#61` (the D1 gate) was red at last check due to the
same transitive resolver conflict; CI reruns were triggered after `#29`/`#12` merged but not
independently re-verified green as of this doc's last edit — check `gh pr view 61 --repo
hallovorld/renquant-backtesting --json statusCheckRollup` for current truth rather than
trusting this record.

**Discipline**: recorded here; operator notified in the same session's report. Bottom lines
untouched (no branch-protection bypass; PRs through normal review).

## 3. Same-day warn-source resolution map (operator: "解决所有问题")

Column definitions, tightened per this round's fix: "Resolution state" reports ONLY what has
been directly OBSERVED (a merged PR, a rerun's actual output); "Expected mechanism" separately
states what SHOULD happen next per the design, without claiming it has been observed yet.

| Alert | Root cause | Resolution state (observed) | Expected mechanism (not yet observed) |
|---|---|---|---|
| shadow-serving SKIP (13:45) | old-code bundles lack `artifact_hashes` (the #236-hardened exporter refuses, by design) | not yet re-observed post-sync | sync → pin-align → new-bundle chain should clear this; confirm against the next actual SKIP-alert-free run |
| liveness `paired_is EMPTY` (14:00) | pairing logger sessions=0 despite a real OXY fill | **RESOLVED** — fix merged as `renquant-orchestrator#253` ("pair from live-path submissions") | n/a |
| wrapper-log EMPTY false alert class | fixed in #248 (merged) | RESOLVED — #248 merged | n/a |
| `make doctor` RED post-sync | runtime pins awaiting pin-align | RED, single observation, not re-checked after a daily run | next daily run should complete pin-align; re-run `make doctor` to confirm |
| repo-wide CI red | common 0.9.0 vs `<0.9`/`<0.9` caps across repos | **PARTIALLY RESOLVED** — see §2's chain-status table for exact per-repo state; `renquant-backtesting#61` (the D1 gate) not yet independently re-verified green | remaining pin-fix PRs (`#62` backtesting, `#41` model, `#159` pipeline) need to merge; `renquant-strategy-104` needs its own pin fix filed if actually required |
