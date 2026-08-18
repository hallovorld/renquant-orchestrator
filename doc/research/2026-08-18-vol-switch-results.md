# Vol-switch confirmatory — the ONE authorized run: CONFIRMED

STATUS: **the ONE authorized execution under the frozen prereg — the vol-switch
confirmatory's one-shot budget is now SPENT.** Prereg:
`doc/research/2026-08-18-vol-switch-confirmatory-prereg.md` (orch#1001, merged).
Runner: `doc/research/data/2026-08-18-vol-switch-derivation.py` (orch#1002,
merged), executed VERBATIM from orchestrator main `88c589c0` — zero edits, zero
added parameters, byte-identity vs a freshly FETCHED origin/main asserted by the
runner's own V2 guard before any computation. One execution; these numbers are
final for this corpus. The prereg §6 sequencing (prereg merged #1001 → runner
committed AND reviewed #1002 → ONE run on the merged copy) held end to end.

DATE: 2026-08-18 (run at 2026-08-18T11:16:05Z, runtime 168.7 s `[VERIFIED —
results JSON run_utc/runtime_sec]`).

PROVENANCE: every number is `[VERIFIED — read from the committed
doc/research/data/2026-08-18-vol-switch-results.json / …-series.csv /
…-blocks.csv / …-refit-ledger.json as written by this run]` unless tagged
otherwise.

## 1. VERDICT (prereg §5, frozen decision rule — FINAL for this corpus)

**CONFIRMED** — P1 AND P2 both pass on the decisive series (primary corpus
2017-01-03..2023-09-29, fixed ON definition vol20 > 0.135, 19 ON-eligible
60-trading-day blocks). Echoing the prereg's §5 consequence string verbatim:

> authorizes ONLY a design PR for a vol-gated bull deployment window
> (shadow/sizing-first, operator-gated; no direct production change;
> survivor-clean confirmation happens at the PIT-universe / live-shadow stage,
> not in this corpus)

| leg | statistic | value | bar | outcome |
|---|---|---|---|---|
| positive control | unconditional primary mean spread | **+0.13919** | > 0, checked BEFORE any conditional read (V13) | PASS |
| P1(a) NW | mean +0.18400, SE 0.09428, t (df=18) | **+1.952** | one-sided 95% CI excludes 0 (t_crit 1.734; CI lower +0.02050) | PASS |
| P1(b) bootstrap | stationary block bootstrap q05 (10,000 resamples, E[block]=2, seed 0) | **+0.02096** | q05 > 0 | PASS |
| P1 anti-lottery | winsorized ±0.50 SD ON mean | **+0.03609** | ≥ 0 | PASS |
| P1 conjunction | disagreement | False | both legs must agree | **P1 PASS** |
| P2 | paired ON−OFF mean diff over 11 blocks | **+0.12769** | > 0 | PASS |
| P2 | block-t | **+2.378** | ≥ 1.0 | **P2 PASS** |
| guard | N ON-eligible blocks | 19 | ≥ 15 | PASS |
| guard | ρ̂₁ / ESS on the decisive series | +0.205 / **12.55** | ESS ≥ 6 | PASS (measurable) |

The realized effect (+0.184 SD ON-state block mean) sits below the prereg §5
power section's exploratory point (+0.67..+0.76) but clears the one-sided bar
under both dependence-robust legs; realized ESS 12.55 lands between the prereg's
N=19 independence case (MDE 0.32) and its ESS-floor case (MDE 0.65)
`[DERIVED — comparison against the prereg §5 power table]`. All 39 weekly
ON-state values behind it are committed in the series CSV; nothing here changes
production.

## 2. The decisive block series (primary corpus, fixed definition — P1's input)

19 ON-eligible blocks (≥15 ON days of 60), per-block ON outcome = mean
DGTW-adjusted top-decile spread over that block's ON-state weekly
cross-sections. Weekly date ranges `[DERIVED — block index joined to the
committed series CSV]`; all other columns `[VERIFIED — committed blocks CSV,
table primary_fixed]`:

| block | weekly dates | ON days | n ON wk | n OFF wk | ON mean | ON mean w50 | OFF mean | ON−OFF |
|---|---|---|---|---|---|---|---|---|
| 4 | 2017-12-14..2018-03-07 | 26 | 5 | 7 | +0.2857 | +0.1174 | +0.4333 | −0.1476 |
| 5 | 2018-03-14..2018-06-01 | 36 | 8 | 4 | +0.2922 | +0.0547 | +0.1593 | +0.1328 |
| 7 | 2018-09-04..2018-11-20 | 33 | 6 | 6 | +0.5480 | +0.1158 | −0.0053 | +0.5533 |
| 8 | 2018-11-28..2019-02-20 | 44 | 9 | 3 | +0.6601 | +0.1711 | +0.5278 | +0.1323 |
| 10 | 2019-05-23..2019-08-12 | 25 | 5 | 7 | −0.1055 | −0.0893 | −0.3049 | +0.1994 |
| 11 | 2019-08-19..2019-11-05 | 36 | 7 | 5 | −0.0307 | −0.0182 | −0.0358 | +0.0051 |
| 13 | 2020-02-10..2020-04-29 | 56 | 11 | 1 | +0.6954 | +0.2205 | +0.6563 | +0.0391 |
| 14 | 2020-05-06..2020-07-24 | 57 | 12 | 0 | +0.3041 | +0.1032 | — | — |
| 15 | 2020-07-31..2020-10-19 | 37 | 8 | 4 | +0.4716 | +0.0929 | +0.4988 | −0.0272 |
| 16 | 2020-10-26..2021-01-14 | 28 | 6 | 6 | +0.4654 | +0.0496 | +0.3594 | +0.1059 |
| 17 | 2021-01-22..2021-04-13 | 46 | 9 | 3 | −0.0692 | −0.0618 | −0.0108 | −0.0585 |
| 18 | 2021-04-20..2021-07-08 | 17 | 3 | 9 | +0.3858 | +0.1305 | +0.2082 | +0.1776 |
| 20 | 2021-10-08..2021-12-28 | 35 | 7 | 5 | −0.7131 | −0.2261 | −0.9299 | +0.2168 |
| 21 | 2022-01-04..2022-03-24 | 58 | 11 | 1 | −0.3306 | −0.1413 | +0.1741 | −0.5046 |
| 22 | 2022-03-31..2022-06-21 | 60 | 12 | 0 | +0.1864 | +0.0272 | — | — |
| 23 | 2022-06-28..2022-09-15 | 60 | 12 | 0 | −0.2945 | −0.0682 | — | — |
| 24 | 2022-09-22..2022-12-09 | 60 | 12 | 0 | −0.1922 | −0.0355 | — | — |
| 25 | 2022-12-16..2023-03-09 | 60 | 12 | 0 | +0.4035 | +0.0997 | — | — |
| 26 | 2023-03-16..2023-06-05 | 35 | 8 | 4 | +0.5337 | +0.1435 | +0.4775 | +0.0561 |

13/19 ON means positive; ON-dominant blocks (≥45 ON days): 13, 14, 17, 21, 22,
23, 24, 25 — the frozen count of 8 (V9). P2's 11 paired blocks (≥15 days AND
≥1 weekly cross-section in EACH state) are 4, 5, 7, 8, 10, 11, 15, 16, 18, 20,
26; the ON−OFF difference is positive in 9 of 11.

## 3. All four corpus × state-definition tables (P1-style and P2-style)

Only the first row decides; the rest are the prereg's declared non-decisive
sensitivity/secondary reports. Secondary-expanding carries no P1/P2 block in
the results JSON; its row is `[DERIVED — recomputed from the committed blocks
CSV with the runner's frozen P2 selection rule and an iid mean/SE on the
eligible ON means; no NW/bootstrap leg is computed for it]`. All other rows
`[VERIFIED — results JSON]`.

| corpus × definition | decisive | N elig | ON mean | NW t (crit) | boot q05 | wins mean | ρ̂₁ / ESS | P1-style | P2: n, diff, t | P2-style |
|---|---|---|---|---|---|---|---|---|---|---|
| primary × fixed | **YES** | 19 | **+0.18400** | +1.952 (1.734) | +0.02096 | +0.03609 | +0.205 / 12.55 | **PASS** | 11, +0.12769, +2.378 | **PASS** |
| primary × expanding | no | 19 | +0.15390 | +1.533 (1.734) | −0.01098 | +0.02531 | +0.404 / 8.07 | fail | 11, +0.04960, +0.790 | fail |
| secondary × fixed | no | 26 | +0.19696 | +2.703 (1.708) | +0.07135 | +0.04153 | +0.227 / 16.37 | pass | 17, +0.13813, +3.353 | pass |
| secondary × expanding | no | 21 | +0.15723 | n/a (not computed) | n/a | n/a | n/a | n/a | 12, +0.06294, +1.069 | pass (t ≥ 1.0) |

Read honestly: the confirmation is definition-sensitive. The expanding-tercile
sensitivity variant — same corpus, same machinery, threshold defined from the
expanding vol history instead of the frozen 0.135 — fails both its P1-style
legs (NW t 1.533 < 1.734; boot q05 −0.011) and its P2-style block-t (0.790).
The two definitions share 18 of their 19 eligible blocks; the frozen fixed
threshold was the exploratory tercile edge rounded, and the prereg froze
FIXED as decisive before any scoring, so the verdict stands as preregistered —
but the variant's failure bounds the claim's robustness and belongs in any
downstream design PR's risk section. The secondary corpus (2017-01..2026-03,
formation-contaminated, cannot decide) is directionally stronger than the
primary on the fixed definition (ON mean +0.197, NW t +2.70), consistent with
the formation window being part of it.

