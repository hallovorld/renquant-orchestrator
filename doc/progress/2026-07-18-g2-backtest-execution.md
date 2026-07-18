# 2026-07-18 — G2 preregistered historical exercise executed: FAIL, tombstone

## What

Executed the frozen G2 reversal costed backtest
(`doc/research/2026-07-17-g2-reversal-backtest-prereg.md`, sealed by
PR #546) against the sealed `crypto_ohlcv` corpus. Ships:

- `scripts/g2_reversal_backtest.py` — seeded, deterministic
  implementation of the frozen §4 construction, §2 MBB inference, §1
  20-member family max-t diagnostic, and §5 fee gate. Fail-closed seal
  check: refuses to run unless the store manifest re-derives the sealed
  fingerprint `sha256:0068eb93…c1cc1` AND every pair's canonical content
  sha256 matches the sealed candidate.
- `doc/research/g2-manifest/2026-07-18-g2-backtest-results.json` — the
  frozen §7 results artifact (max-t diagnostic, per-stress net d_t
  stats, turnover, input digests, execution-proxy declaration, seed).
- `doc/research/2026-07-18-g2-backtest-results.md` — results memo with
  the §7 tombstone.

## Outcome

**FAIL → G2 NO-GO.** Base-fee net MBB 90% lower bound −29.9 bp/day;
+10 bp stress −38.0 bp/day (frozen rule: both must be > 0). n = 1,693
scored days, one-way turnover 0.416/day, names/day 2.97. Gross edge vs
BTC buy-and-hold ≈ 0 (−1.7 bp/day, t −0.29) — not a costs-only failure.
All 20 frozen family members negative net (max t −0.48); H1
family-adjusted p = 1.0. The §3(b) registered censoring inflates PASS,
so FAIL is robust to it. Tombstone recorded in the results memo; no
paper-shadow registration; no re-pitch of the family.

## Verification

- Seal check passed before running (manifest fingerprint re-derivation +
  42/42 per-pair canonical content hashes + committed-vs-store schedule
  identity).
- Deterministic: identical artifact across reruns and across
  PYTHONHASHSEED values; MBB seeded (20260718), block length precomputed
  (Politis-White) — declared in the artifact.
- Accounting cross-check: gross→base mean gap (−1.7 → −22.5 bp/day)
  equals 2 × turnover × 25 bp exactly.
- Read-only on the store; no orders, no capital, nothing touches 104.

## Memory tier touched

SHORT/MID: G2 goal state — historical feasibility screen FAILED, G2
killed per prereg §7 (goal-memory update is an operator-visible
follow-up; this PR is the durable record).
