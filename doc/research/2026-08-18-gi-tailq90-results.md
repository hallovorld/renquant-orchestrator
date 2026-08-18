# G-I `tail_q90_60d` — the AUTHORIZED one-shot screen: FLAGGED

STATUS: **the ONE authorized run under the frozen spec — the `tail_q90` family's
one-shot budget is now SPENT.** Spec:
`doc/research/2026-08-18-gi-tailq90-screen-spec.md` (orch#994, merged). Runner:
`doc/research/data/2026-08-18-gi-tailq90-derivation.py` (orch#996, merged),
executed VERBATIM from orchestrator main `9d73d546` — zero edits, zero added
parameters, byte-identity vs origin/main asserted by the runner itself (T2)
before any computation. One execution; these numbers are final for this corpus.
The spec §6 sequencing (spec merged → runner committed AND reviewed → ONE run)
held end to end.

DATE: 2026-08-18 (run at 2026-08-18T08:24:05Z, runtime 221.4 s
`[VERIFIED — results JSON run_utc/runtime_sec]`).

SEMANTICS (spec §4): the screen **TRIAGES** — it neither kills nor admits.
FLAGGED = deprioritised in the #984 §5b queue; a formal kill additionally
requires a point-in-time-universe rerun (survivorship direction UNKNOWN on the
current-watchlist corpus); admission always needs the full #984 §5b
confirmatory path. **Nothing below kills the candidate.**

PROVENANCE: every number is `[VERIFIED — read from the committed
doc/research/data/2026-08-18-gi-tailq90-screen-results.json / …-ic-series.csv /
…-refit-ledger.json as written by this run]` unless tagged otherwise.

## 1. VERDICT (h=60 PRIMARY, the frozen §4 triage rule — FINAL for this corpus)

| candidate | Δ = mean(gen)−mean(plac) | block-t (29 blocks) | % pos blocks | verdict |
|---|---|---|---|---|
| `tail_q90_60d` | **−0.00801** | **−0.717** | 55.2% (16/29) | **FLAGGED** (Δ ≤ 0 AND t < 1.0) |

The candidate fails two of the three criteria at the trained horizon: Δ is
NEGATIVE (the genuine-score IC is lower than the 120-trading-day-lagged
placebo's) and block-t is negative. The block-majority criterion alone was met
(16/29 > 14.5). Per spec §4 this is a triage outcome: deprioritised, not
killed — kill-side finality needs the PIT-universe rerun, and the spec's own
power note (n_eff ≈ 16 at h=60, annotation-grade) still applies. But note the
failure mode here is not "true-but-small edge under low power": the point
estimate itself is on the wrong side of zero.

## 2. Per-horizon detail

Mean ICs are levels and carry the ~+0.04 embargo-leakage caution — only the
genuine−placebo DIFFERENCE is decision-relevant.

### h=60 (PRIMARY, decisive; 350/359 weekly obs kept; 29/29 blocks with data)

| quantity | value |
|---|---|
| mean IC genuine | +0.06349 |
| mean IC placebo | +0.07150 |
| Δ | **−0.00801** |
| block-t (29 non-overlapping 60d blocks) | −0.717 |
| % positive blocks | 55.2% (16/29) |
| mean per-block Δ | −0.00949 (sd 0.07128) `[DERIVED — per-block means recomputed from the committed CSV]` |
| dropped dates | 9, all `no_refit_placebo` (== the deterministic calendar expectation, T7 assert passed) |
| verdict | **FLAGGED** — `delta=-0.00801 <= 0; block_t=-0.717 < 1.0` |

The genuine leg's IC LEVEL is strongly positive (+0.063) — but so is the
placebo's (+0.072), and higher. Whatever cross-sectional ordering the q90
learner captures at h=60, a 120-trading-day-older copy of its own scores
captures at least as much of it: the score's information content is slow and
persistent, not fresh.

### h=20 (informational ONLY — spec §4: can neither flag nor rescue; 359/359 kept; 89/89 blocks)

| quantity | value |
|---|---|
| mean IC genuine | +0.03786 |
| mean IC placebo | +0.02633 |
| Δ | +0.01154 |
| block-t (89 blocks) | +1.586 |
| % positive blocks | 55.1% (49/89) |
| verdict field | none (spec §4: h=20 carries NO verdict) |

Recorded honestly: had h=20 been decisive, all three criteria would have been
met (Δ > 0, t = 1.586 ≥ 1.0, 49/89 = 55.1% > 50%) `[DERIVED — rule applied to
the numbers above]`. It is not decisive, by the frozen spec's own §4 REVISION
(codex 2×HIGH): the candidate is trained on a 60-trading-day label, and a
horizon the model was not trained for can neither flag nor rescue it. No
horizon rescue is available or claimed — the one-shot verdict is the h=60
FLAGGED above. The h=20 pattern (fresh scores beat their lag at the horizon
the model was NOT trained for, and lose to it at the horizon it WAS trained
for) is recorded as an unexplained observation for a future PIT rerun, not
interpreted further here.

## 3. ρ section (informational — the |ρ|<0.7 roster gate is APPLIED at prereg, not here)

Mean per-date cross-sectional Spearman ρ over 359 dates (sd in parens), ≥50
common names per date:

| pair | mean ρ (sd) | n dates |
|---|---|---|
| `tail_q90_60d` vs `core_rank_ref` (rank-reference) | **+0.696** (0.072) | 359 |
| `tail_q90_60d` vs `mom_slow_12m` (v0) | −0.029 (0.182) | 359 |
| `tail_q90_60d` vs `mom_fast` (v1_fast) | +0.045 (0.223) | 359 |

The rank-reference is the spec §5 declared fallback: a same-recipe
`rank:pairwise` refit at the SAME 31 frozen cutoffs (params VERBATIM, no
delta), trained purely as the ρ reference because committed core-score history
on the corpus dates is unreachable without heavy compute (the #992 named gap).
Its scores were used for ρ ONLY, never screened.

The spec §5 declared risk materialised almost exactly: sharing all 172
features + the label with the core recipe and differing only in objective, the
candidate lands at ρ = +0.696 against the rank-reference — inside the 0.7 bar
by 0.004 `[DERIVED — 0.7 − 0.696]`, i.e. the objective swap changes the
cross-sectional ordering much less than a genuinely new signal would. Against
both momentum clocks it is near-orthogonal (|ρ| < 0.05).

## 4. Refit ledger (T5/T6/T8/T9 — full per-cutoff detail in the committed JSON ledger)

- 31 expanding refits × 2 objectives (candidate + rank-reference), cutoffs
  2018-06-29 .. 2025-12-31, each the last SPY trading day of its quarter
  (T6 assert passed). Train rows grow 72,111 → 333,668; every refit's
  `train_min_date` = 2016-01-04 (expanding, T8) and every refit's max train
  date + 60 trading days ≤ its cutoff (realized labels only, asserted per
  refit). Total fit time 150.3 s of the 221.4 s runtime `[VERIFIED — ledger
  fit_seconds sum]`.
- Per-cutoff booster sha256 digests for BOTH objectives are recorded in
  `doc/research/data/2026-08-18-gi-tailq90-refit-ledger.json`, plus the
  refit-used-by-score-date map (374 scored extended-grid dates).
- 30 of the 31 refits were actually used in scoring: the 2025-12-31 refit's
  first scoreable date under the 60-trading-day embargo is 2026-03-30, past
  the corpus end 2026-03-02 — trained and ledgered, never consumed
  `[VERIFIED — ledger refit_used_by_score_date + first_scoreable_date]`.
- Normalization replay: every cutoff reproduced the artifact's per-column norm
  kinds exactly (158 global_z / 5 robust_z / 9 identity, T9 assert passed per
  refit `[VERIFIED — run log, 31/31]`); the replayed sentiment
  trained_zeroing contract equals the artifact's stored contract (T9 assert
  passed; replay metadata embedded in the results JSON).

## 5. Coverage and dropped dates

- h=60: 350/359 dates kept; the 9 drops are all `no_refit_placebo` — placebo
  score dates (lag 120 trading days) preceding the first refit's maturity —
  and the count equals its deterministic calendar expectation (T7 assert).
  h=20: 359/359 kept, zero drops of any kind.
- Paired floor never binding: minimum shared cross-section 131 names, median
  142, at both horizons (floor 50) `[VERIFIED — CSV n_pairs_shared]`.
- Removed-confound telemetry (per-leg minus shared-leg coverage, the #990
  correction's target): mean gap +0.75 names at h=60 (max +5, nonzero on
  98/350 dates), +0.25 at h=20 (max +3, nonzero 56/359) `[VERIFIED —
  aggregated from the committed IC-series CSV]` — small on this candidate,
  but nonzero, so the paired estimand did real work.
- Watchlist names absent from the panel: CRWV, RKLB, SPCX (3 of 145) —
  recorded by the runner, never silently dropped.

## 6. Guard outcomes and deviations

- **All T1–T15 guards passed**; the runner exited 0 on its single execution
  `[VERIFIED — run log, exit code 0]`. No fix-and-rerun occurred; no
  parameter was touched; the script ran once and only once. The one-shot
  marker (T1) now forbids any re-execution against these output paths.
- T2 asserted the executing bytes equal origin/main's copy at
  `9d73d546` — the runner refuses to run otherwise; the identity block it
  recorded is in the results JSON (`pins.runner_identity`).
- T3 behavioral probe: xgboost 2.1.4 trains `reg:quantileerror` (1-round
  micro-fit passed).
- Zero deviations from the merged spec or runner. Runtime 221.4 s, well under
  the runner PR's 15–20 min estimate (run under caffeinate regardless).

## 7. Pins and reproduction

All digests below `[VERIFIED — results JSON pins block]` unless noted:

- orchestrator main (runner source + execution base): `9d73d5463b23218bf8bded9ff75f9bbf479a3543`
- runner file sha256: `df5c1d66bb14c9660aebd48664210eef6837bdc46ca08f7affd008a13dae9edc` (git blob `dc5b8887`, recorded by T2 inside the results JSON — the orch#990 NEXT item "runner digest in the JSON" is closed by this runner)
- served artifact: `artifacts/prod/panel-ltr.alpha158_fund.json`, sha256 `6461b827…546d15`, config fingerprint `sha256:f8fb2259b2bf1537` (T4 asserts passed: 172 feature_cols, 172 norm kinds, `fwd_60d_excess`, lookahead 60, best_iter 100)
- training frame: `data/alpha158_291_fundamental_dataset.parquet` sha256 `870f68eb…29bf7e`
- production trainer helpers: `scripts/train_production_model.py` sha256 `f35e8778…ed3aec` (imported read-only, T9)
- `renquant-model` HEAD: `9432413a682d923d9a5b1b68f58039b7a5536dfe` (momentum machinery for the ρ lanes only)
- `renquant-strategy-104` checkout: `86a78b41` `[VERIFIED — rev-parse before run]`; watchlist n=145, sha256 `d93d28c5…4b555`
- data: OHLCV digest-of-digests `96a1050d…e746`, SPY `68665523…b0ee` — identical to the #992 moe run's pins, so the two families were screened on the same price store
- python: `/Users/renhao/git/github/RenQuant/.venv` (xgboost 2.1.4; numpy 2.0.2, pandas 2.3.3, scipy 1.13.1 `[VERIFIED — version probe before run]`)
- execution: isolated worktree of orchestrator main at `9d73d546`
  (branch `research/gi-tailq90-results`); the runner chdir()s into the
  umbrella only to READ `data/`; wrote only the three
  `doc/research/data/2026-08-18-gi-tailq90-*` outputs inside the worktree; no
  live-tree or production-path writes.

The runner is deterministic by construction (fixed seed, stable row sort
before the DMatrix build, no early stopping, no search; wall-clock stamps in
metadata only) — re-executing at these pins reproduces these outputs
bit-for-bit (reproduction is not a re-run of the screen; the one-shot budget
is spent).

## 8. What happens next (per the merged spec — no new decisions here)

`tail_q90_60d` joins the three #987 emitters as FLAGGED/deprioritised in the
#984 §5b queue: the screen record on this corpus now reads **0 of 4 not
flagged across both families**. Any kill decision for this candidate first
requires the point-in-time-universe rerun the spec defers to. Two recorded
facts a future PIT rerun can confirm or dissolve — they authorize nothing
today: the h=20 informational pattern (§2), and the ρ = 0.696 near-collision
with the core recipe (§3), which independently caps this candidate's roster
value even if a PIT rerun were to clear it.