## 4. Tilt control (vol-matched, reported only — prereg §6)

STD60-cohort-matched top-decile outcome (per-date STD60 terciles, self-excluded
cohort-mean benchmark) on the primary corpus, fixed definition:

| cohort-matched outcome | value |
|---|---|
| ON-state weekly mean | **+0.15056** |
| OFF-state weekly mean | +0.11058 |
| unconditional weekly mean | +0.12998 |

The ON-state advantage survives when each top-decile name is benchmarked only
against its own volatility cohort — the ON-state spread is not a mechanical
artifact of the top decile tilting into high-vol names while high-vol names
outperform in ON states. (Reported, not a decision leg.)

## 5. Estimand and coverage detail

- Weekly grid: 465 scored cross-section dates total (340 primary — the frozen
  V9 count — plus 125 secondary-extension), every grid date scored, zero drops;
  165 of the 340 primary weekly dates are ON under the fixed definition
  `[DERIVED — count over the committed series CSV]`.
- V12 usable-names floor (≥100) never binding: min 153, median 292, max 292
  usable names per date `[DERIVED — aggregated from the committed series CSV]`.
  Top-decile size 15..29 names.
- DGTW ≥15/cell floor: mean flagged-unadjusted fraction 0.265 (max 0.484 on the
  thinnest early dates) `[DERIVED — aggregated from the committed series CSV]` —
  the prereg's declared flag-don't-drop mechanism, recorded per date in the CSV.
