# RS-5 / M7 down-cap panel measurement — FALLBACK PANEL — verdict: INCONCLUSIVE (primary pending)

STATUS: research measurement memo (read-only scan; no production change, no purchase,
no capital action). Executes the FROZEN spec `doc/design/2026-07-02-rs5-downcap-panel-spec.md`
(merged PR #250; freeze point = merge commit `23dc9ff37ff1f1747e55c94363bc2794d167f482`,
2026-07-02T14:14:07-07:00) against its machine-readable prereg contract
(`doc/research/evidence/2026-07-02-rs5-m7-prereg/prereg_contract.json`, sha256
`fca9a389…dd98cfde`, byte-identical between the freeze commit and today's `main`).
Runner: `scripts/rs5_downcap_measurement.py` — loads the contract at startup, validates
every executed parameter, and refuses to run on any undeclared deviation (spec §7 duty;
this run: **0 deviations** against the contract; operational deviations from the prose
spec are disclosed as D1–D12, §8). Evidence:
`doc/research/evidence/2026-07-03-rs5-downcap/` (manifest with input SHA-256s + code SHA,
per-date IC series sufficient to recompute every bootstrap, full results incl. all seeds).

## 0. Verdict, stated first

**M7 = INCONCLUSIVE (fallback panel; primary constituency-by-date panel pending).**

This is not a hedge — it is the spec's own pre-registered outcome for this branch.
Norgate procurement is trial/POC-first per RS-3 r2/r3
(`doc/research/2026-07-02-rs3-data-vendor-stack.md`: Windows/VM + plugin POC + 3-week
acceptance test BEFORE any fixed-term commitment) and no trial has run, so the PRIMARY
panel (point-in-time R2000 membership incl. delisted names) cannot be built. Spec §2/§5,
round-2 corrected and frozen: *"NEITHER a GO NOR a NO-GO computed on the fallback panel is
decision-grade, and NEITHER may feed D3 under any circumstance … M7's own status while
awaiting that primary-panel result is INCONCLUSIVE, not any of GO/NO-GO/MISS."*

What this run DOES establish (the fallback panel's assigned role, spec §2):

1. **Pipeline feasibility: PASS.** The full M7 machinery — contract-validated runner,
   ~1,300-name panel build with frozen floors/exclusions, placebo-clean estimand, 3-seed
   block bootstrap, §3-cost gate-(b) portfolio, all sensitivity cuts, S-REL controls —
   runs end-to-end in ~36s. When the Norgate panel lands, M7 is a data-swap, not a build.
2. **Exploratory sensitivity readings** (informative context, never a decision input) —
   §4 below.
3. **The harness detects effects and passes nulls** — §5 controls.

## 1. The frozen criteria (quoted from the merged spec §5; cited, not restated)

> **GO requires (a)+(b)+(c2)+(c3)+(d) simultaneously on at least ONE family headline, on
> the PRIMARY (constituency-by-date) panel.**
>
> (a) Pooled placebo-clean IC point estimate **≥ 0.02** on ≥1 family headline, AND that
> family's one-sided 98.75% (Bonferroni k=4) block-bootstrap CI lower bound **> 0**, on
> all three seeds {42,43,44}.
> (b) Top-decile-minus-benchmark(SPY) LONG-ONLY portfolio, 60-session rebalance (3
> staggered start offsets, averaged), costs charged per §3 buckets at realized turnover
> …: annualized net Sharpe **> 0.5** point estimate, with block-bootstrap CI lower bound
> **> 0**. [The zero-borrow L/S Sharpe is demoted to a factor diagnostic.]
> (c2) two-half stability: placebo-clean IC **> 0 in both halves**; (c3) yearly breakdown:
> placebo-clean IC **> 0 in ≥ 60% of calendar years** with ≥100 clean dates. [(c1)
> largest-regime-cell-removed is EXPLORATORY ONLY, does not gate.]
> (d) **n ≥ 600** pooled clean decision dates; **≥ 200 names** per counted date;
> panel-average **≥ 500**; VAL/QUAL admissible-timestamp coverage **≥ 60%** else that
> family is INCONCLUSIVE-by-coverage.
>
> **Decisive NO-GO (KILL)**: every family headline's one-sided 98.75% CI UPPER bound
> < 0.02. **MISS**: no family clears (a)–(d) but KILL doesn't fire.

Estimand (spec §4, frozen): daily cross-sectional Spearman rank IC vs fwd_60d
excess-vs-SPY; the GATING quantity is the placebo-clean difference (real IC minus
shifted-label placebo IC per date, label shifted +horizon within ticker — exactly C3's
convention); fwd_20d reported, never gates; sighunt within-date shuffle floor (N_PERM=200)
reported as the scanner-native second placebo; block=60, n_boot=2000, seeds {42,43,44}.
Family headlines: MOM=`mom_12_1`, REV=`st_rev_21`, VAL=`value_earnings_yield`,
QUAL=quality composite — one pre-declared headline per family, k=4 Bonferroni.

## 2. Panel mode determination and the fallback panel that was built

- **Primary unavailable**: Norgate = trial-first (RS-3 r2/r3); no trial has run; no other
  point-in-time small-cap membership source exists in this system (RS-3's survey).
- **Fallback build (spec §2 protocol)**: local umbrella daily-bar store (read-only;
  2,926 tickers, broad harvest ends 2026-05-08) intersected with CURRENT Russell 2000
  membership from a free current-day constituent list — Vanguard VTWO (Russell 2000 ETF)
  holdings API, 1,938 tickers as-of 2026-05-31, snapshot + SHA-256 committed under
  `evidence/…/inputs/`.
- **Frozen §1 floors/exclusions applied**: ADV ≥ $5M (63-session median dollar volume,
  monthly re-evaluation at last session of month, applied next session), price ≥ $5,
  ≥252 sessions history; excluded: funds/ETFs (20), ADR/foreign (93), REITs (108),
  non-alpha class tickers (3), no-profile (2); secondary-share-class dedup (4);
  37 members missing from the local store. Sector/industry/isAdr/isFund flags from an
  FMP profile snapshot (1,933/1,938 fetched; committed + hashed).
- **Panel realized size**: mean 591 names/date (2,868 dates with members; scored-date
  average 602), min 328 (early era), max 1,008. **This is BELOW the frozen target band
  [800, 1,400], and the early-era minimum breaches the [500, 1,600] hard bound.** Under
  spec §1 a PRIMARY build hitting this must STOP and amend the spec with the size
  evidence before computing any factor. For this fallback feasibility run the size
  evidence is recorded (that IS the §1-mandated amendment input): the shortfall is
  survivorship geometry — a current-membership list thins out toward the past — plus the
  ADV/price floors cutting ~2/3 of R2000 names. The Norgate amendment discussion should
  expect the PRIMARY panel to be materially larger (delisted + historical members
  restored) and re-check the band there.
- **VAL/QUAL declared INCONCLUSIVE-by-coverage BEFORE any IC computation** (spec-native,
  gate (d)): zero local small-cap fundamentals with admissible timestamps (the FMP
  harvests cover the 291-name large-cap universe only), and the subscribed FMP Starter
  tier's ~5y history cap bounds attainable coverage at ~40% < the 60% floor. No VAL/QUAL
  IC was ever computed. Multiplicity stays k=4 (frozen; conservative).
- **Delisting-return machinery**: not exercisable on this panel — current-membership
  fallback contains no delisted names by construction (counts: 0/0/0 by path; the §2
  frozen -100%/proceeds conventions apply to the primary panel run).

## 3. Sample floors actually achieved (gate (d) arithmetic)

| Floor | Frozen | Achieved | Status |
|---|---|---|---|
| pooled clean decision dates | ≥600 | 2,482 (both families) | met |
| names per counted date | ≥200 | enforced per date | met |
| panel-average names (scored dates) | ≥500 | 602 | met |
| VAL/QUAL timestamp coverage | ≥60% | 0% local / ~40% max attainable | INCONCLUSIVE-by-coverage |

Clean-date window: 2016-02 → 2025-11 (label + placebo both defined; local SPY history
starts 2016-01-04 — D6). Covers the 2020 and 2022 bear episodes.

## 4. Exploratory readings (fallback panel — NOT decision-grade, feeds nothing)

Had this been the primary panel, the arithmetic would read: **no family clears the GO
gates; the KILL condition does not fire either → MISS-shaped**. On the fallback panel the
only recorded verdict is INCONCLUSIVE; the numbers below are sensitivity context.

### Gate (a) — pooled placebo-clean IC (point; one-sided 98.75% LB/UB per seed)

| Family | Headline | n | Point | LB (s42/s43/s44) | UB (s42/s43/s44) | ≥0.02 + LB>0? |
|---|---|---|---|---|---|---|
| MOM | mom_12_1 | 2,482 | **+0.0077** | −0.0308 / −0.0357 / −0.0304 | +0.0584 / +0.0583 / +0.0563 | NO |
| REV | st_rev_21 | 2,482 | **+0.0128** | −0.0101 / −0.0110 / −0.0109 | +0.0329 / +0.0325 / +0.0329 | NO |

KILL leg (UB < 0.02 on all seeds, every family): does NOT fire (both UBs > 0.02).
Seeds agree to ~3 decimal places everywhere — no seed-edge ambiguity anywhere in this
run (the #264 single-seed lesson is moot here, but all three seeds are reported per the
frozen contract regardless).

Scanner-native second placebo (sighunt shuffle floor, stride-60 non-overlapping dates,
N_PERM=200): REV clears (raw mean IC +0.0211 vs 2σ floor ≈ ±0.0125); **MOM does NOT
clear** (raw −0.0006) — under the spec's "must clear the shuffle floor to even be
discussed" precondition, the MOM headline would not even reach its gate on this panel.

### Gate (b) — long-only top-decile minus SPY (TR), §3 costs at realized turnover

| Family | Avg net Sharpe (3 offsets) | Per-offset | ±10bps | L/S zero-borrow diag |
|---|---|---|---|---|
| MOM | **+0.038** | −0.024 / +0.024 / +0.114 | +0.028 / +0.048 | +0.078 |
| REV | **−0.128** | −0.358 / −0.095 / +0.069 | −0.143 / −0.113 | +0.044 |

Both are nowhere near the frozen >0.5 bar; every bootstrap LB is deeply negative
(e.g. MOM off0 LB −0.64). Realized cost load: MOM ~22bps/rebalance at turnover 1.09;
REV ~37bps/rebalance at turnover 1.77–1.79 (reversal churns the book — exactly the
cost-eats-premium pattern the §3 buckets were frozen to expose). The ±10bps sensitivity
does not change any conclusion (report-only, never re-gates). Capacity: at this
pipeline's ≤$2k positions vs the $5M ADV floor, position <0.04% of ADV — non-binding.

### Gates (c2)/(c3) — time-split robustness

- MOM: half1 +0.0254 / half2 −0.0100 → **fails c2**; positive in 4/10 eligible years
  (40%) → **fails c3**. The MOM read is a first-half artifact on this panel.
- REV: half1 +0.0062 / half2 +0.0194 → passes c2; positive in 6/10 years (60%) →
  passes c3 exactly at the bar.

### (c1) exploratory regime diagnostic (contaminated labels — C3/#249 limitation, does not gate)

n per regime (clean dates): BULL_CALM 1,841 / BEAR 327 / BULL_VOLATILE 171 / CHOPPY 114.

- MOM per cell: BULL_CALM +0.0236, CHOPPY +0.0216, BEAR −0.0220, BULL_VOLATILE −0.0612.
  Largest-cell(BULL_CALM)-removed: **−0.0379** — the pooled positive is entirely
  bull-calm-driven (echoes C3's bull-cell geometry, on the same non-PIT regime labels).
- REV per cell: BEAR +0.0744, BULL_CALM +0.0015. Largest-cell-removed: +0.0451 —
  REV's read is substantially a bear-market effect.

### Exploratory liquidity-core cut (bucket A, ADV ≥ $25M; min-names floor 100 — not the gate's 200)

| Family | Full panel (n=2,482, ~602 names) | Bucket-A core (n=1,736, ~199 names) |
|---|---|---|
| MOM | +0.0077 | +0.0055 |
| REV | +0.0128 | **+0.0179** |

This is the nearest in-design analogue to the M8-verification mirror-image hypothesis
(#264 §5: incumbent-book dilution was similarity-specific; RANDOM waves mostly IMPROVED
incumbent-book IC — raising the prior that a high-separability CORE can out-carry
breadth). Here the high-liquidity core improves REV but not MOM — weakly consistent,
strictly exploratory, and NOT the incumbent-book core-shrink measurement itself: RS-5's
frozen design contains no incumbent-book leg, so that check belongs to the D3 memo's own
scope (on the M8 evidence), not to this scan. Recorded as context, not evidence.

### Sibling diagnostics (never gate)

mom_6_1 −0.0047, ma200_dist +0.0030, pct_52w_high +0.0052; fwd_20d supporting:
MOM −0.0019, REV +0.0087 (both LB < 0). Ex-biotech sensitivity (mandatory): MOM +0.0067,
REV +0.0147 — same conclusions as with biotech retained (no fragile-GO condition arises).

## 5. S-REL controls (the harness proves it can both detect and pass)

- **Positive control** (planted effect: rank-z(fwd_60d label) + 9.95σ noise ⇒ ~0.1
  planted IC, pre-declared magnitude, same missingness geometry as a real factor):
  pooled clean IC 0.0928/0.0936/0.0942 on seeds 42/43/44, every LB > +0.089 —
  **gate (a) detects it on all three seeds. PASS.**
- **True-null control** (seeded noise factor on the identical grid): pooled clean IC
  −0.0008/+0.0001/+0.0007, gate (a) not triggered on any seed, AND the per-family KILL
  leg (UB < 0.02) **fires** on all three seeds (max UB +0.0034) — the no-effect branch
  demonstrably fires. **PASS.**
- Unit tests (`tests/test_rs5_downcap_measurement.py`, 10 tests, in `make test`):
  the contract refuse-on-tamper branch (gate-a threshold tamper, bucket-C tamper),
  committed-contract match, cost-bucket assignment incl. below-floor drift, sighunt
  factor-formula equality, C3 placebo construction, monthly-floor
  applied-next-session timing, min-names enforcement, and both controls in miniature.

## 6. What this feeds into D3 (cite, don't re-litigate)

Per the alpha-frontier synthesis addendum (master plan
`doc/design/2026-07-02-unified-107-master-plan.md`, 07-03 addendum §"D3 down-cap (Term
BR, the one live model decision)") D3 down-cap is Term BR's only remaining route after
M8's verified NO-GO (#261, verification #264: waves stop; gate fails at every seed).

- **This run gives D3**: M7 status = INCONCLUSIVE-pending-primary. This is explicitly
  NOT the master plan's "M7 null ⇒ D3 = new-data-only, P(G106) → 0.35–0.40" branch —
  no M7 verdict has been rendered. D3 must either (i) wait on the Norgate trial →
  primary panel → decision-grade M7 under these same frozen thresholds, or (ii) decide
  on its other inputs while carrying M7 as pending.
- **The #264 §5 interpretive correction stands as D3 input on its own evidence**
  (similarity-specific dilution; random waves mostly improved incumbent-book IC —
  "shrink to the high-separability core" now has real evidence). Our bucket-A cut is a
  weak, in-design echo (REV improves on the liquid core), exploratory only.
- **Cost realism preview** (exploratory): even the frozen §3 buckets — before borrow,
  before the primary panel's delisting drag — reduce both fallback headlines to ~0 net.
  Any D3 down-cap enthusiasm should price gate (b) as the binding constraint, not
  gate (a).

## 7. Reopening conditions (recorded; none of these is a re-pitch)

1. **R1 — the required next step**: Norgate Windows/VM + plugin POC + 3-week trial
   acceptance test (spec §6 item 1, four pass/fail criteria incl. delisting-proceeds
   joinability). On pass: build the PRIMARY panel and re-measure under the SAME frozen
   thresholds (no re-freeze — spec §2). That run renders M7's decision-grade verdict.
   Procurement/spend is ask-first per standing operator directive.
2. **R2**: a fundamentals source with ≥60% admissible-timestamp coverage of the panel ×
   date grid unlocks VAL/QUAL (INCONCLUSIVE-by-coverage never voted; re-running after
   fixing coverage is spec-sanctioned).
3. **R3**: bar-store refresh (experiment paths only) extends the resolved-outcome era
   past 2026-05-08.

## 8. Deviations disclosed (D1–D12)

Recorded in full in `evidence/…/manifest.json` (`deviations_disclosed`); headline items:
**D1** fallback panel (spec-native branch, verdict INCONCLUSIVE, zero D3 authority);
**D2** runner filename `rs5_downcap_measurement.py` (dispatch-directed) vs spec §6's
`m7_downcap_scan.py` — all §6-item-3 duties implemented; **D3** membership = VTWO
holdings as-of 2026-05-31 (~1 month stale); **D4** REIT/type/ADR screens from FMP
profile flags, not GICS 60/SIC 6798; **D5** biotech cut keyed on FMP industry; **D6**
SPY history starts 2016-01-04 → clean window starts 2016 (n=2,482 ≫ 600); **D7** panel
intermediates in the session scratchpad, not umbrella `data/exp` (no-writes-outside-
scratchpad rule this run; hashes recorded); **D8** no bar refresh (landing actions
ask-first; era ends 2026-05-08); **D9** VAL/QUAL coverage arithmetic (above); **D10**
share-class dedup heuristic; **D11** ±0.5 label clip inherited from the C3 repo
convention; **D12** shuffle floor on stride-60 non-overlapping dates (sighunt-native).

## 9. Evidence boundary

Panel window 2014-01-01 → 2026-05 (bulk of store ends 2026-05-08); scored dates
2015-01-02 → 2026-05; clean (gating) dates 2016-02 → 2025-11, n=2,482; n per regime as
in §4(c1); resolved-outcome era ends 2026-05-08. Survivor-conditioned membership: bias
direction NOT identified (spec §2 round-2 correction — this is exactly why the panel
cannot gate). Multiple-comparisons frame: Bonferroni k=4, one-sided α=0.0125, held at
k=4 despite two families being coverage-inconclusive. Seeds {42,43,44} all run, all
reported, none cherry-picked.
