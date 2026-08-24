# GOAL-1 Stage 0 v2: what the sizing arithmetic admits at each cap — with parity

STATUS: AC1 of orch#1025 — v2, rewritten after codex review. Mechanical replay,
committed, reproducible (byte-identical re-run). **No return-based claim; no
configuration change follows from this document (AC3).**

## What v2 replays, and what it proves it replays

Every load-bearing sizing input is the PRODUCTION seam, imported from the
pinned pipeline (`kernel.sizing`, `kernel.regime`), and the preamble mirrors
`SizeAndEmitTask` (task_selection.py:228-262) exactly: legacy
`max_pct = max_position_pct × confidence_to_size_multiplier(conf) × conviction
× sigma` (Kelly is OFF in the served config), reserve confidence-scaled,
`per_session_buy_cap` honoured, real `fractional_eligible` +
`fractional_dust_floor_usd`, one-share floor off per config.

**Parity against production, current-config era (2026-08-10+):**

| metric | value |
|---|---|
| conviction / reserve max abs Δ | **0.0** |
| sigma_mult max abs Δ | 1.3e-4 |
| max_pct max abs Δ | **2.3e-5** |
| share mismatches on matched orders | **0** |
| sessions set-identical | 5 / 9 |

The 4 non-identical sessions are each annotated with **production's own
recorded reason**, and every one is a layer this replay declares unreplayed:
`candidate_not_selected` (greedy corr/sector admission — inputs not persisted),
`broker_pending_submitted` (broker state), `wash_sale` (CRWD 2026-08-20).
One session (2026-08-21) is excluded by the coverage guard: the price join is
against `ticker_forward_returns`, which is backfilled, and that date had
close_price for 0 of 27 gate-passers at run time.

**Why parity is era-gated — a finding in itself.** Reverse-engineering every
recorded NEW_BUY's `max_pct/(conv×sigma)` against today's config: ratio
**exactly 0.4000** for all orders 2026-06-22..08-04 (the `max_position_pct=
0.12` era; 0.12/0.3 = 0.4), per-ticker ratios ≤ 0.40 before 06-22 (the Kelly
era), **exactly 1.0000 from 2026-08-10 onward**. Production's sizing policy
changed twice in the sample. This replay deliberately applies TODAY'S config
to all history — the forward-looking counterfactual "what would today's policy
do at cap X" — so parity is only *defined* in the current era, where it holds
to 2.3e-5.

## Session provenance

Selection is by EXPLICIT provenance, not uniqueness alone [codex round 2]:
`strategy = 'renquant-104'` is filtered AND validated — any other strategy
value among candidate-bearing live runs fails the whole script closed, because
an unexpected lane means the selection model is wrong, not that a row should
be skipped. Every selected run's `{run_id, strategy, commit_sha, created_at}`
is recorded; 19 dates with multiple qualifying runs are excluded and recorded.
38 canonical sessions, 2026-04-23 .. 2026-08-21.

Reproducibility is fingerprinted on THE EXACT INPUTS USED, not the container:
a deterministic sha256 over every selected `pipeline_runs` /
`candidate_scores` / price / trades row this script read (the DB is live — a
path and row counts cannot anchor a re-run), plus the pinned pipeline commit
(`git rev-parse` of `--pipeline-src`) and a sha256 of each imported seam
module file (`sizing.py`, `regime.py`). All in the artifact; re-run
reproduces the JSON byte-identically including the digests.

## The grid (38 canonical sessions; medians)

| cap | mode | med filled | med deployed | price tilt (out/in) |
|---:|---|---:|---:|---:|
| 8 | integer | 2.0 | **17.3%** | 1.28× |
| 8 | fractional | 2.0 | 20.3% | 1.00× |
| 10 | integer | 3.0 | **32.6%** | 1.20× |
| 10 | fractional | 4.0 | 35.2% | 1.06× |
| 12 | integer | 5.0 | 42.9% | 1.21× |
| 12 | fractional | 5.0 | 44.7% | 1.07× |
| 15 | integer | 5.0 | 44.6% | **1.40×** |
| 15 | fractional | 5.0 | 47.3% | 1.10× |
| 20 | integer | 5.0 | 44.6% | **1.50×** |
| 20 | fractional | 5.0 | 47.3% | 1.13× |

Findings (directionally identical to v1, honest numbers under parity):
1. **cap 8 → 10 roughly doubles deployment** (17.3% → 32.6% median).
2. **The cap saturates by ~15** — the binding constraint becomes per-position
   size × filled count.
3. **The coupling**: integer tilt grows with the cap (1.28× → 1.50×);
   fractional holds 1.00–1.13×. Raising the cap without fractional amplifies
   the orch#608 anti-high-price tilt.

## Boundaries

- No return claim (Stage 1, gated on AC2's ESS). Single-regime evidence.
- Admission above cap 8 is rank-order fill WITHOUT corr/sector guards — an
  upper bound, and the measured cap-8 gap (4/9 sessions differ, all by those
  guards) is the size of that approximation at the production cap.
- v1's numbers (37%→62% deployment) are superseded: they were computed with
  assumed sizing params, per-date session selection, and no parity check.