- Weekly ON/OFF spread means behind the block aggregation (primary, fixed):
  ON +0.16485 over 165 dates vs OFF +0.11500 over 175 dates `[DERIVED —
  committed series CSV]`.

## 6. Refit ledger (V5/V6/V7/V8)

- 39 expanding refits, cutoffs 2016-06-30..2025-12-31, each the last SPY
  trading day of its quarter, strictly increasing (V5 assert); 30 in the
  primary sub-ladder 2016-Q2..2023-Q3. Train rows grow 17,095 → 691,203; every
  refit's train_min_date = 2016-01-04 and every refit's max train-row date
  + 60 td ≤ its cutoff (realized labels only, V7 asserted per refit). Total fit
  time 139.6 s of the 168.7 s runtime `[VERIFIED — ledger fit_seconds sum]`.
- 37 of 39 refits were consumed in scoring; the two unused are deterministic
  calendar facts: 2016-06-30 (first scoreable 2016-09-26, always superseded by
  a newer admissible refit before the corpus starts) and 2025-12-31 (first
  scoreable past the last grid date) `[VERIFIED — ledger
  refit_used_by_score_date]`. Per-cutoff booster sha256 digests and the
  refit-used-by-date map (465 dates) are in the committed ledger JSON.
- Embargo: C + 60 td ≤ d asserted per grid date, newest-admissible asserted per
  grid date (V6); primary dates all resolved within the primary sub-ladder (V5).
- Normalization replay: every cutoff reproduced the artifact's per-column norm
  kinds exactly (158 global_z / 5 robust_z / 9 identity, 39/39 `[VERIFIED — run
  log]`); the replayed sentiment trained_zeroing contract equals the artifact's
  stored contract (V8; replay metadata embedded in the results JSON —
  526,863 zeroed rows + 7,627 warmup-zeroed).

## 7. Guard outcomes and deviations

