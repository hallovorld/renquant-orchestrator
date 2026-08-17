# G-I MoE step 2 — IC screen: EXPLORATORY PILOT (superseded, not the authorized run)

STATUS: **exploratory pilot — WITHDRAWN as a verdict.** These numbers were
produced by a runner whose genuine and placebo legs were filtered
INDEPENDENTLY and then subtracted, so a lag-dependent difference in which
NAMES each leg covered could appear as Delta — the one quantity the screen
decides on (codex HIGH on orch#990; G7 in the runner header). The defect is
fixed in this same PR, but a corrected runner has NOT been run: spec §7 step 2
requires the runner reviewed BEFORE execution, and re-running it here would
repeat the very sequencing error that produced this correction.

**Nothing below advances any candidate.** `quality_gp` is NOT promoted to the
#984 §5b manifest freeze on the strength of these numbers, and the one-shot
budget of the frozen spec is NOT considered spent — the authorized run has yet
to happen, under the corrected and separately-reviewed runner.

Retained rather than deleted because the pilot is genuine evidence about the
PIPELINE (it ran end to end, the guards fired, the corpus and pins resolved)
even though it is not evidence about the CANDIDATES.

Spec: `doc/research/2026-08-17-gi-moe-step2-ic-screen-spec.md` (orch#987, merged).
DATE: 2026-08-17 (run at 2026-08-17T23:04:42Z, runtime 105.5 s).
SEMANTICS (of the spec, for reference — NOT exercised by this pilot): the screen
**TRIAGES** — a FLAGGED candidate is deprioritised in the #984 §5b queue and
requires a point-in-time rerun before any kill; a NOT FLAGGED candidate has shown
only "not obviously dead" (spec §1). Nothing kills or admits anything. The
one-shot budget applies to the AUTHORIZED run, which has not yet happened — this
pilot does not consume it.

PROVENANCE: every number below is `[VERIFIED — read from the committed
doc/research/data/2026-08-17-gi-moe-screen-results.json, produced by the
committed runner doc/research/data/2026-08-17-gi-moe-screen-derivation.py]`
unless tagged otherwise. The runner was committed BEFORE the run (spec §7
step 2 requires committed AND REVIEWED; only the first held — commit order
within one branch is author-controlled and the results carry no runner digest,
so the ordering claim was never externally checkable, which is part of why the
G7 defect reached the numbers), the
emitter pin `74c22647` (model#227 merge) was verified as ancestor — it is in
fact renquant-model main HEAD exactly — and the run wrote only to
`doc/research/data/` in an isolated worktree.

## 1. Pilot table (h=20, the frozen §5 rule applied — NOT a verdict)

| candidate | Δ = mean(gen)−mean(plac) | block-t (89 blocks) | % pos blocks | pilot outcome (NOT a verdict) |
|---|---|---|---|---|
| `high52w` | +0.00863 | 0.528 | 49.4% | **FLAGGED** (t < 1.0 AND pos ≤ 50%) |
| `lowbeta` | +0.00495 | 0.911 | 50.6% | **FLAGGED** (t < 1.0) |
| `quality_gp` | +0.00417 | 1.443 | 51.7% | **NOT FLAGGED** (all three criteria met) |

**1 of 3 not flagged — as a PILOT outcome only.** `quality_gp` does NOT proceed to the #984 §5b manifest freeze on this evidence;
`high52w` and `lowbeta` are deprioritised and may only be killed after a
point-in-time-universe rerun (spec §1/§2 — for `lowbeta` especially, the
survivorship direction argues the current-watchlist corpus may UNDERSTATE it).

## 2. Per-horizon detail

Mean ICs are levels and carry the ~+0.04 embargo-leakage caution — only the
genuine−placebo DIFFERENCE is decision-relevant (spec §3).

### h=20 (primary; 359 weekly obs kept of 359; 89/89 blocks with data)

| candidate | mean IC genuine | mean IC placebo | Δ | block-t | % pos blocks |
|---|---|---|---|---|---|
| `high52w` | −0.00891 | −0.01753 | +0.00863 | 0.528 | 49.4% |
| `lowbeta` | −0.05009 | −0.05504 | +0.00495 | 0.911 | 50.6% |
| `quality_gp` | +0.01289 | +0.00872 | +0.00417 | 1.443 | 51.7% |

### h=60 (informational ONLY, never decisive; 359/359 kept; 29/29 blocks)

| candidate | mean IC genuine | mean IC placebo | Δ | block-t | % pos blocks |
|---|---|---|---|---|---|
| `high52w` | −0.02445 | −0.02067 | −0.00378 | −0.181 | 55.2% |
| `lowbeta` | −0.09935 | −0.12228 | +0.02293 | 1.398 | 65.5% |
| `quality_gp` | +0.00588 | −0.00553 | +0.01141 | 1.211 | 41.4% |

Annotation-grade observations (n_eff≈16 at h=60, spec §4): `lowbeta`'s Δ
strengthens with horizon while its IC LEVEL is strongly negative in both arms —
the placebo-vs-genuine gap, not the level, is what the estimand trusts, and the
level's sign is exactly where the spec's survivorship caveat (§2) points.
`quality_gp` is the only candidate with positive genuine levels in both
horizons. `high52w`'s Δ changes sign across horizons — noise-compatible.

## 3. Dropped dates

Zero. All 359 cross-sections passed the ≥50-pairs floor for BOTH the genuine
and the placebo arm, for every candidate at both horizons
(`dropped = {floor_genuine: 0, floor_placebo: 0, degenerate: 0}` in every
cell); all 89 (h=20) and 29 (h=60) blocks have data. Per-date coverage
(median n_scored): high52w 143, lowbeta 143, quality_gp 73.

## 4. ρ matrix (informational — the |ρ|<0.7 gate is APPLIED at #984 §5b, not here)

Mean per-date cross-sectional Spearman ρ over 359 dates (sd in parens):

| candidate | vs `mom_slow_12m` (v0) | vs `mom_fast` (v1_fast) | vs `multifactor_core` |
|---|---|---|---|
| `high52w` | +0.439 (0.192) | +0.513 (0.156) | NAMED GAP (§5) |
| `lowbeta` | +0.046 (0.251) | +0.010 (0.311) | NAMED GAP (§5) |
| `quality_gp` | +0.087 (0.152) | +0.031 (0.168) | NAMED GAP (§5) |

`high52w` is, as designed, momentum's closest sibling — mean ρ ≈ 0.44–0.51
against both momentum clocks (under the 0.7 bar but by far the least
incremental of the three). `lowbeta` and `quality_gp` are near-orthogonal to
the momentum lanes.

## 5. Named gaps (recorded, not fabricated)

1. **`multifactor_core` ρ column** — no committed/reachable historical score
   series for the panel champion exists on the corpus dates without running the
   panel pipeline (`data/score_db.sqlite` is empty `[VERIFIED — sqlite_master
   has zero tables]`; production run bundles cover 2026 live dates only). The
   spec forbids heavy compute here; the column is deferred to the #984 §5b
   Stage-A batch where those scores exist anyway.
2. **Point-in-time universe** — inherited from the spec (§2): the corpus is
   the current 145-name watchlist and is survivorship-tilted for the 2019-era
   cross-sections; this is why FLAGGED ≠ killed.

## 6. Deviations from the spec text (reported, not papered over)

1. **359 cross-sections, not 358.** The frozen RULE (every 5th trading day on
   the 1,792-day window `[VERIFIED — SPY calendar count]`) yields
   ceil(1792/5) = 359 `[DERIVED]`; the spec's §2/§4 derived count said 358.
   The rule governs (runner guard G1); the discrepancy is asserted tight
   (|n−358| ≤ 1) and reported. No observation was dropped to fit the quoted
   count. Block counts are unaffected (89/29 complete blocks, asserted
   exactly).
2. **Runner review timing.** Spec §7 step 2 asks that the runner be committed
   and reviewed before the run. The runner WAS committed before the run
   (separate, earlier commit on this branch) with every §7 guard written down
   (G1–G12 in its header), but review necessarily arrives with this results
   PR — the two could not be sequenced through separate reviewed PRs inside
   the one authorized execution window. The one-shot rule was honored: the
   screen ran exactly once, and no parameter was touched after any output was
   seen.

## 7. Reproduction

```
cd <this repo>
/path/to/python doc/research/data/2026-08-17-gi-moe-screen-derivation.py
```

Inputs (all read-only; sha256 digests in the results JSON `pins` block):
SPY + per-ticker `data/ohlcv/*/1d.parquet` (digest-of-digests
`96a1050d…49d1e746`), `data/sec_fundamentals_daily.parquet`
(gross_profitability + its `_source_available_at` PIT column),
`renquant-strategy-104/configs/strategy_config.golden.json` watchlist
(n=145, checkout `86a78b41`), `data/ticker_sectors.json`, and
`renquant-model` at `74c22647a7880c6a3234e53fb5d037d82fde3faf` (= main HEAD,
the model#227 merge pin the spec froze). The script is deterministic — no
randomness, no clock in any computed number.
