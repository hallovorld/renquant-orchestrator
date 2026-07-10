# Decision-ledger health check + first gate retro-verification (2026-07-10)

STATUS: research memo — health check + earliest-signal probe. **Every result in
§3 is DIRECTIONAL / LOW-POWER** (3-9 runs, 1-5d horizons, one regime, one
scorer, overlapping forward windows). Nothing here is a gate verdict, a
promotion input, or a config-change recommendation on its own.

Read-only analysis; no production store was written. Evidence + reproducible
script: `doc/research/evidence/ledger_health/analyze_ledger_health_2026-07-10.py`
and `.../ledger_health_2026-07-10.json` (all numbers below are `[VERIFIED]`
against that snapshot unless tagged `[GUESS]`).

## 0. Bottom line

1. **The S5 verdict ledger is alive and complete at run grain**: 5/5 NYSE
   sessions since enable (2026-07-06 → 07-10) recorded, 23 runs, exactly 6
   gate rows per run, zero nulls. But **4 of the 6 gates carry structurally
   wrong or vacuous inputs** (F1-F3, F6 below) — the ledger currently proves
   *that* runs happened, not *what the gates decided*. Per-name retro-analysis
   must (and can) go through `runs.alpaca.db candidate_scores ⋈
   ticker_forward_returns` instead; that substrate is healthy.
2. **The per-name outcome half of the ledger is empty by design** — the
   `decision_outcomes` table does not exist yet in the ledger DB; the outcome
   observer only writes once all of 5d/20d/60d have matured, so the first
   ledger-native outcome rows land ≈ **2026-09-29** (60 trading days after
   07-06).
3. **Single most mature directional finding** (fwd_5d, matured for the six
   canonical XGB-era runs 06-23 → 07-02, SPY-relative): the VetoWeakBuys floor
   is ordered correctly — admitted names +1.28pp (n=95, hit 62%) vs the
   0.5σ-1.0σ marginal band **−0.41pp (n=74, hit 41%)**, deep-vetoed −0.87pp
   (n=316). Earliest signal says the 1.0σ floor is *not* leaving obvious money
   in the 0.5σ-1.0σ band. DIRECTIONAL/LOW-POWER.
4. Companion finding for the blocked #145/#190 demean validation: demean-ON
   would have admitted ≤1 name on 7 of 9 XGB-era runs (0 on 2), added **zero**
   names ever, and the names it would have dropped went on to **beat** SPY at
   5d (+0.77pp, n=65, hit 62%) — directionally supports the 2026-06-29
   emergency revert to demean OFF. The *formal* #190 metric is fwd_60d and
   remains unevaluable until ~Sep.
5. The monthly mechanical gate scorecard is blocked by ~10 concrete gaps (§4),
   half of them one-line stamping fixes in
   `renquant-pipeline/src/renquant_pipeline/decision_ledger.py`.

## 1. What exists where (storage map)

| store | content | state 2026-07-10 |
|---|---|---|
| `~/renquant-data/decision_ledger.db` · `decision_ledger` | run×gate verdict rows (S5, enabled 07-05 via strategy-104 s5 PR; writer = pipeline `DecisionLedgerWriteTask`) | 142 rows at snapshot (live-written during analysis: 136 → 142 within minutes); WAL — readonly access needs `immutable=1` |
| `~/renquant-data/decision_ledger.db` · `decision_outcomes` | per-name outcomes w/ fwd_5d/20d/60d placeholders (`ledger_attribution.py` schema) | **table absent** — `write_outcomes` has never run in prod (deliberate: observer is sole writer, atomic-after-60d; see `task_decision_ledger.py` docstring) |
| `RenQuant/data/runs.alpaca.db` · `candidate_scores` | per-name mu/raw/rank/sigma/expected_return/blocked_by, kept AND vetoed (since 2026-05-04) | healthy on full runs; defects in §2.3 |
| `RenQuant/data/runs.alpaca.db` · `ticker_forward_returns` | fwd_1d/5d/10d/20d/60d per (as_of, ticker) | populating daily (observer job last ran 07-10 20:55); coverage caveats in §2.4 |
| `RenQuant/data/runs.alpaca.db` · `gate_verdicts` | older parallel verdict table | **0 rows, ever** — this is what the `gate_verdict_age` KPI cross-checks |
| `RenQuant/data/runs.alpaca_shadow.db` | shadow-arm pipeline_runs/candidate_scores | owns 17 of the 23 ledger run_ids |

