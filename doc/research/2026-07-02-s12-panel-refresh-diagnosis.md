# S12 panel-refresh root-cause diagnosis — why `transformer_v4_wl200_clean.parquet` ends 2026-02-10

STATUS: read-only diagnosis memo (S12's mandated FIRST slice per the merged #212
design `doc/design/2026-06-30-shadow-scorer-freshness.md` §3.1/§4 and the #231/
H2-roadmap S12 row: "panel-refresh-prerequisite diagnosis FIRST"). No code, no
config, no data, no scheduler, and no live-tree file was changed; no builder or
training was run. All evidence gathered 2026-07-02 by read-only inspection
(file reads, parquet column scans, `launchctl list`, log reads, `gh pr view`).

## 0. Verdict (lead with the conclusion)

**The panel ends 2026-02-10 because it is a ONE-OFF research snapshot — built
once (bar frontier 2026-05-07, file written 2026-05-18) by a recipe that is NOT
committed anywhere, on NO refresh cadence — and nothing has rebuilt it since.**
On the design's dichotomy:

- **"builder-never-ran"** — CONFIRMED, in a sharper form: the builder chain ran
  exactly once and *cannot* re-run, because no committed script produces this
  exact file (see §2). This accounts for the entire non-structural gap.
- **"label-join dropna clip (the #26 fund-freshness family)"** — PRESENT but
  **NOT the defect**. The fwd_5/20/60d `dropna` clips the TRAINING axis, which
  is required (unlabeled rows are untrainable; the trainer re-drops them anyway
  at `renquant-model/src/renquant_model_patchtst/hf_trainer.py:347`). It
  explains only the *structural* ~86-calendar-day lag, never the freeze. The
  #26 bug was this same clip applied to the SERVING axis — that is not what is
  happening here.
- **"something else"** — YES, three additional binds discovered (§4) in the
  *just-merged* refresh/promote chain (RenQuant #424 + #419, both merged
  2026-07-01). As wired today, that chain **still cannot** advance the served
  corpus or the served pin: the refresh rebuilds the WRONG recipe (fails its
  own swap gate closed), the promote applies a raw 28d calendar SLA to the
  label-clipped axis (structurally unsatisfiable — the #26 failure *pattern*
  recurring inside the new freshness gate itself), and the weekly retrain
  cutoff is pinned to a static WF source manifest whose latest cutoff is
  2026-03-09. The scheduled job is also still not installed.

**Ownership conclusion:** no orchestrator-owned defect. The corpus recipe,
refresh module, promote script, and wrapper are umbrella-`RenQuant/scripts`
artifacts whose concerns the #212 §5 ownership table assigns to
**base-data/model** (panel refresh), **backtesting/model** (promote mechanics),
and **umbrella ops** (wrapper + launchd). The orchestrator-owned pieces are
correct: `build_patchtst_wf_manifest` faithfully trains the cutoffs its
`--source-manifest` input names, and the merged #213 monitor already
horizon-adjusts the label-clipped axis (the semantics the promote is missing).
Hence: this memo + precisely-scoped follow-ups (§5), no fix PR here.

## 1. What the served corpus actually IS (recipe identification)

The #424 refresh module assumes the corpus is the output of
`scripts/transformer_dataset_builder.py` (raw 5-channel OHLCV, 292-ticker
tier_A∪tier_B universe). Ground truth says otherwise:

| Property | `transformer_dataset_builder.py` output | served `transformer_v4_wl200_clean.parquet` (measured) |
|---|---|---|
| Features | 5 raw channels (O/H/L/C/V), z-scored | **148 qlib alpha158** (KMID…VSUMD60) **+ 5 FUND + 3 PEAD + 3 SUE + 3 SENT** (166 cols + labels + `split_label`) |
| Universe | 292 tickers (tier_A∪tier_B) | **142 tickers = the live watchlist**, all ending exactly 2026-02-10 |
| Label rows | keeps NaN forward-label rows (via inner join on a labels file that retains NaNs) | **zero NaN labels** (fwd_60d NaN rate = 0.0) — label-dropna applied at build |

