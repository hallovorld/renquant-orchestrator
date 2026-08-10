# Stale config surface audit — the umbrella `strategy_config.json` vs the pinned running config

Audited: 2026-08-09 20:59 PDT (`date` read this session). Read-only research;
no config was modified. All file:line citations were read this session from:

- UMBRELLA copy: `/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.json`
  [VERIFIED — RenQuant HEAD f85a639; file mtime 2026-08-09 06:27, uncommitted `M` in git status]
- PINNED GOLDEN: `/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.golden.json`
  [VERIFIED — renquant-strategy-104 HEAD aa77593; file last commit e00d935 2026-08-06; configs/ clean]
- PINNED ACTIVE: `/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json`
  (the file the daily runner actually loads — see §1)

## 0. Bottom line

1. The daily decision run consumes the PINNED ACTIVE config
   (`renquant-strategy-104/configs/strategy_config.json`, `ranking.panel_scoring.kind
   = "blend"`), never the umbrella copy. The umbrella copy still says `kind =
   "hf_patchtst"` — a scorer retired on 2026-08-02 — plus 102 other divergent
   substantive keys.
2. The umbrella file is NOT a dead surface: the weekly per-ticker tournament
   retrain reads it as its config, and the retrain's recalibrate step writes
   two keys back into it (observed written TODAY). So it cannot be deleted or
   blanket-deprecated; it must be re-scoped.
3. The daily drift guard compares the umbrella file against the umbrella
   golden — two stale copies of each other — so this divergence is structurally
   invisible to it ("reports clean forever" is the in-repo phrasing).
4. Risk counts over the 103 substantive differing leaf keys (umbrella vs pinned
   golden): (a) actively misleading = 43, (b) inert-but-confusing = 56,
   (c) benign = 4. Single most misleading key: `ranking.panel_scoring.kind`.

## 1. Which file the daily runner actually consumes (evidence chain)

Launchd daily job → `daily_104.sh`:

- `daily_104.sh` resolves the pinned config before anything runs:
  `PROD_STRATEGY_CONFIG="$(renquant_strategy_config "$SUBREPO_ROOT" strategy_config.json)"`
  [VERIFIED — /Users/renhao/git/github/RenQuant/scripts/daily_104.sh:113]
- `renquant_strategy_config` returns `$root/renquant-strategy-104/configs/$config_name`
  [VERIFIED — /Users/renhao/git/github/RenQuant/scripts/subrepo_env.sh:54-63]
