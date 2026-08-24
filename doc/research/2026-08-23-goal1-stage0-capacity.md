# GOAL-1 Stage 0: what the sizing arithmetic admits at each position cap

STATUS: AC1 of orch#1025 delivered — mechanical replay, committed and
reproducible (re-run reproduces the JSON byte-identically). **No return-based
claim is made and no configuration change follows from this document (AC3).**

## Method

Replay the recorded live candidate history through the **production sizer**
(`renquant_pipeline.kernel.sizing.compute_position_size`, the same function
`SizeAndEmitTask` calls, same `fractional` flag) for the grid
`cap ∈ {8,10,12,15,20} × {integer, fractional}`. Per-regime
`max_position_pct` / `cash_reserve_pct` are **read from the served config**
and confidence-scaled per run, exactly as production does. One session = the
live run with the most candidates that date (join per `run_id`, never per
date). Direction gate = `panel_score > 0 AND expected_return > 0` — the column
the gate actually reads. Read-only against `runs.alpaca.db`.

48 sessions with ≥1 priced admissible candidate, 2026-04-22 .. 2026-08-21;
**87/90 sessions BULL_CALM** — this is a single-regime picture.

## Result

| cap | mode | med filled | med deployed | price tilt (out/in) |
|---:|---|---:|---:|---:|
| 8 | integer | 2.0 | **37.0%** | 1.05× |
| 8 | fractional | 2.0 | 39.8% | 1.00× |
| 10 | integer | 4.0 | **61.7%** | 1.08× |
| 10 | fractional | 4.0 | 64.0% | 0.99× |
| 12 | integer | 5.0 | 70.2% | **1.20×** |
| 12 | fractional | 4.0 | 71.2% | 0.99× |
| 15 | integer | 5.0 | 71.4% | **1.24×** |
| 15 | fractional | 4.0 | 72.9% | 0.99× |
| 20 | either | = cap 15 | saturated | — |

## The three findings

1. **cap 8 → 10 nearly doubles deployment** (37.0% → 61.7% median): two extra
   slots absorb most of the unmet admissible demand (20–27 names/session vs
   0–4 free slots at cap 8).
2. **The cap stops binding above ~12** — 15 and 20 are identical; the binding
   constraint becomes per-position size × filled count.
3. **The coupling is real and quantified**: under integer shares, raising the
   cap WORSENS the anti-high-price tilt (1.05× → 1.24×) because smaller
   tickets floor away expensive names; fractional pins it at 0.99–1.00×
   at every cap. Raising the cap without fractional amplifies orch#608.

## Boundaries (what this does NOT say)

- Nothing about returns. More deployment is not established as better; that is
  Stage 1's question, gated on AC2's effective-sample check.
- Single-regime evidence (87/90 BULL_CALM sessions).
- The tilt here (1.05–1.24×) is a DIFFERENT statistic from orch#608's 4.76×
  (sized-in vs sized-out among priced admissible candidates, vs actually
  bought vs skipped). They must not be compared numerically.
- A first draft assumed `max_position_pct=0.15, cash_reserve_pct=0.10`; the
  served BULL_CALM values are **0.3 / 0.0**. Every deployment figure moved.
  The script now reads the config — recorded here so the lesson survives.

## Files

`data/2026-08-23-goal1-stage0/`: `stage0_capacity.py` (the replay),
`stage0_capacity.json` (the grid), `stage0_capacity.out` (run log),
`input_manifest.json` (DB row counts, config sha256, sizer resolution).