## 2. Ledger health

### 2.1 Coverage since enable

Every NYSE session since the 07-05 enable is covered (07-03 holiday, 07-04/05
weekend — first tradable session was 07-06):

| session | ledger rows | runs | active-path full run | shadow runs |
|---|---|---|---|---|
| 2026-07-06 | 18 | 3 | `ebb9c2ca` | 2 |
| 2026-07-07 | 12 | 2 | `dc2a3247` | 1 |
| 2026-07-08 | 12 | 2 | `369734c3` | 1 |
| 2026-07-09 | 24 | 4 | `40e2dbd0` | 3 |
| 2026-07-10 | 72 | 12 | `6f9d5284` | 10 + 1 orphan |

23/23 runs have exactly the formatter's 6 gates (conviction, model_admission,
regime, rotation, vol_gate, wash_sale); no null reasons/inputs. Verdicts:
conviction 18 allow / 5 block ("no candidates"), rotation 23 halve, everything
else 23 allow. 4 pre-enable rows exist (as_of 2026-06-11, scope `book`,
gates bear_override/drawdown_breaker/kelly_sizing/transition_window — the
false-BEAR autopsy demo from the #133 era; harmless, but a scorecard must
window on `as_of >= 2026-07-06`).

Run attribution: 5 active-path (in `runs.alpaca.db`), 17 shadow-path (in
`runs.alpaca_shadow.db` — the two-arm shadow A/B runner explains the 07-10
burst `[GUESS]`), and **1 orphan** `2026-07-10-unscoped` — the formatter's
fallback when `ctx.run_id` is absent (`task_decision_ledger.py`), which is
un-joinable to any run by construction (F4).

### 2.2 Verdict-fidelity defects (the important part)

All in `renquant-pipeline/src/renquant_pipeline/decision_ledger.py` unless noted.

- **F1 — conviction rows don't reflect the real gate.** `_conviction_gate_verdict`
  reads `config["conviction_gate"]` but the live config nests it at
  `ranking.panel_scoring.conviction_gate` → `mu_floor` stamps as **0.0** on
  23/23 runs (actual floor 0.03). `n_above_floor` counts `mu > 0` over
  `ctx.candidates` **after** the gates already pruned it — hence tautologies
  like "16/16 above floor". Demean flag and xs_mean are not stamped. The real
  per-name record is `candidate_scores.blocked_by =
  'conviction:mu_below_floor'` (14 name-days this week on the active path).
- **F2 — vol_gate / wash_sale rows are structurally vacuous.** They read
  `getattr(ctx, "blocked_by", {})`, but the kernel `InferenceContext` has no
  such dict — `blocked_by` is a `str|None` scalar (`context.py:194`); the
  per-ticker map is `_blocked_by_ticker`. Result: "none blocked"/allow is the
  only value these rows can ever take (e.g. the 07-02 run had
  `risk_gate_vol_dropped=32`; a ledger row for that run would still read
  "none blocked").
- **F3 — rotation verdict semantics.** 0 considered / 0 viable maps to
  `halve` (23/23 rows). In the GateRegistry algebra a `halve` multiplies size
  ×0.5 — a scorecard (or any future consumer of the aggregate) would read a
  phantom daily size-halving that never happened.
- **F4 — `<date>-unscoped` fallback run_id** breaks joins and can collide
  (INSERT OR IGNORE silently merges two unscoped runs on the same day).
- **F5 — no config-arm discriminator.** Active, golden and shadow arms all
  stamp scope `strategy-104`; attribution requires probing multiple runs DBs
  by run_id (and the shadow DB, being WAL, rejects `mode=ro` opens — needs
  `immutable=1`).