The 14 extra columns are exactly the FUND/PEAD/SUE/SENT families emitted by
`scripts/build_alpha158_fund_panel.py` (whose sentiment-survivor columns were
added on **2026-05-18** — the same day as the corpus file's mtime). The
2026-06-16 retrain log confirms the trainer consumed this engineered panel
(`panel … n_feat=172 … 142 tickers … dates=2016-01-04..2026-02-10`), i.e. the
served shadow corpus is an **alpha158+fund-family panel restricted to the
watchlist with labels dropna'd** — the `build_alpha158_qlib.py` (label
`shift(-h)` + `dropna(subset=[fwd_5d/20d/60d_excess])`, line 448 family) →
`build_alpha158_fund_panel.py` chain. **No committed script writes the file
`transformer_v4_wl200_clean.parquet`** — every reference in the repo *reads* it
(`--dataset` defaults, the WF gate, the calibrator, the promote's SLA source
list). The filename is a historical misnomer kept as a stable path; the exact
2026-05-18 invocation was ad-hoc research and is not reproducible from any
committed entrypoint.

## 2. Why it ends 2026-02-10 — the causal chain, quantified

The label clip is deterministic arithmetic: with fwd_60d labels dropna'd, the
max labeled row = bar frontier − 60 trading days. Working backwards
(NYSE calendar; Presidents Day 02-16 + Good Friday 04-03 in the window):
**2026-02-10 + 60 trading days = 2026-05-07** — the OHLCV bar frontier embedded
in the last (only) build. The file was written 2026-05-18 15:27; the on-disk
`transformer_panel_labels.parquet` sibling (2026-05-05 build, bar frontier
2026-05-05, max labeled 2026-02-06) is a separate, slightly older pass of the
same arithmetic. Since 2026-05-18 nothing has touched the corpus.

The gap split, as of the last completed session 2026-07-01:

| Component | Span | Size |
|---|---|---|
| Total panel staleness | 2026-02-10 → 2026-07-01 | **141 calendar days** |
| Structural floor (fwd_60d clip, correct) | achievable frontier 2026-04-06 → 2026-07-01 | **86 calendar days** (60 trading days) |
| **Non-structural excess (the defect)** | 2026-02-10 → 2026-04-06 | **55 calendar days** (~38 trading days ≈ the "~2 months" the S12 brief anticipated) |

The 55-day excess is exactly the age of the embedded bar frontier
(2026-05-07 → 2026-07-01 = 55 days): the corpus is stale by precisely how long
its builder has not re-run. Empirical cross-check: the PROD sibling panel on
the same alpha158+fund pipeline (`alpha158_291_fundamental_dataset.parquet`),
which IS on a daily cadence (mtime 2026-06-30), has labeled frontier
**2026-04-02** (= its 06-30 bar frontier − 60 trading days) — the achievable
frontier is real and currently being achieved by the prod twin of this exact
recipe.

Answers to the three §3-of-the-brief diagnosis questions:

