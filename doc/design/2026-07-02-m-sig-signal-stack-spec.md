# M-SIG: the G106 signal-stack spec — candidates, estimands, frozen thresholds, kill conditions

STATUS: design / pre-registration scaffold for review (docs only). This is the MID-term IC
core of the unified plan (#231 §1 Term IC) — the explicit build+measure task G106 gates on.
DATE: 2026-07-02 (r1); r2 2026-07-02 (Codex review: r1 was a candidate roadmap with
substantial researcher degrees of freedom left open in every candidate — not yet a frozen
spec. This revision closes every open parameter per candidate, adds multiplicity control,
separates prior-inspected from genuinely prospective evidence, and replaces the narrative
"wait for strongest leg" sequencing rule with a deterministic, date-bounded stack decision
procedure.); r3 2026-07-02 (Codex review: r2's "fixed hierarchical order" did NOT control
family-wise error — every candidate still ran at the full nominal α=0.05, and the 2-of-3
early-GO rule adds an implicit additional look. r2 also left C2's PIT field and C3's
benchmark/sector sources deferred to "confirm in the build PR," and C4's margin was
justified only as "below a known floor" without an actual noise argument. r3 fixes all
four: a real Bonferroni correction (k=3, one-sided α=0.05/3 per candidate — see §2a),
frozen production source citations for C2/C3 in place of deferred confirmation, an honest
arbitrary-margin-with-sensitivity label for C4 in place of the floor-based hand-wave, and a
bounded (not indefinite) horizon for C1's background accrual.); r4 2026-07-02 (Codex review:
r3's C2 admissible-mapping rule fell back to the bare fundamentals-PERIOD date as a "same-day
conservative floor" when no filing timestamp existed — that is LOOKAHEAD BIAS, not a floor
(the period date precedes actual publication by weeks to months). r4 removes the period-date
fallback entirely: an observation with no genuine `acceptedDate`/`filingDate` is INADMISSIBLE,
not proxy-dated. Investigated this repo's actual FMP fundamentals fetcher and found it
carries no filing-timestamp field at all (fetch-date indexed only) — the expected case is
that C2 falls back to a `sec_fundamentals.py`-sourced SEC EDGAR `available_date` join (a
genuine PIT timestamp already implemented and pinned in this repo, with a realistic ~45-day
filing-lag fallback, never zero-lag) before being marked inadmissible.)

**Freeze status (honest, per-candidate — see §1 for detail): C2, C3, C4 are FROZEN — every
parameter below is fixed and may not be tuned after seeing a result, and their formal GO/KILL
decision rule now uses a Bonferroni-corrected one-sided 98.33% CI (not the naive 95%) to
control the 3-candidate family-wise error rate — see §2a. C1 is FROZEN on
methodology/procedure but its go/kill bar's STATISTICAL POWER is honestly unresolved until
real accrued data exists to check it against (§1.1); C1 may not be used as a standalone
go/kill gate until that check passes, is EXCLUDED from the Bonferroni family (it never
independently votes — §1.1, §3), and its background accrual is now bounded to 2027-Q4, not
indefinite — see the explicit downgrade rule in §1.1.**

## 0. The gate this feeds (fixed, from the merged route)

**G106 (2027-Q4): ≥2 orthogonal signals, each placebo-clean IC ≥ 0.015 individually,
combined ≥ 0.02, measured cross-family ρ committed, TC ≥ 0.6.** Stacking math planning range
0.028–0.033 at the measured intra-family ρ = 0.217 (POC-D). Kill branch if nothing clears:
benchmark-sleeve default + PIT accrual continues + 107 re-scoped execution-only.

## 1. The candidates — full frozen specification

Shared conventions across all four candidates (defined once, referenced below):

- **Substrate**: S5/S8 durable pick-table + ledger only, never an ad-hoc `/tmp` panel (the
  A1 lesson — see `renquant-orchestrator#240`'s harness-bug postmortem for why this matters:
  an unwired substrate silently disables the thing being tested).
- **CI methodology (default, unless a candidate states otherwise)**: moving-block bootstrap
  on the per-decision-date IC series, `block = 60` (the fwd_60d label horizon in sessions —
  matches this repo's established convention in
  `scripts/research_panel_exit_predictiveness.py::_moving_block_bootstrap`, chosen because
  adjacent decision dates share overlapping forward-return windows and are NOT
  independent), `n_boot = 2000`, seed drawn from the fixed set `{42, 43, 44}` (this repo's
  established seed-robustness convention — see `doc/research/2026-06-23-trendscan-label-
  evidence.md` — all three seeds must be run and reported; do not cherry-pick one).
- **Minimum effective sample size (default)**: at least `10 * block = 600` decision-date
  observations (≈2.4 years at daily cadence) — below this the bootstrap in
  `_moving_block_bootstrap` itself refuses to produce a CI (`n <= block` returns
  `(None, None, None)`), and even above that floor a bootstrap with too few independent
  blocks understates true uncertainty. **600 decision dates ÷ block=60 is only 10 EFFECTIVE
  BLOCKS at the floor** — the same thin-sample regime that made #235's/#431's 10-day
  cohorts unreliable for CI width; 600 is a floor for the bootstrap to run at all, not
  evidence the resulting CI is narrow. Report the actual `n`, block count, AND (per
  candidate, §1) a detectable-effect/power read at that block count — a floor being met is
  not the same as the test being adequately powered (see the per-candidate power notes
  added in r3 below; C2/C3/C4 do not yet have real σ estimates to compute this rigorously,
  same limitation as C1's illustrative-only calc in §1.1 — report it as illustrative, not
  authoritative, until real data exists).
- **Deterministic decision rule (default, r3: Bonferroni-corrected)**: GO iff the
  block-bootstrap CI lower bound, at the level in §2a (98.33% one-sided for C2/C3/C4 — NOT
  the naive 95%), exceeds the candidate's frozen individual threshold; KILL iff the
  same-level CI upper bound is below the threshold; else INCONCLUSIVE (this mirrors the
  frozen equivalence-style rule already applied to `#235`/`#431` this session — a point
  estimate above the bar is never sufficient on its own). C1 is explicitly EXEMPT from this
  corrected level (§1.1: it never independently votes, so it is not part of the 3-candidate
  Bonferroni family — see §2a).
- **Prospective-vs-retrospective evidence**: per candidate below, every number that was
  already computed/inspected BEFORE this freeze date (2026-07-02) is explicitly labeled
  EXPLORATORY/RETROSPECTIVE and may motivate why a candidate is worth testing, but may
  NEVER itself be reported as, or substitute for, that candidate's confirmatory result. Only
  a genuinely new measurement — run for the first time after this freeze, on data/cells not
  previously inspected — counts toward a GO/KILL/INCONCLUSIVE verdict.

### 1.1 C1 — Estimate-revision drift

- **Estimand**: cross-sectional rank of trailing 1-month Δ(consensus FY1 EPS estimate),
  PIT `available_at`-lagged.
- **Feature formula (frozen)**: for name `i` at decision date `t`,
  `revision_drift_1m(i,t) = (FY1_consensus(i,t) − FY1_consensus(i, t−21td)) / |FY1_consensus(i, t−21td)|`,
  where `t−21td` is 21 trading days prior (≈1 calendar month) and `FY1_consensus(i,τ)` is the
  most recent FY1 EPS consensus estimate with `available_at ≤ τ`. **1m is the PRIMARY window
  — the 3m variant is dropped from the frozen gate entirely** (it may still be computed as a
  secondary diagnostic in the eventual build PR, but the 3m read never gates GO/KILL; running
  both and picking whichever clears is exactly the researcher-degrees-of-freedom problem this
  revision closes).
- **FY1/FY2 combination**: FY1 only for the frozen gate. FY2 is explicitly OUT of scope for
  C1's go/kill threshold (a separate, future candidate if FY1 clears and a next leg is
  wanted) — no blending, no "whichever looks better" selection.