- **All V1–V14 guards passed**; the runner exited 0 on its single execution
  `[VERIFIED — run log + exit code 0]`. No fix-and-rerun; no parameter touched;
  the script ran once and only once. The one-shot marker (V1) now forbids any
  re-execution against these committed output paths.
- V2 asserted the executing bytes equal a freshly fetched origin/main's copy at
  `88c589c0` (runner sha256 `e6002a85…7fe296`, recorded in the results JSON
  `pins.runner_identity`).
- V9 frozen-geometry recompute matched the prereg's counted numbers EXACTLY:
  1,697 corpus td; 821/808 ON days (fixed/expanding); expanding threshold first
  defined 2018-01-31; 28 complete blocks; 19/19/18 eligible
  (fixed/expanding/both); 8/8 dominant; 340 weekly grid dates `[VERIFIED —
  results JSON frozen_geometry_measured]`.
- V13 ordering held: the positive control was computed and passed before any
  conditional statistic.
- Zero deviations from the merged prereg or runner. Runtime 168.7 s under
  caffeinate, in line with the prereg §4 estimate ("minutes").

## 8. Pins and reproduction

All digests `[VERIFIED — results JSON pins block / shasum before commit]`:

- orchestrator main (runner source + execution base): `88c589c01b706ce058324865548d567776aca21a` (= the #1002 merge commit; prereg #1001 merged immediately prior at `bd40ea13`)
- runner file sha256: `e6002a85225e01f743aabcfd2fbc6c89cb6b6124a80bba3b3bc7b90347fe5296` (git blob `6f9a2143`)
- served artifact: `artifacts/prod/panel-ltr.alpha158_fund.json`, sha256 `6461b827…546d15`, config fingerprint `sha256:f8fb2259b2bf1537` (V3 asserts passed: 172 feature_cols, 172 norm kinds, `fwd_60d_excess`, lookahead 60, best_iter 100); params VERBATIM with objective `rank:pairwise`, seed 42 (V4 — zero delta)
- training frame: `data/alpha158_291_fundamental_dataset.parquet` sha256 `870f68eb…29bf7e` (292 tickers, data start 2016-01-04 — both asserted)
- production trainer helpers: `scripts/train_production_model.py` sha256 `f35e8778…ed3aec` (imported read-only, V8)
- SPY store: `data/ohlcv/SPY/1d.parquet` sha256 `68665523…b0ee` — identical to the #992 moe and #999 tail_q90 runs' pins, so all three screens/confirmatories share one price store
- python: `/Users/renhao/git/github/RenQuant/.venv` (xgboost 2.1.4, numpy 2.0.2, pandas 2.3.3, scipy 1.13.1 `[VERIFIED — version probe before run]`)
- execution: isolated worktree of orchestrator main at `88c589c0` (branch `research/vol-switch-results`); the runner chdir()s into the umbrella only to READ; wrote only the four `doc/research/data/2026-08-18-vol-switch-*` outputs inside the worktree (V14); no live-tree or production-path writes.
- output digests: results JSON `09ceb639…2ee9aa`, series CSV `f5812870…116c0b`, blocks CSV `37d9b1b3…c3c72`, refit-ledger JSON `cb8bfd06…850ab` `[VERIFIED — shasum at commit time]`.

The runner is deterministic by construction (fixed seeds 42/0, fixed calendar,
stable row sort before the DMatrix build, no early stopping, no search;
wall-clock stamps in metadata only) — re-executing at these pins reproduces
these outputs bit-for-bit (reproduction is not a re-run of the confirmatory;
the one-shot budget is spent).

## 9. What happens next (per the merged prereg — no new decisions here)

CONFIRMED authorizes ONLY a design PR for a vol-gated bull deployment window —
shadow/sizing-first, operator-gated, no direct production change. Two facts the
design PR must carry into its risk section, recorded here so they cannot be
lost: (a) the expanding-definition sensitivity variant FAILS both its P1-style
legs on the same corpus (§3) — the effect's certification is specific to the
frozen fixed threshold; (b) survivorship is state-dependent and undischarged in
this corpus (prereg §3/CORRECTIONS #6) — the survivor-clean confirmation lives
at the PIT-universe / live-shadow stage, which is also where the PARTIAL-grade
activation burden would have applied had P2 failed. Nothing is deployed,
nothing is sized, no production surface changes on this verdict alone.