- **(a) Scheduled job?** NONE. `launchctl list | grep renquant` (2026-07-02)
  shows the other weekly jobs (`weekly-wf-promote`, `weekly-fundamental-refresh`,
  `weekly-apy104`) but **no `weekly-retrain-patchtst`**; `~/Library/LaunchAgents/`
  has no matching plist. The wrapper has only ever run manually — 3 log files
  (2026-06-07 / 06-08 / 06-16), nothing since. And no run has ever rebuilt the
  corpus: the refresh wiring only merged 2026-07-01 (#424) and has never
  executed (no refresh logs, no `<corpus>.bak`, corpus mtime still 2026-05-18).
- **(b) Source-manifest bound?** YES, as a *secondary* bind on the retrain
  cutoff (not on the panel): `walkforward_manifest_v2_20260602.json` is static,
  39 cutoffs, **latest 2026-03-09**; the wrapper's weekly mode trains only that
  latest cutoff (the 06-16 run: 6 cutoffs, 2024-01-01 → 2026-03-09). See §4-B3.
- **(c) Label-join clip?** Present, correct, training-axis only (§0).

## 3. Why the served pin is even staler than the panel (context, from #212)

Two already-diagnosed compounding freezes (#212 §1.2/§1.3, confirmed): the
served artifact `pt07_strict_trainfit_embargo60_20260522/seed_44` (metadata:
`trained_date=2026-05-22`, `effective_train_cutoff_date=2024-11-13`,
`effective_selection_cutoff_date=2026-02-10`, `lookahead_days=60`) was never
advanced by any retrain because no promote existed until #419. This memo's
subject is the *prerequisite* layer beneath that: even the new promote cannot
act until the corpus itself advances — and §4 shows the merged chain cannot yet
advance it.

## 4. The three binds that survive #424 + #419 (the "something else")

**B1 — the refresh rebuilds the WRONG recipe, so its own swap gate fail-closes
forever.** `refresh_transformer_corpus.py`'s default `builder_fn` invokes
`scripts/transformer_dataset_builder.py` (raw-OHLCV, 292 tickers). Its output
cannot match the served corpus's 166-column alpha158+fund schema or its
142-ticker coverage, so the module's (correct) swap gate — schema/feature/
label-horizon/ticker-coverage parity — rejects the staged rebuild and keeps the
frozen corpus. #424's docstring flags this seam ("point `builder_fn` at the
exact recipe"); ground truth (§1) is that the divergence is total, so the seam
is live, not hypothetical: **as wired, the weekly refresh can never advance the
served corpus.** Also, #424's stated root-cause #2 (research-ticker OHLCV
freeze) does not bind the served corpus: all 142 served tickers' bars are fresh
to 2026-07-02; only the 152 non-watchlist universe names are frozen (139 at
2026-05-12) — they bind the module's own full-universe freshness guard, which
its own fetch step repairs.

**B2 — the promote's 28d calendar SLA on the label-clipped axis is structurally
unsatisfiable (the #26 failure pattern, recurring inside the new gate).**
`promote_shadow_patchtst.py` `DEFAULT_SOURCES` puts `transformer_panel` on
`axis=fast, sla_days=28, date_col=date`, and `source_sla_verdict` computes
`age = now − max(date)`. But the corpus's max `date` is *structurally* ≥ ~86
calendar days behind (the fwd_60d clip) — a maximally fresh rebuild scores
age ≈ 91d > 28d, so the promote returns `RC_NOT_FRESH` (10) **forever**, even
after a perfect refresh. This contradicts both #424's own FWD-60D note ("the
built corpus legitimately ends ~today-60 trading days") and the merged
orchestrator #213 monitor, which explicitly horizon-adjusts
`label_observation_cutoff` by the artifact's stamped `lookahead_days` (=60
here) so the population is "aged from the achievable frontier, not born-BREACH".
The promote needs the same horizon-adjusted key (or must gate the fast axis on
the rawlabel/bar frontier, which is not label-clipped).

**B3 — the weekly retrain cutoff is pinned to a static manifest (latest
2026-03-09).** After a corpus refresh, the next weekly retrain would train at
cutoff 2026-03-09; `effective_train_cutoff` and `effective_selection_cutoff`
advance once past the served pin (2024-11-13 / 2026-02-10) — then every later
week re-trains the SAME cutoff, `cutoffs_advance` correctly refuses, and the
pin re-freezes with the monitor degrading again. The weekly mode must derive
its cutoff from the refreshed corpus frontier (or an advancing source manifest)
rather than `walkforward_manifest_v2_20260602.json`'s frozen tail.

**Plus phase-2 not done:** the `com.renquant.weekly-retrain-patchtst` plist is
still not installed (§2a), so even the fixed chain has no cadence yet.

## 5. Remediation path (per #212 §4 + the §5 ownership table)

Order is load-bearing (fresh data → retrain → validated promote → cadence):

1. **Commit the TRUE corpus recipe and point `builder_fn` at it** — owner:
   **base-data/model** (panel refresh prerequisite), implemented at the
   umbrella-script seam #424 built for exactly this (a one-line injection per
   its docstring). Cheapest correct recipe, consistent with how the corpus was
   actually made: derive the shadow corpus from the already-daily-refreshed
   prod panel — subset `alpha158_291_fundamental_dataset.parquet` to the
   142-ticker watchlist, `dropna` the three label columns, preserve the exact
   served column set/`split_label` — zero new fetch/build cost, frontier
   2026-04-02+ immediately, and the swap gate's schema/coverage parity then
   passes by construction. (The full-universe OHLCV refresh #424 also performs
   remains valuable for the research universe, but is not what unfreezes the
   served corpus.)
2. **Horizon-adjust the promote's `transformer_panel` SLA** — owner:
   **backtesting/model** (promote mechanics, umbrella script) — key the fast
   axis on `max(date) + lookahead_days` trading days (the implied bar
   frontier), mirroring #213's `label_observation_cutoff` semantics, or gate on
   the rawlabel/bar frontier. Without this, step 1 still ends in `RC_NOT_FRESH`.
3. **Advance the weekly retrain cutoff with the corpus** — owner: **umbrella
   ops** (wrapper) with the orchestrator pipeline unchanged: derive
   `LATEST_CUT` from the refreshed corpus's max labeled date instead of the
   static 2026-06-02 manifest's frozen tail.