- If the pinned config cannot be resolved, the script FAILS CLOSED rather than
  fall back to the umbrella copy ("The umbrella copy is NOT an equivalent
  config (different primary panel_scoring.kind); substituting it would run a
  different strategy") — umbrella fallback exists only under an explicit
  `RQ_DAILY_RUNNER=umbrella`
  [VERIFIED — daily_104.sh:135-140; provenance comment for RenQuant#546 at daily_104.sh:114-134]
- Every run logs which config and which scorer kind it resolved
  [VERIFIED — daily_104.sh:146-147]
- The main run invokes the orchestrator bridge, not plain `live.runner`:
  `RUNNER_ARGS=(-m renquant_orchestrator daily-bridge --repo-dir "$REPO_DIR")`
  [VERIFIED — daily_104.sh:407-411; invocation with no config flag at :414-416]
- The bridge injects the pinned path into the runner argv:
  `runner_argv = _with_pinned_strategy_config(runner_argv, repo_root=repo_root)` inside `run_bridge`
  [VERIFIED — /Users/renhao/git/github/renquant-orchestrator/src/renquant_orchestrator/live_bridge.py:410; function at :373]
- `_with_pinned_strategy_config` builds
  `resolve_subrepo_root(repo_root) / "renquant-strategy-104" / "configs" / config_name`
  and appends `--strategy-config-path <that path>`; `config_name` defaults to
  `strategy_config.json` (`strategy_config.shadow.json` only for
  readonly-alpaca)
  [VERIFIED — live_bridge.py:93-113; name resolution at :74-82]
- `live/runner.py` then loads exactly that file:
  `config_file = Path(config_path).expanduser() if config_path else strategy_dir / config_name`,
  `config = json.loads(config_file.read_text())`
  [VERIFIED — /Users/renhao/git/github/RenQuant/live/runner.py:406,413; CLI arg wiring at :1373-1377,1386-1388,1408-1413]

Same for the intraday sell-only pass: `intraday_sell_104.sh` routes through
`-m renquant_orchestrator live-bridge`, which runs the same
`_with_pinned_strategy_config` injection
[VERIFIED — /Users/renhao/git/github/RenQuant/scripts/intraday_sell_104.sh:92-109; live_bridge.py:408-410 runs for both bridge modes].
Same for the weekly panel promote: `weekly_wf_promote.sh` resolves the pinned
config and fails closed
[VERIFIED — /Users/renhao/git/github/RenQuant/scripts/weekly_wf_promote.sh:79-87].

The only code in the live tree that reads the umbrella
`backtesting/renquant_104/strategy_config.json` on the decision path is
`_is_multi_stock` (live/runner.py:1316-1322) — which is DEAD CODE: defined but
never called anywhere in the live tree (call sites exist only in
`.claude/worktrees/` copies)
[VERIFIED — grep of `_is_multi_stock` across RenQuant this session: definition at live/runner.py:1316, zero live-tree call sites].

### 1.1 Golden vs active in the pinned repo

The runner loads the pinned ACTIVE file; the GOLDEN file is the drift
reference. They are in semantic lockstep: a full flattened diff this session
found 15 differing leaf keys, of which 14 are `_`-prefixed comment keys and 1
is `walkforward.manifest_path` (present in active, absent in golden)
[VERIFIED — flatten diff run this session over both pinned files]. Both have
`ranking.panel_scoring.kind = "blend"` with the identical two `components`
entries (panel-ltr xgb + momentum_residual ledger) [VERIFIED — same diff].
So "umbrella vs golden" below is equivalent to "umbrella vs running" except
for `walkforward.manifest_path`, which the umbrella and the ACTIVE agree on
(both carry it; golden lacks it) — that one row is a golden-only artifact,
not an umbrella staleness.

## 2. The umbrella file is still a LIVE surface (for a different job)

This is the load-bearing nuance for remediation:

- The weekly per-ticker tournament retrain reads the UMBRELLA config:
  `STRATEGY_CONFIG="$REPO_DIR/backtesting/renquant_104/strategy_config.json"`
  [VERIFIED — /Users/renhao/git/github/RenQuant/scripts/weekly_tournament_retrain.sh:97]
  invoking `train_104.py --skip-panel --force`
  [VERIFIED — weekly_tournament_retrain.sh:277],
  and `train_104.py` loads `REPO_ROOT / "backtesting" / <strategy> / strategy_config.json`
  [VERIFIED — /Users/renhao/git/github/RenQuant/scripts/train_104.py:194-201].
- The retrain's recalibrate step WRITES back into the umbrella file — it
  re-reads the file and merges exactly two keys it owns,
  `ranking.blend_updated` and `ranking.blend_n_symbols`
  [VERIFIED — /Users/renhao/git/github/RenQuant/scripts/recalibrate_scores.py:144-146 (path), :281-288 (write)].
  Observed: umbrella `blend_updated = "2026-08-09"` (today),
  `blend_n_symbols = 141`, file mtime 2026-08-09 06:27, uncommitted `M`
  [VERIFIED — file read + `git status` this session]. The 2026-07-20
  mirror-lag incident comment inside the umbrella file itself documents this
  consumer relationship [VERIFIED — umbrella strategy_config.json:180,
  `_parallel_ticker_timeout_umbrella_mirror_lag_20260720`].
- Consequence: for the key subset the tournament retrain consumes
  (`watchlist`, `parallel_ticker_timeout_seconds`, `training`, `acceptance`,
  `model_staleness_days`, `sharpe_floor`, ...), an umbrella≠pinned divergence
  is not merely a forensic hazard — it changes the retrain's actual behavior.
  Today that subset diverges on exactly one thing: the WATCHLIST — umbrella
  has 142 names, pinned golden has 145; missing from umbrella: CRWV, RKLB,
  SPCX (plus their `sector_map` rows)
  [VERIFIED — set diff run this session]. Those 3 names therefore never enter
  the weekly per-ticker tournament. (`parallel_ticker_timeout_seconds` = 2400
  in both since the 2026-07-20 fix [VERIFIED — umbrella :178, golden :187].)

Two more umbrella-surface readers, both non-decision:

- `scripts/production_runner.py` reads the UMBRELLA
  `strategy_config.golden.json` for its universe (default
  `--strategy-dir` = `REPO/backtesting/renquant_104`)
  [VERIFIED — production_runner.py:71-73 (get_universe), :237-238 (default)],
  but it is a legacy standalone tool whose `--execute` is hard-disabled with
  an error directing to `live.runner`
  [VERIFIED — production_runner.py:248-257]; it appears in neither
  daily_104.sh nor the orchestrator launchd manifest
  [VERIFIED — grep this session, zero hits].
- The daily drift guard `check_config_drift.py --strategy renquant_104`
  compares umbrella-active vs umbrella-golden — BOTH stale on panel_scoring —
  defaults `--baseline strategy_config.golden.json` / `--live
  strategy_config.json` under `REPO_ROOT/backtesting/<strategy>`
  [VERIFIED — check_config_drift.py:94-100; invoked at daily_104.sh:264].
  The umbrella golden also says `kind = "hf_patchtst"`
  [VERIFIED — json read this session of
  RenQuant/backtesting/renquant_104/strategy_config.golden.json]. daily_104.sh
  itself states the consequence: "the golden file carries the SAME inverted
  intent, so the drift guard below compares one stale copy against another
  and reports clean forever" [VERIFIED — daily_104.sh:127-129].

## 3. Full diff, umbrella vs pinned golden

Method: recursive flatten of both JSON documents to leaf keys (lists compared
as JSON blobs), run this session. Totals: 147 differing leaf keys — 44 are
`_`-prefixed comment/annotation keys (stale RATIONALE text; not
risk-classified below, see §4.4), 103 are substantive
[VERIFIED — diff output this session].

Top-level sections present only in the umbrella: `tournament_shadow`,
`walkforward`, `_parallel_ticker_timeout_umbrella_mirror_lag_20260720`.
Present only in golden: `bear_defensive_sleeve`, `decision_ledger`,
`deployment_governor`, `intraday_decisioning`, `live`,
`sdl_skip_if_trailing_armed`, `sizing`, `sleeve`, `wash_sale_min_material_npv`
(+2 comment keys) [VERIFIED — top-level key set diff this session].

For EVERY row below, the daily decision runner consumes the PINNED value (the
§1 chain injects the pinned active file; pinned active ≡ golden on every
non-comment key except `walkforward.manifest_path`, §1.1). The umbrella value
is consumed ONLY by the weekly tournament retrain (§2) and only for the keys
that job reads — among the rows below, that is `watchlist`/`sector_map` alone.

### 3.1 `ranking` section (the request's focus) — 24 substantive leaf diffs

| Key (under `ranking.`) | Umbrella value | Golden (= running) value | Risk |
|---|---|---|---|
| `panel_scoring.kind` | `"hf_patchtst"` | `"blend"` | (a) |
| `panel_scoring.artifact_path` | `../../artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt` | `artifacts/prod/panel-ltr.alpha158_fund.json` | (a) |
| `panel_scoring.components` | ABSENT | 2 entries: panel-ltr xgb (content sha256:6461b827ab2339a8) + `momentum_residual` ledger (fp momentum-v0-fd65161a20b29314) | (a) |
| `panel_scoring.shadow_models` | 1 entry: `xgb_alpha158_fund_previous_primary` (prod xgb as SHADOW) | 3 entries: `topdecile_clf_blend_leg`, `momentum_residual_v0_shadow`, `momentum_fast_v1_shadow` | (a) |
| `panel_scoring.shadow_experiment` | `renquant_104_xgb_shadow_after_patchtst_promotion` | `renquant_104_patchtst_shadow_after_xgb_promotion` | (a) |
| `panel_scoring.global_calibration.enabled` | `true` | `false` | (a) |
| `panel_scoring.global_calibration.artifact_path` | `artifacts/shadow/panel-rank-calibration.hf_patchtst_seed44_trainfit_20230103_20240409.json` | `artifacts/prod/panel-rank-calibration.json` | (a) |
| `panel_scoring.buy_floor` | `"adaptive_mean_std"` | `null` (z-blend NULLED 2026-08-04) | (a) |
| `panel_scoring.sizing.enabled` | `false` | `true` | (a) |
| `kelly_sizing.enabled` | `true` | `false` (z-blend DISABLED) | (a) |
| `kelly_sizing.fractional` | `0.5` | `0.3` | (a) |
| `kelly_sizing.max_concentration` | `0.12` | `0.3` | (a) |
| `kelly_sizing.sigma_horizon_days` | ABSENT | `60` | (a) |
| `panel_scoring.conviction_gate.{enabled,mu_floor,demean_cross_sectional}` | ABSENT (3 leaves) | `false / 0.03 / false` | (b) |
| `panel_scoring.fingerprint.accept_legacy_stamps` | ABSENT | `true` (== reader default, declared for the M6 migration) | (c) |
| `panel_scoring.ngboost.artifact_path` | `artifacts/shadow/ngboost-head.alpha158_fund.shadow.json` | `artifacts/prod/ngboost-head.alpha158_fund.json` (both `enabled:false`) | (b) |
| `panel_scoring.specialists` / `specialist_confidence_threshold` / `specialist_blend_top_k` | `{} / 0.8 / 2` (3 leaves, umbrella-only) | ABSENT | (b) |
| `panel_scoring.shadow_tracking_uri` | `file:./mlruns` | ABSENT | (b) |
| `blend_updated` | `"2026-08-09"` (FRESH — written today by recalibrate) | `"2026-05-06"` (stale side is the PINNED copy here) | (c) |
| `blend_n_symbols` | `141` (fresh) | `103` (stale) | (c) |

[VERIFIED — every value above from the flatten diff + direct reads this
session; umbrella `kind` at umbrella file :876, golden `kind` at golden file
:985; z-blend override notes at golden :926,:1020,:1089.]

Note the inversion on the last two rows: `blend_updated`/`blend_n_symbols`
are tournament-retrain bookkeeping that lives CORRECTLY in the umbrella file
(§2); the pinned copies of those two keys are the stale mirror. They are the
only umbrella-fresher keys in the whole diff.

### 3.2 Buy/sell gates and exits — 18 substantive leaf diffs

| Key | Umbrella | Golden (= running) | Risk |
|---|---|---|---|
| `model_sell.panel_veto.enabled` | `true` | `false` (z-blend DISABLED) | (a) |
| `wf_gate.diagnostic_only_buy_admission.*` (6 leaves) | ABSENT | `authorized:true`, operator renhao, authorized_at 2026-07-16, EXPIRES 2026-08-15, sha-bound scorer sha256:656b70be… | (a) |
| `risk.model_protection.{enabled,exit_mu_threshold,n_strikes}` | ABSENT | `true / 0.0 / 3` | (a) |
| `risk.sdl_anchor_policy.{mode,entry_regimes,current_regimes}` | ABSENT | `entry_regime / [BULL_CALM] / [BULL_VOLATILE,CHOPPY,BEAR]` | (a) |
| `sdl_skip_if_trailing_armed` | ABSENT | `true` | (a) |
| `risk.panel_exit.min_holding_days_by_regime.default` | ABSENT (only BULL_CALM:60) | `60` | (a) |
| `live.broker_side_stops.{enabled,pct}` | ABSENT | `true / 0.2` (broker-resident GTC catastrophe stops) | (a) |
| `wash_sale_min_material_npv` | ABSENT | `5.0` (operator decision 2026-08-03) | (a) |

### 3.3 Regime detection and sizing — 9 substantive leaf diffs

| Key | Umbrella | Golden (= running) | Risk |
|---|---|---|---|
| `regime_params.BULL_CALM.max_position_pct` | `0.12` | `0.3` | (a) |
| `regime_params.CHOPPY.max_hold_days` | `40` | `500` (2026-06-11 RFC; the MU force-sell fix) | (a) |
| `regime.bear_trend_filter.{enabled,ma_window}` | ABSENT | `true / 200` (false-BEAR fix) | (a) |
| `regime.bear_short_route_require_both` | ABSENT | `true` | (a) |
| `watchlist` | 142 names | 145 names (adds CRWV, RKLB, SPCX) — OPERATIVE for the weekly tournament retrain, §2 | (a) |
| `sector_map.{CRWV,RKLB,SPCX}` (3 leaves) | ABSENT | `datacenter_hw / industrial / industrial` | (a) |

### 3.4 Rotation / QP subtree — 13 substantive leaf diffs

`rotation.joint_actions.enabled = false` in BOTH files [VERIFIED — umbrella
:663, golden :761], so this subtree is off the daily order path in both; the
z-blend batch nulled the pinned values anyway ("mirrors active"). Flagged (b)
with one caveat: the 2026-08-04 operator batch judged these worth nulling, so
any consumer outside the QP solver (e.g. top-up admission helpers) should be
re-verified before relying on the (b) call.

| Key | Umbrella | Golden (= running) | Risk |
|---|---|---|---|
| `rotation.panel_buy_floor` / `panel_sell_floor` / `panel_buy_rank_floor` | `0.3 / 0.2 / 0.2` | `null / null / null` (z-blend NULLED; rotation itself IS enabled) | (a) |
| `rotation.joint_actions.qp_admission_gate.min_rank_score` / `topup_min_rank_score` | `0.55 / 0.55` | `null / null` | (b) |
| `rotation.joint_actions.qp_admission_gate.min_expected_return_by_regime` (2 leaves) | `{BULL_CALM: 0.01}` | `null` | (b) |
| `rotation.joint_actions.qp_soft_sell_guard.min_holding_days_by_regime.default` | ABSENT | `60` | (b) |
| `rotation.joint_actions.qp_live_shadow_telemetry.*` (4 leaves) | ABSENT | `enabled:true`, candidate `hybrid_option_f_allocator`, JSONL path | (b) |
| `rotation.joint_actions.allow_cap_compliance_sells_on_infeasible` | ABSENT | `true` | (b) |

The three `rotation.panel_*` floors are classed (a), not (b): `rotation.enabled
= true` in both files [VERIFIED — umbrella :650, golden :748], so a forensic
reader would apply GBDT-era floors (0.3/0.2) to z-composite scores on the LIVE
rotation path and mis-explain rotation admissions.

### 3.5 Dormant/shadow scaffolding present only in golden — 37 substantive leaf diffs

All are declared-inert or shadow-only blocks whose ABSENCE from the umbrella
misleads only about scaffolding, not orders. All (b):

- `sleeve.*` (10 leaves; `enabled:true, mode:"shadow"` — JSONL logging only) — a
  reader of the umbrella cannot explain `logs/parking_sleeve_shadow.jsonl`
- `intraday_decisioning.*` (7 leaves; `enabled:true, mode:"shadow"`, never-submit
  runtime-asserted)
- `deployment_governor.*` (10 leaves; `enabled:false`, placeholder numerics)
- `execution.fractional_shares.*` (4 leaves; `enabled:false`)
- `execution.software_stops.*` (3 leaves; `enabled:false`)
- `bear_defensive_sleeve.enabled` (`false`)
- `sizing.one_share_floor_enabled` (`false`)
- `decision_ledger.enabled` (`true` — hides an evidence SOURCE from a forensic
  reader, but implies no wrong trade conclusion)

### 3.6 Umbrella-only keys — 2 substantive leaf diffs

- `tournament_shadow.enabled = false` — tournament-side key on the file the
  tournament job actually reads; (c) benign.
- `walkforward.manifest_path` (absolute umbrella path) — present in umbrella
  AND pinned active, absent only from golden (§1.1); (b) as a golden-side
  bookkeeping gap, not an umbrella staleness.

## 4. Risk classification summary

Counting the 103 substantive differing leaf keys (umbrella vs pinned golden):

| Class | Count | Definition |
|---|---|---|
| (a) actively misleading | 43 | a forensic reader of the umbrella file draws a WRONG conclusion about live behavior (wrong primary scorer, wrong sizing caps, wrong exit/stop lines, missing buy-admission authorization, wrong universe) |
| (b) inert-but-confusing | 56 | divergent but behind a disabled/shadow flag on both sides, or hides scaffolding/evidence sources without implying a wrong trade conclusion |
| (c) benign | 4 | `fingerprint.accept_legacy_stamps` (== default), `blend_updated` + `blend_n_symbols` (umbrella is the FRESH side), `tournament_shadow.enabled` |

[VERIFIED — per-leaf classification enumerated in §3.1-3.6; counts re-added
this session: class (a) = 13 (§3.1) + 18 (§3.2) + 9 (§3.3) + 3 (§3.4 rotation
floors) = 43; class (b) = 8 (§3.1) + 10 (§3.4) + 37 (§3.5) + 1 (§3.6) = 56;
class (c) = 3 (§3.1) + 1 (§3.6) = 4; section totals 24+18+9+13+37+2 = 103.]

Plus 44 `_`-comment-key diffs excluded from the classes above: stale rationale
text. One of them is actively USEFUL and must survive any cleanup —
`_parallel_ticker_timeout_umbrella_mirror_lag_20260720` (umbrella :180), the
in-file record of the mirror-lag incident class.

### 4.1 Single most misleading stale key

`ranking.panel_scoring.kind = "hf_patchtst"` [VERIFIED — umbrella :876].
It names as PRIMARY a scorer that was retired on 2026-08-02 (orch#741; golden
carries the retirement note at :1023), whose served artifact was 625d stale,
and whose scores are intrinsically all-negative — the exact substitution that
RenQuant#546 measured would produce a silent sell-only book
[VERIFIED — daily_104.sh:119-125]. Every other ranking-section misread
(artifact_path, calibration, shadow roles, buy_floor) follows from accepting
this one key. It has already misled forensics at least once (the
"assumed tree is not the running tree" failure class).

## 5. Remediation options (PROPOSALS ONLY — nothing executed here)

Any change to the umbrella `strategy_config.json` is PRODUCTION-ADJACENT
(§2: it is a live input to the weekly tournament retrain and a live write
target of recalibrate) and requires its own reviewed PR in RenQuant with a
retrain-behavior-invariance argument. None of the options below is executed
in this PR.

**Option A — deprecation banner keys in the umbrella file (recommended, cheapest).**
Add a top-level `"_STALE_SURFACE_WARNING"` and a
`ranking.panel_scoring._STALE_SECTION_WARNING` stating: decision-path
authority is `renquant-strategy-104/configs/strategy_config.json`; this file
is authoritative ONLY for the weekly tournament retrain subset; do not read
`ranking.panel_scoring` here. Survivability: recalibrate's write-back
re-reads the file and merges only its two owned keys, so unknown keys survive
[VERIFIED — recalibrate_scores.py:281-288]. Risks: (i) the umbrella drift
guard will flag the new key vs umbrella-golden unless the same banner lands in
golden or an `--ignore-path` is added (supported —
check_config_drift.py:88-89); (ii) a banner does not FIX any wrong value, it
only warns; (iii) any strict-schema consumer would need a check (none known —
train_104 reads keys by name).

**Option B — surgical re-mirror of the retrain-consumed subset only.**
Bring `watchlist` + `sector_map` (the only operatively-divergent retrain keys,
§2) into lockstep with pinned, adding CRWV/RKLB/SPCX to the weekly tournament.
This is a REAL behavior change to the retrain (3 new tournament names) and
needs its own validation, but it closes the only divergence with live effect.
Explicitly NOT a full-file re-mirror: re-mirroring `ranking.panel_scoring`
would recreate a fresh-looking stale copy that starts drifting again the day
after, and the 2026-07-20 incident shows partial mirrors rot silently.

**Option C — delete the stale `ranking.panel_scoring` section from the umbrella file.**
Rejected as a first move: `train_104.py` runs WITHOUT `--skip-panel` on other
surfaces (`retrain_panel.sh`, `daily_retrain_alpha158_fund.sh`,
`conditional_retrain_104.sh` all invoke it [VERIFIED — grep this session]),
and those paths read panel/ranking config from the same umbrella file. A
deletion requires a full consumer inventory of every `train_104.py` caller
first; without it this option risks breaking the panel retrain, not just a
forensic surface.

**Option D — doc pointer only (no config change).**
A `doc/ops` note + memory entry naming the authority chain. Zero production
risk, no review burden on RenQuant, but historically insufficient: readers go
to the file, not the doc (the 2026-07-20 mirror-lag incident and the forensics
misdirection that motivated this audit both happened with the operating-model
doc already in place).

**Option E — re-target the drift guard at the real authority.**
Change/extend `check_config_drift.py` (or a new orchestrator-side scan) to
compare the umbrella file against the PINNED config on the retrain-consumed
key subset, alerting on divergence there, and to treat `ranking.panel_scoring`
as expected-divergent (or assert it carries the Option-A banner). This fixes
the structural blindness ("stale copy vs stale copy", §2) so the class cannot
recur silently. Requires a RenQuant code PR + tests.

Recommended sequence: A (banner, umbrella + umbrella-golden in one PR) →
E (guard re-target) → B (watchlist re-mirror, separately validated). C only
after a train_104 caller inventory; D as the fallback if no RenQuant PR
bandwidth exists.

## 6. What this PR does NOT do

- No file outside `renquant-orchestrator/doc/` is touched.
- No umbrella or pinned config is modified.
- No claim is made about WHY the umbrella file was left stale (the git log
  shows deliberate "umbrella mirror" commits ending with ebd79fd, the
  2026-07-20 timeout mirror [VERIFIED — git log this session]); the
  divergence documented here is the accumulation since the pinned repo became
  the authority.
