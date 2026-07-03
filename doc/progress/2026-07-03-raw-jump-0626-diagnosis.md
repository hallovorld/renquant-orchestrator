# Progress: diagnosing the 2026-06-26 raw-score cross-section jump

Date: 2026-07-03
Branch: `research/raw-jump-0626-diagnosis`
Scope: research memo + read-only diagnostic tool + pinned evidence. No design
changes, no retraining, no re-stamping, no live-tree writes.

## Why

V5 (`doc/research/2026-07-03-v5-m4-verification.md`, check 5 / PR #272) proved
the M4 intercept regime begins 2026-06-26 with a +0.25 upward shift of the raw
score cross-section (median −0.297 → −0.047) and flagged root cause as
out-of-scope follow-up. If a routine feed rebuild can move the whole score
distribution by 0.25, everything score-anchored (mu floors, calibrators, BL-4
sign gates) inherits that fragility — so the cause needed a ruling.

## What was done

- `scripts/diagnose_raw_jump_0626.py`: read-only forensic tool (DB `mode=ro`,
  no pipeline imports; the panel feature transform is re-implemented pure
  numpy/pandas; boosters loaded straight from `booster_raw_json`). Emits
  pinned evidence to
  `doc/research/evidence/2026-07-03-raw-jump-0626/diagnosis.json`.
- `doc/research/2026-07-03-raw-jump-0626-diagnosis.md`: the memo.

## Ruling (short)

- The jump is a **silent prod scorer rollback**, not input sensitivity: the
  06-25 run's bundle stamps the 2026-06-21-trained XGB (panel sha `04d7a381…`,
  operator-promoted 06-22); the 06-26 run stamps the 2026-05-18-trained XGB
  (`5ce63326…`). Booster-content hashing collapses all artifact copies into
  exactly these two models; no promote event exists in the window.
- Mechanism: the 2026-06-25 live-tree recovery `checkout -B main origin/main`
  restored the committed (05-18) artifact over the uncommitted 06-22
  promotion; the revert was misread at the time as a stale config-fingerprint,
  re-stamped, and committed as prod. Umbrella `commit_sha` flips at the same
  boundary.
- The fund-freshness rebuild (#26) actually landed **06-29** and moved the raw
  cross-section by only +0.007 mean / 0.077 std (same-model pair), an order of
  magnitude below the boundary (+0.158 mean / 0.219 std, Spearman 0.185).
- Monitoring: the PSI drift monitor fired (0.46 → 2.66, new incident, 1
  notification) but is saturated — 247/247 rows CRITICAL since birth. Gap = no
  run-over-run scorer-identity (booster hash / trained_date) diff.
- Consequences flagged (not acted on): prod currently runs a 45-day-old model
  (violates the 28-day freshness directive); the live calibrator is anchored
  to the rolled-back-away model's score scale (reframes M4-b's intercept as a
  pairing artifact); the 06-21 model's promoted bytes are still recoverable on
  disk.

## Verification

- All load-bearing numbers recomputed from prod-persisted sources
  (`score_distribution`, `pipeline_runs.run_bundle_json`,
  `score_drift_audits`, `alert_incidents`) and pinned by content hash
  (DB sha `0630ffb5…` — byte-identical to the DB V5 verified).
- Committed-blob check done via GitHub API only (`gh api`), never local git in
  the live tree.

## Follow-ups (owned elsewhere)

- Comment on renquant-pipeline PR #162 (M4-b) with the pairing-artifact
  reframe.
- Operator decision: restore the 06-21 promotion or ratify the 05-18 rollback
  (freshness policy currently violated either way).
- Monitoring fix candidate (separate PR): scorer-identity change alarm +
  per-vintage PSI baseline re-anchor.