4. **Install the launchd cadence** (`com.renquant.weekly-retrain-patchtst`) —
   owner: **umbrella ops** — only after 1–3, per #212 §3.1 ("cadence is the
   liveness signal, never the freshness key").

**Landing-loop command** (umbrella-ops action on the live tree, per #212 §4 —
NOT run by any agent; after fixes 1–3):

```bash
bash scripts/weekly_retrain_patchtst.sh   # refresh → WF retrain → validated promote
```

**Expected result:** corpus labeled frontier advances 2026-02-10 → ~2026-04-06
(bars through 2026-07-01; the prod twin already demonstrates 2026-04-02); the
retrain's `effective_selection_cutoff_date` advances to the same; the validated
promote passes §3.4 and swaps the served pin off its 2026-05-22 bytes; the #213
monitor reads the shadow population healthy with the **documented ~86-calendar-
day structural lag** — precisely the S12 fallback ledge ("serve at the
achievable frontier with a documented-lag caveat").

## 6. Evidence appendix (all read-only, 2026-07-02)

- Served corpus scan (pandas, columns only): 346,022 rows; 142 tickers; dates
  2016-01-04 → 2026-02-10; per-ticker max date = 2026-02-10 for all 142;
  fwd_60d/fwd_5d NaN rate 0.0. Schema: 148 alpha158 + `fwd_5d/20d/60d_excess` +
  `split_label` + `earnings_yield, book_to_price, gross_profitability, roe,
  asset_growth` + `days_since_earnings, pead_signal, pead_quintile_rank` +
  `sue_signal, surprise_momentum, surprise_streak` + `sentiment_pos_share,
  mean_sentiment, n_articles_log`.
- File mtimes: corpus 2026-05-18 15:27; `transformer_panel_labels.parquet`
  2026-05-05 16:08 (max date 2026-05-05; max labeled 2026-02-06; 292 tickers);
  prod `alpha158_291_fundamental_dataset.parquet` 2026-06-30 13:12 (max date =
  max labeled = 2026-04-02); `alpha158_qlib_dataset.parquet` 2026-07-02 03:02.
- OHLCV frontiers (per-ticker `1d.parquet` max index): all 142 served tickers =
  2026-07-02; the other 152 tier_A∪B names: 139 at 2026-05-12, 9 at 2026-05-29,
  2 at 2026-05-04, 2 fresh.
- Trading-day arithmetic (NYSE 2026 holidays): 2026-02-10 + 60td = 2026-05-07;
  2026-07-01 − 60td = 2026-04-06; 2026-04-02 + 60td = 2026-06-30.
- Scheduler: `launchctl list | grep renquant` — no `weekly-retrain-patchtst`;
  `~/Library/LaunchAgents/` — no matching plist. Retrain logs: exactly
  2026-06-07 / 06-08 / 06-16; the 06-16 log shows 6 cutoffs (2024-01-01 →
  2026-03-09) trained on `transformer_v4_wl200_clean.parquet`
  (`dates=2016-01-04..2026-02-10`, `n_feat=172`, 142 tickers).
- Merged chain: RenQuant #424 (refresh, merged 2026-07-01T22:09Z) and #419
  (validated promote, merged 2026-07-01T22:51Z); wrapper
  `weekly_retrain_patchtst.sh` wires refresh → WF build → promote. Key code
  points read: `refresh_transformer_corpus.py::_default_build_corpus` (invokes
  `transformer_dataset_builder.py`), `promote_shadow_patchtst.py`
  `DEFAULT_SOURCES` (`transformer_panel`, fast, `sla_days=28`, `date_col=date`)
  and `source_sla_verdict` (`age = now − max(date)`, no horizon adjustment);
  `transformer_dataset_builder.py:189` (inner label join),
  `build_alpha158_qlib.py:448` (label dropna), `hf_trainer.py:347` (trainer
  label dropna). Served pin metadata: `trained_date=2026-05-22`,
  `effective_train_cutoff_date=2024-11-13`,
  `effective_selection_cutoff_date=2026-02-10`, `lookahead_days=60`.
- Orchestrator #213 monitor (merged 2026-07-01T22:14Z):
  `model_freshness_monitor.py` keys the shadow population on a
  `label_observation_cutoff` explicitly horizon-adjusted by the artifact's
  stamped `lookahead_days` — the semantics the promote's panel SLA lacks (§4-B2).
