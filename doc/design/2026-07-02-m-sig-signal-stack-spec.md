# M-SIG: the G106 signal-stack spec — candidates, estimands, frozen thresholds, kill conditions

STATUS: design / pre-registration scaffold for review (docs only). This is the MID-term IC
core of the unified plan (#231 §1 Term IC) — the explicit build+measure task G106 gates on.
DATE: 2026-07-02 (r1); r2 2026-07-02 (Codex review: r1 was a candidate roadmap with
substantial researcher degrees of freedom left open in every candidate — not yet a frozen
spec. This revision closes every open parameter per candidate, adds multiplicity control,
separates prior-inspected from genuinely prospective evidence, and replaces the narrative
"wait for strongest leg" sequencing rule with a deterministic, date-bounded stack decision
procedure.)

**Freeze status (honest, per-candidate — see §1 for detail): C2, C3, C4 are FROZEN — every
parameter below is fixed and may not be tuned after seeing a result. C1 is FROZEN on
methodology/procedure but its go/kill bar's STATISTICAL POWER is honestly unresolved until
real accrued data exists to check it against (§1.1); C1 may not be used as a standalone
go/kill gate until that check passes — see the explicit downgrade rule in §1.1.**

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
  blocks understates true uncertainty. 600 is a floor, not a target; report the actual `n`
  and block count achieved.
- **Deterministic decision rule (default)**: GO iff the block-bootstrap 95% CI lower bound
  exceeds the candidate's frozen individual threshold; KILL iff the CI upper bound is below
  the threshold; else INCONCLUSIVE (this mirrors the frozen equivalence-style rule already
  applied to `#235`/`#431` this session — a point estimate above the bar is never sufficient
  on its own).
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
  **Frozen resolution — codex's third option, applied**: C1 is DOWNGRADED to
  INFORMATIVE-ONLY at both the 6mo and 9mo checkpoints. It may NEVER independently decide
  GO or KILL for the stack. At each checkpoint, compute the empirical monthly-IC std from
  the actually-accrued data and the resulting CI width using the SAME moving-block-bootstrap
  machinery (block=1 month here, since that's the true independence unit) applied to however
  many monthly points exist; report it, but do not gate on it. C1 is READ (not decided) at
  9mo: if the point estimate and CI are directionally encouraging (CI does not clearly
  exclude the 0.015 bar), accrual continues indefinitely as a background PIT-collection task
  and C1 is re-read at each subsequent 6-month mark using the same informative-only
  procedure — it simply never becomes a G106 stack vote until the CI is genuinely narrow
  enough to resolve GO/KILL, which may take years at this cadence. **G106's ≥2-of-4 stack
  vote (§3) is computed over C2/C3/C4 only unless C1 someday reaches a genuinely powered
  read; the 2027-Q4 gate date does not wait on C1.**
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
- **As-of lag**: 1 trading day after `acceptedDate` (SEC filing acceptance timestamp, or
  FMP's equivalent PIT field — confirm exact field name against the N3-upgraded FMP schema
  in the build PR; if it differs from `acceptedDate`, use whichever field FMP's Starter tier
  actually PIT-stamps, and record that decision).
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
- **Beta/sector definitions (frozen)**: market beta = OLS slope of the name's daily return
  against the S5/S8 substrate's existing benchmark series (whatever this repo's production
  panel already uses as its market factor — confirm the exact series name in the build PR
  and cite it; do not introduce a new benchmark definition). Sector = this repo's existing
  production sector-map assignment (the same map already used elsewhere in the panel
  pipeline — confirm and cite the exact source file in the build PR).
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
- **The frozen comparison (unchanged from r1, restated precisely)**: GO requires BOTH (a)
  the conditioned (residual×regime) cell's own CI lower bound > 0.015, AND (b) the
  conditioned-minus-unconditioned point-estimate difference has a block-bootstrap 95% CI
  that excludes zero on the positive side (computed via the paired daily difference series,
  block-bootstrapped the same way — not two separate CIs compared by eye).
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
- **Placebo-difference margin (frozen NOW, not deferred)**: **0.02**. Justification: the
  measured shared embargo-leakage floor is ~+0.04 (see
  `doc/design/2026-06-30-model-freshness-governance.md`'s Fix-3 discussion and this
  session's memory record `wf-gate-embargo-leakage-floor`) — requiring the placebo
  DIFFERENCE (trend-scan minus raw) to exceed 0.02 means the signal must clear roughly half
  of that floor's magnitude, which is comfortably distinguishable from floor noise while
  not being an arbitrarily strict bar. r1 left this "to be fixed in the S3 gate-repair PR" —
  that deferral is exactly the "claims frozen, isn't" contradiction codex flagged. **This
  revision freezes the margin here, in this design doc, now.** S3's job is to confirm the
  repaired gate computes placebo-difference correctly, not to choose or adjust this number.
- **Deterministic rule**: GO iff placebo-difference (trend-scan minus raw, on the S3-repaired
  gate) block-bootstrap 95% CI lower bound > 0.02, evaluated on production WF; sim
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

## 2a. Multiplicity control (new in r2)

The candidate space has real multiplicity: 4 candidates, C3's residual×regime combination,
seed-robustness across `{42,43,44}` per candidate, and C1's window/FY choice (now closed to
a single 1m/FY1 path — see §1.1, which itself IS this revision's multiplicity-reduction move
for that candidate). Without control, the chance that at least one candidate/cut spuriously
clears its bar is materially higher than the nominal per-candidate α=0.05.

**Frozen rule: a FIXED HIERARCHICAL TESTING ORDER, not a formal multiplicity correction.**
A Bonferroni-style correction across 4 candidates would shrink each already-thin-sample
threshold further, compounding C1's power problem onto every candidate — the wrong tool
here. Instead, the candidates are tested in a fixed, pre-declared order, and only a
candidate's OWN frozen bar (§1, not a corrected one) applies at its own test — the ordering
itself is what bounds the effective number of independent "looks" the overall G106 decision
gets to take:

1. **C3 first** (2026-Q3, data exists now, cheapest to test).
2. **C4 second** (2026-Q3, gated on S3 landing).
3. **C2 third** (2026-Q4, gated on the N3 coverage verdict).
4. **C1 last, informative-only** (2027-Q1 earliest read, never a standalone gate — §1.1).

Each candidate's result is FINAL once measured (per design rule 5: a miss is recorded and
dropped, never re-run under the same hypothesis) — this, not a p-value correction, is what
prevents "keep trying candidates until one clears." The seed-robustness check
(`{42,43,44}`, all three reported) within each candidate's own test is a ROBUSTNESS check on
that one result, not an independent additional look — it does not multiply the candidate
count for multiplicity purposes.

## 3. Sequencing and the stack-level decision rule (rewritten — r1's version created
optional stopping)

r1's "wait for strongest leg" language was narrative, not a rule — it implicitly allowed
checking results whenever convenient and declaring victory or defeat at will (optional
stopping), and had no defined end state if no candidate ever clearly won (G106 could stay
open indefinitely). Both are fixed here:

- **Maximum calendar date (frozen): 2027-Q4** (unchanged from the existing G106 gate date in
  §0 — this revision makes explicit that it is a hard deadline, not just a target).
- **Per-candidate outcome, using the hierarchical order in §2a**: each of C2, C3, C4 resolves
  to GO, KILL, or INCONCLUSIVE per its own frozen rule (§1) by its earliest-test date. C1
  never resolves to GO/KILL under this stack's timeline (§1.1) — it contributes NOTHING to
  the stack vote below unless it independently reaches a powered read before 2027-Q4, in
  which case it is added to the vote using its own frozen bar.
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