- **Update handling**: `FY1_consensus(i,τ)` uses the LATEST available snapshot as of `τ`; a
  name with no revision at all in `[t−21td, t]` (no analyst update in the window) is
  EXCLUDED from that date's cross-section (see missingness below) rather than treated as
  zero drift — a flat consensus is a different economic state than "no data."
- **As-of lag**: 1 trading day after `available_at` (matches N2's own PIT publication
  contract — see `renquant-orchestrator#233`'s liveness-check manifest fields).
- **Universe & missingness**: the current production S5/S8 pick-table universe, no
  additional filtering. A name is excluded from date `t`'s cross-section if it has no
  qualifying FY1 estimate observation in the trailing window (see above); it is NOT imputed.
  Report the excluded fraction per date as a diagnostic (a persistently high exclusion rate
  is itself informative about N2's coverage, separate from the IC result).
- **Forward-return horizon**: fwd_60d (matches this repo's standing convention, e.g. C4's
  raw-label comparator).
- **IC estimator & aggregation**: daily Spearman rank IC between `revision_drift_1m` and
  realized fwd_60d return, aggregated as the mean across decision dates within the accrual
  window.
- **TC/turnover relevance**: revision-drift scores are expected to be low-turnover (updates
  ≈monthly per name, not daily) — this must be checked empirically once real data exists
  (report realized turnover in the eventual build PR); no threshold is frozen for this axis
  since it's diagnostic, not a gate.
- **Accrual cutoff (frozen)**: the first candidate test uses data accrued through exactly
  6 calendar months from N2's actual first live snapshot date (`renquant-orchestrator#233`,
  merged 2026-07-02 — record N2's actual first successful scheduled snapshot date, not the
  merge date, as the accrual-window anchor in the eventual build PR, since installation/
  activation may lag merge). A second checkpoint exists at 9 months from the same anchor
  (see the power rule below).
- **Minimum effective sample size / power (frozen procedure, NOT a precomputed number)**:
  codex's concern is exactly right — 6-9 months of MONTHLY-cadence observations (the natural
  independence unit here, since the underlying estimate-revision data itself only refreshes
  ≈monthly per name) is 6-9 data points, and the default `block=60`/`n≥600` convention above
  does not apply to C1 (there is no multi-year daily history to block-bootstrap; N2 only
  started accruing this session). **Illustrative-only, NOT authoritative**: at a plausible
  literature-informed per-month IC std of ~0.10 (no real measurement exists yet for this
  specific signal), a one-sided test with α=0.05, power=0.80, detecting 0.015 vs 0 would
  need `n ≈ ((1.645+0.84)·0.10/0.015)² ≈ 274` months — i.e., monthly cadence cannot reach
  power at any accrual horizon anyone would wait for. This is illustrative of the scale of
  the problem, not a number to act on directly (the real σ is unknown until data exists).
  **Frozen resolution — codex's third option, applied, r3 adds an explicit horizon bound**:
  C1 is DOWNGRADED to INFORMATIVE-ONLY at both the 6mo and 9mo checkpoints. It may NEVER
  independently decide GO or KILL for the stack, and it is EXCLUDED from the §2a Bonferroni
  family (a candidate that structurally can never vote should not consume shared alpha
  budget). At each checkpoint, compute the empirical monthly-IC std from the actually-accrued
  data and the resulting CI width using the SAME moving-block-bootstrap machinery (block=1
  month here, since that's the true independence unit) applied to however many monthly
  points exist; report it, but do not gate on it. **r3 correction**: r2 said "accrual
  continues indefinitely" as a background task past 9mo if directionally encouraging — codex
  correctly flagged this as conflicting with the stack's own date-bounded design. Fixed:
  C1's monitoring under THIS design doc's scope is bounded to the SAME 2027-Q4 deadline as
  every other candidate (§3). C1 is re-read at each 6-month mark through 2027-Q4 using the
  informative-only procedure above; if it has not reached a genuinely powered read by
  2027-Q4, monitoring under this document STOPS at that date — it does not roll forward
  indefinitely as part of the G106 stack's scope. (The underlying PIT data collection itself
  — N2's raw accrual — may continue as separately-scoped, ordinary data infrastructure
  outside this design doc's purview; what stops at 2027-Q4 is C1's status as a monitored
  G106 candidate, not N2's data pipeline.) **G106's stack vote (§3) is computed over
  C2/C3/C4 only, at the k=3 Bonferroni correction from §2a. In the unlikely event C1
  reaches a genuinely powered read before 2027-Q4, this document does not attempt to
  pre-specify how it would join the vote — that would require re-deriving a k=4 correction
  and re-examining whether C2/C3/C4's already-resolved verdicts (evaluated at k=3) remain
  valid once a 4th test enters the family, which is a real methodological question this
  edge case cannot be pre-answered without knowing which candidates have resolved by then.
  If this scenario actually arises, it requires its own follow-up design note before C1's
  read is used, rather than a rule frozen now under uncertainty about which candidates would
  even still be live. The 2027-Q4 gate date never waits on C1 either way — this is only
  about how C1 could, in principle, join a k=3 decision that has already been made.**
- **Prior evidence**: literature-cited standalone monthly IC 0.02–0.03 post-decay
  (McLean–Pontiff-style post-publication decay already discounted in the citation) — this is
  EXTERNAL literature, not this repo's own prior-inspected data; OUR data is genuinely
  prospective (none existed before N2).

### 1.2 C2 — Quality composite (FMP-full)

- **Estimand**: cross-sectional rank of a quality composite over {gross-profit/assets,
  total accruals, net share issuance}, quarterly-refreshed, `acceptedDate`-lagged.
- **Composite construction (frozen)**: `composite(i,t) = mean(zscore(GP/A(i,t)), −zscore(accruals(i,t)),
  −zscore(net_issuance(i,t)))`, where each `zscore` is computed cross-sectionally within the
  universe at date `t` (so each of the three legs contributes equally by construction — no
  discretionary weighting), and the two negatively-oriented legs (higher accruals/issuance
  is worse quality) are sign-flipped before averaging. This is an EQUAL-WEIGHT composite,
  frozen — no PCA, no IC-weighted blend, no "whichever weighting wins" search.
- **"Beats the thin-panel NULL by a stated margin" (frozen)**: the `fundamentals_scan`
  measured NULL on the free-tier panel is the baseline to beat; re-test is justified ONLY if
  the FMP-full/N3 coverage report shows ≥20% panel-coverage improvement over that baseline
  (unchanged from r1 — this was already a frozen number, just re-stated here for
  completeness). The composite's OWN individual threshold, once re-tested, is the same
  ≥0.015 placebo-clean bar as every other candidate (§0) — there is no separate,
  weaker bar for C2.
- **As-of lag (frozen, fail-closed admissible-mapping rule — r3, resolves r2's deferral)**:
  1 trading day after the fundamentals record's PIT-acceptance timestamp. The exact field
  name on the N3-upgraded FMP Starter-tier schema is NOT yet verified in this session (grep
  of this repo's current FMP/base-data source found no confirmed field name to cite here
  honestly rather than guess one). r3 froze an admissible-mapping rule that fell back from
  `acceptedDate`/`filingDate` to the bare fundamentals-PERIOD date ("date") as a "same-day
  conservative floor" when neither timestamp field was present. **That fallback is WRONG and
  is removed in this round (r4, codex-caught):** a fundamentals period date describes what
  time period the data COVERS (e.g. "this is Q2 2026 data"), not when it became knowable —
  it virtually always PRECEDES actual publication/filing by weeks to months. Using it as an
  availability timestamp is LOOKAHEAD BIAS (the backtest sees the number before a real
  trader could have), which can manufacture IC rather than measure it. There is no safe
  same-day floor for this; the fallback is deleted outright, not replaced with a different
  single field.
  **Corrected admissible-mapping rule (r4, frozen):** the availability timestamp MUST come
  from a genuinely PIT-verified publication/acceptance field. (1) `acceptedDate` (SEC EDGAR
  acceptance timestamp) if present in the N3 payload; (2) `filingDate` if present and
  `acceptedDate` is not. If NEITHER is present for a given ticker-period observation, that
  observation is **INADMISSIBLE** — excluded from C2's cross-section at that date entirely,
  not backfilled with any proxy. This priority order is fixed now, before N3 data exists,
  with no discretion at build time; record which field matched (or "INADMISSIBLE — neither
  present") per observation in the build PR's evidence.
  **Source-level investigation (r4, this round):** grepped this session's actual checked-out
  `renquant-base-data` for whether FMP's fundamentals path exposes any PIT filing timestamp.
  Finding: `src/renquant_base_data/fetchers/fundamentals.py` and
  `src/renquant_base_data/loaders/fundamentals.py` (the FMP-backed fundamentals fetch/load
  path) index data by FETCH date only — no `acceptedDate`/`filingDate`/period-date field
  appears anywhere in either module. As currently implemented in this repo, **FMP's
  fundamentals path cannot supply the `acceptedDate`/`filingDate` fields this admissible
  mapping rule requires** — meaning C2 would be inadmissible on essentially 100% of
  observations if run against the current FMP fetcher, unless the N3 upgrade's actual API
  response payload turns out to carry these fields even though the current fetcher code
  doesn't surface them (this is genuinely unverified — N3 data doesn't exist in this
  session).
  However, this repo ALREADY has a working, PIT-correct alternative:
  `src/renquant_base_data/sec_fundamentals.py::build_quarterly_panel` derives an
  `available_date` field directly from real SEC EDGAR XBRL `filed` timestamps per concept
  (`row["available_date"] = max(selected_filed) if selected_filed else end_date +
  pd.Timedelta(days=45)` — i.e. it uses the genuine filing date when known, and even its own
  fallback is a REALISTIC ~45-day filing-lag estimate added to the period end, never the
  bare period date with zero lag). This is the kind of "externally verified filing timestamp
  join" codex's review asks for. **C2's admissible-mapping rule is therefore amended: at
  build time, if the N3/FMP payload does not carry `acceptedDate`/`filingDate` for a given
  observation (the expected case per the grep above), fall back to sourcing that
  observation's availability timestamp from `sec_fundamentals.py`'s `available_date` via a
  ticker+period-end join, BEFORE declaring the observation inadmissible.** Only if NEITHER
  the FMP payload nor a SEC EDGAR join can supply a genuine filing-adjacent timestamp is the
  observation inadmissible. Whether the SEC EDGAR XBRL concept tags actually cover C2's three
  required fields (gross-profit/assets, total accruals, net share issuance) is itself
  unverified in this pass — confirm the exact XBRL concept-tag mapping in the build PR; if
  coverage is incomplete, C2 runs on whichever fraction of the universe/period grid has a
  genuine timestamp from either source, with the coverage gap reported explicitly rather than
  silently reducing effective sample size.
- **Universe & missingness**: current production universe; a name missing ANY of the three
  legs at date `t` is excluded from that date's cross-section entirely (no partial-composite
  fallback — a composite with 2 of 3 legs is a different, uncontrolled instrument).
- **Forward-return horizon**: fwd_60d.
- **IC estimator & aggregation**: daily Spearman rank IC vs fwd_60d, block-bootstrap CI per
  the shared default (block=60, n≥600 decision dates, seeds {42,43,44}) — unlike C1, this
  candidate CAN be tested over the FULL historical panel depth once the N3-upgraded FMP data
  is backfilled (the quarterly refresh cadence of the underlying fundamentals does not
  limit the daily cross-sectional IC test the way N2's real-time-only accrual limits C1),
  so the shared default sample-size convention applies here, not C1's informative-only
  downgrade.
- **TC/turnover relevance**: quarterly-refresh features are expected low-turnover; report
  realized turnover as a diagnostic, not a gate.
- **Earliest test**: 2026-Q4, strictly after the N3 coverage verdict (unchanged from r1).
- **Prior evidence — EXPLORATORY/RETROSPECTIVE**: `fundamentals_scan` (measured, thin
  free-tier panel): quality composite reads NULL. This number is retrospective and may ONLY
  be used to justify why a coverage-delta re-test is worth running — it is explicitly NOT
  C2's result and does not count toward this candidate's own GO/KILL/INCONCLUSIVE verdict.

### 1.3 C3 — Regime-conditioned residual momentum

- **Estimand**: `mom_12_1` (12-month minus 1-month price momentum), orthogonalized
  (residualized) to sector and market beta, evaluated ONLY within `BULL_CALM`/
  `BULL_VOLATILE` regime-labeled dates.
- **Residualization fit window (frozen)**: rolling 252-trading-day (1-year) lookback,
  refit at each decision date using only data available as of that date (no lookahead) —
  `residual_mom(i,t) = mom_12_1(i,t) − β̂_sector(i,t)·sector_factor(t) − β̂_mkt(i,t)·mkt_factor(t)`,
  with `β̂` estimated by OLS over the trailing 252-day window.
- **Beta/sector definitions (frozen NOW, r3 — resolves r2's "confirm in the build PR"
  deferral)**: market beta = OLS slope of the name's daily return against the strategy
  config's `benchmark` key (`config.get("benchmark", "SPY")` — confirmed live in this
  repo's own preflight gate,
  `RenQuant/backtesting/renquant_104/kernel/preflight.py:1010`; production default is SPY,
  the actual pinned value comes from the run's `strategy_config.json`, not a value chosen
  after seeing C3's results). Sector = the strategy config's `sector_map` key, the SAME map
  already consumed uniformly across this repo's production panel/sim/lean adapters and
  config-consistency/preflight checks (confirmed live at
  `RenQuant/backtesting/renquant_104/adapters/panel_runtime.py:54`,
  `adapters/sim.py:1306`, `adapters/lean.py:909`,
  `kernel/decision_trace.py:132,166`, `kernel/config_consistency.py:72-73`,
  `kernel/preflight.py:1009` — one canonical config-sourced map, not independently defined
  per adapter). No new benchmark or sector definition is introduced; both are the existing
  production values already pinned in whatever `strategy_config.json` the eventual build PR
  runs against.
- **Regime pooling (frozen)**: `BULL_CALM` and `BULL_VOLATILE` dates are POOLED into one
  combined test population for the frozen gate (not tested separately with an
  either/or pass) — this matches how the candidate is framed in §0 (a single individual
  threshold, not per-regime sub-thresholds). A per-regime breakdown must still be REPORTED
  as a diagnostic (design rule 2, §2), but only the pooled BULL_CALM+BULL_VOLATILE reading
  decides GO/KILL/INCONCLUSIVE.
- **Forward-return horizon**: fwd_60d.
- **IC estimator, CI, sample size**: shared default (daily Spearman rank IC vs fwd_60d,
  moving-block bootstrap block=60, n≥600 in-regime decision dates, seeds {42,43,44}) — this
  answers r1's open review question #2 (the "A1 convention, block=13?" question is
  resolved: block=60 matching the fwd_60d horizon, per the shared default above, not 13;
  13 was never actually adopted anywhere in this codebase as a block-size convention — a
  check of `research_panel_exit_predictiveness.py`, the only extant block-bootstrap
  implementation in this repo, confirms block is always set to the label horizon).
- **The frozen comparison (restated precisely; r3: both legs use the §2a Bonferroni-corrected
  98.33% level, not the naive 95%)**: GO requires BOTH (a) the conditioned (residual×regime)
  cell's own 98.33% CI lower bound > 0.015, AND (b) the conditioned-minus-unconditioned
  point-estimate difference has a block-bootstrap 98.33% CI that excludes zero on the
  positive side (computed via the paired daily difference series, block-bootstrapped the
  same way — not two separate CIs compared by eye). Both legs are part of C3's ONE frozen
  decision rule, not two separate looks — the correction is spent once per candidate (§2a),
  not once per leg within a candidate.
- **Earliest test**: 2026-Q3 (data exists now).
- **Prior evidence — EXPLORATORY/RETROSPECTIVE, with an explicit prospectivity check
  required**: `regimemom` (measured): the UNCONDITIONAL trend-gate fails (2021 sign-flip
  inside an UP-trend) — this prior result is retrospective and motivates WHY the
  conditioned cell is worth testing (it identifies the untested combination), but is not
  itself C3's result. **The specific residual×regime combination defined above has NOT been
  computed or inspected as of this freeze date (2026-07-02) — the build PR must include an
  explicit affirmative statement (e.g. "no prior script in this repo's git history computed
  this exact residual×regime×block-bootstrap combination before 2026-07-02") before its
  result may be treated as genuinely prospective/confirmatory.** If that affirmation cannot
  be made honestly, the result must be labeled retrospective/exploratory instead, same as
  C4 below.

### 1.4 C4 — Trend-scanning label (model-side lever)

- **Estimand**: retrain target = signed t-stat of the strongest forward trend window
  (López de Prado trend-scanning label), compared against the raw fwd_60d label, on the
  PROPER (repaired) WF gate.
- **Substrate**: alpha158 multi-horizon panel (exists) + the repaired WF gate (S1–S3;
  S1/S2 merged, S3 pending as of this freeze).
- **Placebo-difference margin (frozen NOW, not deferred; r3 corrects r2's justification)**:
  **0.02**. r2 justified this as "half the measured ~+0.04 embargo-leakage floor," which
  codex correctly rejected: being below a known noise floor is not automatically
  "comfortably distinguishable" from that floor without an actual variance/paired-difference
  argument — this session has no verified paired placebo-difference noise distribution
  (standard error / CI width of the difference itself, as opposed to the floor's point
  estimate) available to derive the margin rigorously from data. **r3 is honest about this:
  the 0.02 margin is ARBITRARY, not derived from a paired-noise argument** — it is a
  round number below the ~0.04 floor, chosen for legibility, not statistically justified as
  "comfortably distinguishable." The frozen GATE stays 0.02 (do not move it after seeing
  results — that discretion is exactly what freezing exists to prevent), but the build PR
  MUST additionally report a sensitivity check: the same block-bootstrap CI evaluated
  against neighboring candidate margins {0.015, 0.02, 0.025} (bracketing the frozen value),
  to show whether the GO/KILL/INCONCLUSIVE conclusion is robust to small perturbations in
  this admittedly-arbitrary choice or flips on them. If the conclusion flips within that
  bracket, the result must be reported as margin-sensitive/fragile alongside the frozen-gate
  verdict, not just the frozen-gate verdict alone. r1 left this "to be fixed in the S3
  gate-repair PR" — that deferral is exactly the "claims frozen, isn't" contradiction codex
  flagged. S3's job remains to confirm the repaired gate computes placebo-difference
  correctly, not to choose or adjust this number.
- **Deterministic rule (r3: Bonferroni-corrected 98.33% level, per §2a)**: GO iff
  placebo-difference (trend-scan minus raw, on the S3-repaired gate) block-bootstrap 98.33%
  CI lower bound > 0.02, evaluated on production WF; sim
  non-inferiority (trend-scan does not materially underperform raw on the simulation-side
  metrics the repaired gate reports) is a required secondary condition, not a separate
  threshold — define "non-inferiority" as: sim Sharpe does not fall by more than 0.1 versus
  the raw-label sim Sharpe over the same window (a concrete number, replacing the
  undefined "non-inferiority" reference in r1).
- **CI, sample size**: shared default (block-bootstrap, block=60, n≥600, seeds {42,43,44}).
- **Earliest test**: 2026-Q3, strictly after S3 lands.
- **Prior evidence — EXPLORATORY/RETROSPECTIVE (explicit, unlike r1's framing)**: `#176`
  (measured): BULL_CALM placebo-clean beats raw in 3/3 seeds, mean +0.0149 — **this number
  is retrospective.** It was computed and inspected before this freeze, using the
  PRE-repair WF gate (absolute ICs explicitly untrustworthy per the embargo floor, per
  `#176`'s own text). It justifies promoting C4 to a proper-gate test; it is NOT a valid
  substitute for, or an early read of, the S3-gate confirmatory result. The eventual C4
  build PR's result must come from a genuinely fresh run on the repaired gate — it may not
  simply re-cite +0.0149 as if it were the frozen-gate outcome.

## 2. Design rules (bind all candidates, unchanged from r1)

1. **Measurement substrate**: every candidate is evaluated on the S5/S8 substrate (durable
   pick-table + ledger), never on ad-hoc /tmp panels — the A1 lesson.
2. **Placebo-clean differences only** (never absolute IC — the ~+0.04 embargo floor).
   Per-regime cuts mandatory; BULL_CALM is the binding cell (79% of live time).
3. **No settled-NULL re-litigation**: raw momentum, fundmom, label neutralization,
   multi-horizon sleeves stay closed. C2 re-runs ONLY under its coverage-delta hypothesis;
   C3 tests ONLY the untested residual×regime cell.
4. **Orthogonality is measured, not assumed**: pairwise score ρ committed per candidate pair
   as each lands (extends POC-D beyond the price family); the combined-IC projection uses
   measured ρ.
5. **One candidate PR at a time**, each with its own frozen threshold cited from THIS table;
   a candidate that misses its bar is recorded (evidence doc) and dropped — the stack's
   value is the survivors, not the roster.

## 2a. Multiplicity control (r2 attempt corrected in r3 — a fixed order alone does NOT
control FWER)

The candidate space has real multiplicity: 4 candidates, C3's residual×regime combination,
seed-robustness across `{42,43,44}` per candidate, and C1's window/FY choice (now closed to
a single 1m/FY1 path — see §1.1). Without control, the chance that at least one
candidate/cut spuriously clears its bar is materially higher than the nominal
per-candidate α=0.05.

**r2's claim was wrong and is retracted.** r2 asserted a fixed testing ORDER alone bounds
the number of independent "looks." Codex correctly identified the flaw: a fixed order does
not control family-wise error when every candidate is STILL RUN regardless of prior
outcomes, each retains the FULL nominal α=0.05, and the §3 "2 of 3 reach GO" early-stack-GO
rule adds a genuine additional combinatorial look (which PAIR of 3 candidates clears is
itself a choice made after seeing results, unless corrected for).

**Frozen rule (r3): Bonferroni correction across the k=3 formally-voting candidates
{C2, C3, C4}.** C1 is excluded from this family — it never independently votes (§1.1, §3),
so including it in the correction would (as r2 correctly worried) needlessly shrink C2/C3/C4's
already-thin budgets to compensate for a candidate that structurally cannot cast a vote.
Bonferroni, not a step-down procedure (Holm) or formal gatekeeping, is used deliberately:
Holm's step-down ordering requires knowing all k p-values SIMULTANEOUSLY to rank them, but
C2/C3/C4 resolve SEQUENTIALLY over calendar time (C3 in 2026-Q3, C4 in 2026-Q3, C2 in
2026-Q4) — there is no well-defined "smallest p-value first" order to step down through
without waiting for the last candidate to resolve, which would delay every decision to the
slowest candidate. A true fixed-sequence gatekeeping procedure (stop testing entirely on the
first non-significant result) does not fit this stack's actual goal either — the goal is
"find ANY 2 of 3 that clear," and stopping at the first miss could kill the stack even if the
other two would have cleared. Bonferroni is the correction that remains VALID regardless of
resolution order and is compatible with "test all 3 independently, count the survivors":

- Each of {C2, C3, C4} uses a per-candidate one-sided α = 0.05 / 3 ≈ **0.01667**, i.e. a
  one-sided **98.33%** CI (z ≈ 2.128, replacing the naive one-sided 95%/z≈1.645 everywhere
  in §1's per-candidate GO/KILL rules — this is now the actual value used in §0's shared
  "Deterministic decision rule").
- This is CONSERVATIVE (Bonferroni is known to be looser than necessary when tests are
  positively correlated, which C2/C3/C4 likely are to some degree via shared market
  exposure) but VALID under any correlation structure, unlike a naive uncorrected 0.05 — the
  conservatism is the honest cost of controlling FWER without step-down machinery this
  stack's sequential-resolution structure cannot support.
- **Consequence, stated plainly**: this makes each individual candidate's own bar harder to
  clear than r1/r2's spec implied. A candidate that would have read GO at the naive 95%
  level may now read INCONCLUSIVE at the corrected 98.33% level. This is the actual price of
  a genuinely FWER-controlled 3-candidate family; it is not a cosmetic wording change.
- **Early GO inherits the same correction, no separate combinatorial adjustment needed.**
  Because each individual candidate's own GO verdict already required clearing the
  Bonferroni-corrected bar (not the naive one), a §3 early-GO on any 2 of the 3 candidates
  is not an additional uncorrected look — the correction was already spent per-candidate,
  not per-combination. No further adjustment for "which pair" is required once the
  per-candidate correction is in place.
- **Testing order is retained for a DIFFERENT reason than r2 claimed**: not as the
  multiplicity-control mechanism (that role now belongs to the Bonferroni correction above),
  but purely for OPERATIONAL sequencing (cheapest/soonest-ready candidate first) and to keep
  design rule 5's "a miss is recorded and dropped, never re-run" invariant simple to
  administer:
  1. **C3 first** (2026-Q3, data exists now, cheapest to test).
  2. **C4 second** (2026-Q3, gated on S3 landing).
  3. **C2 third** (2026-Q4, gated on the N3 coverage verdict).
  4. **C1 read only, never voting** (2027-Q1 earliest read — §1.1).

The seed-robustness check (`{42,43,44}`, all three reported) within each candidate's own
test is a ROBUSTNESS check on that one already-corrected result, not an independent
additional look — it does not further multiply the k=3 family for Bonferroni purposes.

## 3. Sequencing and the stack-level decision rule (rewritten — r1's version created
optional stopping)

r1's "wait for strongest leg" language was narrative, not a rule — it implicitly allowed
checking results whenever convenient and declaring victory or defeat at will (optional
stopping), and had no defined end state if no candidate ever clearly won (G106 could stay
open indefinitely). Both are fixed here:

- **Maximum calendar date (frozen): 2027-Q4** (unchanged from the existing G106 gate date in
  §0 — this revision makes explicit that it is a hard deadline, not just a target).
- **Per-candidate outcome, using the hierarchical order in §2a**: each of C2, C3, C4 resolves
  to GO, KILL, or INCONCLUSIVE per its own Bonferroni-corrected frozen rule (§1, §2a) by its
  earliest-test date. C1 never resolves to GO/KILL under this stack's timeline (§1.1) and
  contributes NOTHING to the stack vote below — see §1.1's r3 note on why the edge case of
  C1 someday reaching a powered read is deliberately left as "requires its own follow-up
  design note," not pre-answered here.
- **Missing-data / underpowered outcome**: if a candidate other than C1 fails to reach its
  minimum effective sample size (§1, shared default: n≥600 decision dates) by 2027-Q3 (one
  quarter before the deadline, leaving time to act on the result), it is marked
  INCONCLUSIVE — NOT KILL. INCONCLUSIVE candidates do not count toward the stack GO vote
  below, but also do not count as a stack KILL vote; they are simply excluded from the
  denominator.
- **Stack-level decision rule (frozen, replaces "wait for strongest leg")**: at 2027-Q4 (or
  earlier if resolved sooner — see below), let `N_resolved` = the count of {C2, C3, C4} that
  reached a genuine GO or KILL verdict (excluding INCONCLUSIVE and excluding C1 per above).
  - **G106 GO** iff at least 2 of `N_resolved` reached GO, AND the measured combined IC
    (per §0's stacking-math projection, using the ACTUAL measured pairwise ρ, not the
    planning-range assumption) is itself ≥ 0.02.
  - **G106 KILL (fires the benchmark-sleeve/PIT-accrual/107-re-scope branch from §0)** iff
    `N_resolved < 2` reached GO as of 2027-Q4, REGARDLESS of how many are still
    INCONCLUSIVE — an inconclusive candidate does not keep the gate open past its hard
    deadline; it simply does not count as a win.
  - **Early GO**: if 2 of {C2,C3,C4} reach GO before 2027-Q4 (e.g. C3+C4 both clear in
    2026-Q3, per §2a's ordering), the gate MAY be declared GO early — this is the one
    legitimate form of the r1 "early double-clear pulls the read forward" idea, now made
    precise: early GO requires 2 genuine GO verdicts under the frozen per-candidate rules
    (§1), not an informal "looking good so far" read. Early GO does NOT skip the remaining
    candidates in the hierarchical order (§2a) — C2 and any not-yet-tested candidate still
    run on their own schedule and their results still get recorded per design rule 5, they
    just no longer gate G106's own timing.
  - There is no "early KILL": per r1's original intent (preserved here), the stack may not
    be declared dead before every candidate in the hierarchical order (§2a) that is
    scheduled to have resolved by a given date has actually had its chance to run — this
    prevents killing the stack before its strongest legs are even measurable, which was r1's
    correct original concern; what r1 lacked was the CORRESPONDING hard stop at the other
    end (an indefinite wait), which this section now supplies.

## 4. Open review questions — resolved in r2 (kept here for the record, not re-opened)

1. ~~C2's "coverage-delta ≥20% or don't re-run" — right bar?~~ Unchanged from r1; not itself
   in dispute this round.
2. ~~C3's conditioned-cell CI construction (date-block bootstrap, block=13 per A1
   convention?)~~ **Resolved**: block=60 (the shared default, matching the fwd_60d label
   horizon), not 13 — see §1.3.
3. ~~C4's frozen placebo-difference margin: propose 0.02...~~ **Resolved**: frozen at 0.02
   now, in this document — see §1.4. No longer deferred to the S3 PR.