- **F6 — the binding gates are missing entirely.** VetoWeakBuys — the single
  most binding admission gate (123 of 137 active-path blocks this week) — has
  no ledger row, nor do kelly/sizing, correlation, or any **exit** gate
  (§3c).

### 2.3 Per-name substrate (active path)

| run | candidates (pre-veto) | holdings | mu/rank non-null | blocked_by present | buys emitted |
|---|---|---|---|---|---|
| 07-06 `ebb9c2ca` | 35 | 6 | 41/41 | yes | 2 (AVGO, MCHP) |
| 07-07 `dc2a3247` | 33 | 7 | 40/40 | yes | 1 (ZM) |
| 07-08 `369734c3` | **0** | 5 | 5/5 | n/a | 0 |
| 07-09 `40e2dbd0` | **0** | 5 | 5/5 | n/a | 0 |
| 07-10 `6f9d5284` | 85 | 3 | 88/88 | yes | 4 (FTNT, APH, ZM, NFLX) |

- mu / raw / rank / expected_return stamp correctly on every candidate row
  (raw_score is null only on holding-role rows). `sigma` stamps on only
  ~10-12 rows/run.
- **`selected` is 0 on every row since 07-06 even though buys were emitted** —
  admits are only recoverable by joining `trades` (gap A5).
- **07-08/07-09 produced zero candidates** (conviction ledger row honestly
  says "block: no candidates"; counters `no_candidate_streak` 1→2). The
  07-06/07-07 cross-sections were also half-size (35/33 vs 76-85 normal).
  Cause not root-caused here; consistent with the chronic breadth/veto-floor
  problem tracked via strategy-104#53 `[GUESS]`. 07-10 restored (85).

### 2.4 Are forward returns populating as horizons mature?

Yes at the 1d horizon, with a coverage caveat:

| as_of | tfr rows | fwd_1d filled | fwd_5d | candidate names that day |
|---|---|---|---|---|
| 07-06 | 42 | 42 | 0 (matures 07-13) | 35 |
| 07-07 | 41 | 41 | 0 (07-14) | 33 |
| 07-08 | 8 | 8 | 0 | 0 |
| 07-09 | 6 | 6 | 0 | 0 |
| 07-10 | 6 | 0 (07-13) | 0 (07-17) | 85 |

07-08/09/10 rows are **holdings+SPY only**. The 07-10 85-name cross-section
is not yet stamped. **Acceptance check (mechanical): by Mon 07-13 close,
`ticker_forward_returns` should hold ~86 rows for as_of 07-10 with fwd_1d
non-null; if it still holds 6, the observer is only tracking holdings and
vetoed-name outcomes will be unjoinable for the scorecard.** (The aged window
Apr-Jun sits at 98% fwd_20d coverage per the RS-6 KPI, so backfill has worked
historically.)

Maturity calendar for the ledger-enabled window: fwd_5d first matures
2026-07-13 (for 07-06); fwd_20d ≈ 2026-08-03; fwd_60d ≈ 2026-09-29 — which is
also when the observer writes the first ledger-native `decision_outcomes`
rows (atomic all-three-horizons rule).

## 3. First gate retro-verification — DIRECTIONAL / LOW-POWER

Method: per-run re-derivation from `candidate_scores` (pre-veto snapshot,
candidate role only), mirroring the pinned gate code: veto floor
`max(0.20, mean+1.0σ)` on calibrated rank_score; conviction admit
`expected_return ≥ 0.03`. Floor reconstruction agrees with the stamped
`blocked_by` tags on **100%** of scored name-days (both windows) — the
re-derivation is faithful. Two windows:

- **post-enable** (07-06, 07-07, 07-10): only fwd_1d matured, 2 of 3 runs.
- **XGB-era canonical** (06-23, 06-25, 06-26, 06-30, 07-01, 07-02 from the
  RS-6 canonical list + the 3 post-enable candidate-bearing runs): same
  scorer (XGB), same gate config family; fwd_5d matured for the six
  pre-enable runs; **fwd_20d matured for none; fwd_60d for none.**

