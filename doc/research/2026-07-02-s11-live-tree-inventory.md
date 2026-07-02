# S11: live-tree dirt inventory — every item ticketed or resolved (read-only audit)

STATUS: research evidence / audit record (read-only — no git mutation was performed in any
live or working checkout; `git status`/`diff`/`show` only). Task S11 of the unified plan
(#231 Term PROCESS / floor tier-2).
DATE: 2026-07-02

## Verdict up front

**No durable-PR work remains for live-tree CODE dirt.** The headline hotfix (adapter-save
NameError) is ALREADY durable on umbrella origin/main; the rest of the dirt is data churn,
known re-stamp artifacts (root cause already scheduled as M6/R2), or out-of-sync working
copies whose content is already merged upstream. The S11 acceptance ("live tree diff =
empty or fully ticketed") is met by THIS inventory; the remaining action is the
already-flagged LANDING step (sync the checkout to pins), which is outside the
direction-loop's lane.

## Inventory (umbrella RenQuant live tree, `git status` 2026-07-02)

| Item | Class | Disposition |
|---|---|---|
| `backtesting/renquant_104/adapters/runner.py` (1-line diff: `save_live_state_atomic(..., config → self._config)`) | CODE hotfix residue | **RESOLVED upstream** — verified `origin/main:runner.py:1785` already ships `self._config`; the local diff is a stale copy on a checkout that is BEHIND origin/main (matches the daily run's "umbrella main behind origin/main; newer pins NOT deployed" WARN). Memory record corrected. No PR needed; needs the LANDING sync only |
| `artifacts/prod/panel-ltr.alpha158_fund.json`, `panel-rank-calibration.json`, `walkforward_calibrators/*/panel-rank-calibration.json` | artifact re-stamps (the 07-01 calibrator fingerprint re-stamp unblock) | **TICKETED**: root cause = triple-implemented content fingerprint; the permanent fix is M6/R2 (fingerprint unification), already on the plan. Artifacts are not PR'd |
| `backtesting/data/equity/usa/daily/*.zip`, `factor_files/*`, `map_files/*` | LEAN daily data churn | normal operation; no action |
| local `renquant-backtesting` checkout: `loader.py`, `wf_gate/runner.py` modified + 2 untracked tests | working-copy residue of ALREADY-MERGED work (URI-resolution fix #54 + parity/genuine-IC commits are on backtesting origin/main) | content is upstream; the residue cleanup is a checkout-sync (landing) action — NOT performed by this loop per the live-tree hard rule |
| `renquant-pipeline`, `renquant-strategy-104`, `renquant-base-data` checkouts | clean | — |

## The one standing risk (unchanged, for the lander)

The live umbrella checkout is BEHIND origin/main while carrying dirt that OVERLAPS commits
it hasn't pulled. A naive `git pull` will conflict on runner.py; a naive `reset/checkout`
is the exact 06-25 incident. The safe landing sequence (for the operator/lander, NOT this
loop): stash-verify-pull-diff-drop-stash — and it is precisely the "recovery drill doc"
deliverable that remains open under R7.