Shared caveats: consecutive-run 5d windows overlap and the same names recur
(name-days are NOT independent); all-BULL_CALM; no cost model; demean was ON
for runs 06-25→06-26 and OFF otherwise (counterfactuals applied uniformly);
07-06/07 cross-sections were half-size.

### (a) VetoWeakBuys marginal entrants (0.5σ-1.0σ band)

Bands per run: `admitted_core` = rank ≥ mean+1.0σ (today's floor);
`marginal` = mean+0.5σ ≤ rank < floor (admitted under a hypothetical 0.5σ
floor); `deep_veto` = below. The min=0.20 fail-safe never bound (floors ran
0.539-0.581).

XGB-era pooled, SPY-relative (**fwd_5d matured** — the most mature view):

| band | name-days | rel_fwd_1d mean | rel_fwd_5d mean (n) | rel_fwd_5d hit |
|---|---|---|---|---|
| admitted_core | 125 | −0.07pp | **+1.28pp** (95) | **62%** |
| marginal 0.5-1.0σ | 98 | −0.07pp | **−0.41pp** (74) | 41% |
| deep_veto | 415 | +0.10pp | −0.87pp (316) | 41% |

Directional reading: the marginal band behaves like the vetoed population,
not like the admits — no earliest-signal support for relaxing the floor to
0.5σ. This is the strongest-maturity result in the memo and it is still only
6 effective sessions of 5d outcomes. Post-enable-only (fwd_1d, n=12/14/42):
flat to slightly inverted (admits −0.19pp rel, marginal +0.23pp) — 1d is
noise at this n. 20d/60d: pending.

### (b) ConvictionGate mu-floor + demean sensitivity (blocked #145/#190 validation)

Actual floor blocks (`conviction:mu_below_floor`): 55 name-days XGB-era.
Blocked names' rel_fwd_5d **+0.83pp** (n=41, hit 54%) vs admitted +1.05pp
(n=73, hit 62%): ordering correct but the floor is NOT yet visibly saving
money at 5d — blocked names still beat SPY on average. Post-enable fwd_1d:
blocked (3 names) −1.23pp rel vs admits +0.16pp — right-way, tiny n.

Demean-ON counterfactual (admit iff `mu − xs_mean ≥ 0.03`, xs_mean over the
full pre-veto snapshot — exactly the reverted #145 semantics):

| metric | value (9 XGB-era runs) |
|---|---|
| runs where demean-ON admits 0 names | 2/9 (06-25, 07-07) |
| runs where demean-ON admits ≤1 name | 7/9 (OFF admits 3-17) |
| names demean-ON would ADD | **0** in every run (xs_mean > 0 always) |
| names demean-ON would DROP | 75 name-days |
| dropped names' rel_fwd_5d | **+0.77pp** (n=65, hit 62%) — realized SPY-beaters |
| admission headroom max_mu − xs_mean | 0.027-0.057, median ≈ 0.032 vs floor 0.03 |

Directional reading: at the horizons that have matured, the #190 revert
metric (`dropped_by_demean_mean_fwd > 0`) is TRUE — demean-ON would have
dropped realized winners while adding nothing, and its admission margin
teeters on the 0.03 boundary daily. This *supports* the 2026-06-29 emergency
revert (demean OFF) but does **not** close #190: the formal metric is
fwd_60d (first evaluable ~Sep), and 5d ≠ the 60d model horizon. Do not
re-litigate the monitored exception on this memo alone.

Note: all of §3b was computed from `candidate_scores`, not from the ledger's
conviction rows — F1 makes those rows unusable for exactly this question.

### (c) Panel-exit verdicts

**Not recorded.** The formatter has no exit gate; per-ticker sell decisions
are formatted (`s5_decisions_formatted`) but deliberately unpersisted. Worse
for coverage: all 5 sell trades in the window were `model_protection` exits
and **4 of 5 were emitted by intraday monitor runs that never write the
ledger at all**. Exit evidence today lives only in `trades.exit_reason`
(historical taxonomy: model_sell 4426, rotation 417, stop_loss 372, …,
model_protection 9). The σ-blind panel-exit question (orch #195 shadow
replay) cannot be answered from the S5 ledger in its current shape.

## 4. Automation gap list — monthly mechanical gate scorecard

Blockers, each with the mechanical fix. KPI placeholder citations refer to
`doc/research/evidence/kpi_scorecards/kpi_2026-07-07.json`.

| # | gap | fix owner / shape |
|---|---|---|
| A1 | `gate_verdict_age` KPI cross-checks the **empty** `runs.alpaca.db gate_verdicts` table (0 rows ever) while real verdicts live in `~/renquant-data/decision_ledger.db` | point the KPI at the ledger DB (orchestrator, one-line source change) and drop/retire the dead table |
| A2 | F1: conviction `mu_floor` stamped from wrong config path; `n_above_floor` post-gate tautology; demean/xs_mean unstamped | pipeline `decision_ledger.py::_conviction_gate_verdict`: read `ranking.panel_scoring.conviction_gate`, count over the pre-veto snapshot, stamp `xs_mean`, `demean`, per-name pass/fail counts |
| A3 | F2: vol_gate/wash_sale read non-existent `ctx.blocked_by` → always "none blocked" | read `ctx._blocked_by_ticker` (or add a public accessor) |
| A4 | F3: rotation `halve` on 0-considered | verdict `allow` + reason `no_rotations_considered` when n_considered==0 |
| A5 | `candidate_scores.selected` = 0 on all rows since 07-06 despite emitted buys | stamp it again, or scorecard must derive admits via `trades` join (fragile: buy_pending vs filled) |
| A6 | VetoWeakBuys not in the ledger and its floor (mean+1σ value) not stamped anywhere machine-readable — this memo re-derived it (100% agreement today, but that is the triple-impl-hash failure mode waiting to recur) | add a `veto_weak_buys` gate row stamping floor, mean, std, n_dropped |
| A7 | No exit gates in the ledger + exits fire from monitor runs that skip the ledger write entirely (4/5 this week) | add exit verdict rows; wire `DecisionLedgerWriteTask` (or a sell-side equivalent) into the intraday sell pipeline |
| A8 | Per-name ledger registry absent: `decision_outcomes` unwritable before ~09-29 (observer 60d atomic rule) and `format_ticker_decisions` output is discarded; the observer's pending-query would treat any early row as "done" (the #351 poisoning trap) | build the separate per-ticker registry the `task_decision_ledger.py` docstring calls for; until then the scorecard's per-name source of truth is `candidate_scores ⋈ ticker_forward_returns` |
| A9 | `ticker_forward_returns` coverage narrowed to holdings+SPY on 07-08/09/10 (§2.4 acceptance check on 07-13); vetoed-name outcomes need full-cross-section stamping | verify/extend the observer's ticker enumeration to the day's full candidate set |
| A10 | No run_type / arm discriminator (F5) + orphan unscoped run_ids (F4): scorecard cannot mechanically pick "one canonical run per session per arm" from the ledger alone | stamp `scope` = `strategy-104:<arm>` (or add a column), fail loud instead of `-unscoped` fallback |
| A11 | `sizing_fidelity` KPI placeholders: `sizing_mode`, `size_floor_reason`, fractionability, direct `target_notional` not stamped (`pending_contract_fields_unavailable`); `inputs.serving_artifact_sha256: null` | active-path stamping contracts (already tracked in the KPI file); scorecard should treat these as `unavailable`, never proxy silently |

## 5. Recommended next steps (small, in order)

1. A2-A4 stamping fixes in one pipeline PR (each is a few lines; the ledger
   becomes truthful at zero behavior risk — verdict rows are write-only
   telemetry).
2. Run the §2.4 acceptance check on 2026-07-13; if the 07-10 cross-section is
   still 6 rows, fix the observer enumeration (A9) before anything else — it
   silently caps every future retro-verification.
3. Re-run this memo's script when fwd_5d matures for the post-enable window
   (07-17) and fwd_20d for the XGB era (early Aug); the §3 tables upgrade in
   place with zero new code.
4. Hold #145/#190 demean relitigations until fwd_60d (Sep); cite §3b as the
   interim directional record.
