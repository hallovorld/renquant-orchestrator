# RS-5: the M7 down-cap MVP screen — panel specification + frozen thresholds (pre-registration)

STATUS: design / pre-registration for review (docs only — no data crunching, no panel built,
no scan run, no purchase made). This is RS-5 of the unified plan (`#231` §1 Term IC, M7 row;
`doc/design/2026-07-02-h2-execution-roadmap.md` §6, RS-5 row: "M7's panel spec + frozen
thresholds; AC: M7 runs on it"). Every threshold below is FROZEN as of this document's merge
date, BEFORE any down-cap panel exists or any down-cap number has been computed or inspected —
the prereg discipline the M7 row itself demands ("frozen thresholds BEFORE running").
DATE: 2026-07-02 (r1)

**Binding design rules inherited from the M-SIG spec**
(`doc/design/2026-07-02-m-sig-signal-stack-spec.md` §2, applied here unchanged):
placebo-clean DIFFERENCES only (never absolute IC — the ~+0.04 embargo-floor lesson);
per-regime cuts mandatory; frozen thresholds cited from THIS table by the eventual scan PR;
a miss is recorded (evidence doc) and dropped, never re-argued. Changes to any frozen number
in this document require a fresh, explicitly-labeled amendment PR merged BEFORE the scan
runs — never after a result exists, and never via a roadmap re-baseline addendum
(`2026-07-02-h2-execution-roadmap.md` §8's scope limit names "M7's frozen thresholds"
explicitly as un-revisable by addendum).

## 0. Motivation — why M7, and why its dependence just went up

- **The route**: `#230` §2.4 ranks "point the same machinery at a less-arbitraged universe"
  as a literature-supported path to both IC and BR (breadth). M7 is that bet's cheap,
  read-only MVP screen; D3 (`#231` §1.5) consumes its verdict when choosing the 106/107
  information set.
- **C3's status is UNRESOLVED, not a settled prior (PR #249, corrected round 2, 2026-07-02)**
  — regime-conditioned residual momentum, the first candidate M-SIG attempted to formally
  vote, was found to rest on future-contaminated substrate (its historical regime labels and
  survivorship-biased universe were both reconstructed with present-day information not
  knowable on the historical decision dates they claim to describe). Its governing verdict is
  **UNADJUDICATED**, not MISS — C3 casts **no formal vote**, neither GO nor a recorded MISS,
  per #249 §10. This document does NOT treat C3 as one of two remaining live M-SIG candidates,
  does NOT claim "one M-SIG vote is already spent," and does NOT cite a specific P(G106)
  reading conditioned on C3's outcome — all of that depends on a decision-grade C3 result that
  does not yet exist. **What raises D3's dependence on the down-cap leg is unchanged in
  direction but currently unquantified**: M7 remains a large potential IC+BR contributor to
  the plan regardless of how C3 eventually resolves, and this spec exists so that when M7 runs
  (early Aug per RS-5's due date), its verdict is decision-grade rather than another
  retrospectively-argued number.
- **A methodological lesson from C3's exploratory measurement, independent of its verdict**:
  C3's raw bull-cell IC (+0.0253) was measured to be almost entirely explained by its own
  label-shift placebo (+0.0275) — this specific NUMBER is an empirical fact from C3's
  measurement and is unaffected by the verdict-classification correction above. Overlapping-
  horizon label structure can inflate apparent IC; a NEW panel (down-cap) has an UNMEASURED
  placebo structure. Every gate below is therefore stated on placebo-clean differences, and
  the headline IC bar is set ABOVE the large-cap 0.015 convention (see §5 rationale). This
  lesson is cited as a cautionary empirical observation, not as evidence that C3's own
  candidate-level verdict is settled.

**External evidence (tier: EXTERNAL/CITED — motivates the bet, never substitutes for our own
measurement, per the M-SIG prospective/retrospective discipline):**

- Hou, Xue & Zhang (2020, RFS, "Replicating Anomalies"): ~65% of published anomalies fail
  replication under NYSE breakpoints + value-weighting; the anomalies that survive
  concentrate their returns in small/micro caps. This is BOTH the bet (the factors that
  NULLed on our large-cap panel may live down-cap) AND the trap (much of that concentration
  sits in names too illiquid to trade — hence the liquidity floor in §1 and the frozen cost
  model in §3).
- McLean & Pontiff (2016, JF): anomaly returns decay ~26% out-of-sample and ~58%
  post-publication. Applied here as a prior haircut: literature small-cap factor premia are
  read at roughly half strength, which is part of why the GO bar is 0.02 and not the
  literature-implied larger number.
- Realistic small-cap costs: Novy-Marx & Velikov (2016, RFS, "A Taxonomy of Anomalies and
  their Trading Costs") — small-cap anomaly portfolios carry one-way effective spreads in the
  tens of bps and many published premia do not survive them; Frazzini, Israel & Moskowitz
  (2018, JF) measure far lower realized costs but ONLY via patient, liquidity-providing
  execution that this pipeline does not have (POC-C: our fills are AT THE OPEN, crossing the
  spread — their cost regime is not ours and may not be cited to soften §3); Corwin & Schultz
  (2012, JF) high-low spread estimation documents the small-cap spread magnitudes the §3
  buckets are anchored to.

## 1. Universe construction (frozen)

| Parameter | Frozen value | Rationale | Evidence tier |
|---|---|---|---|
| Index basis | **Russell 2000, point-in-time membership by date** (Norgate constituency-by-date boolean, per RS-3) | The canonical small-cap universe: cleanest mapping to the HXZ small-cap-concentration evidence and to published small-cap cost studies; R2500's mid-cap half dilutes the down-cap hypothesis and partially overlaps existing large/mid coverage. R3000−R1000 derivation acceptable if the plugin exposes it that way. | RS-3 (measured vendor capability, corrected r2) + HXZ (cited) |
| Membership timing | Daily membership truth as exposed by the vendor boolean; floors re-evaluated MONTHLY (last session of month, applied next session) | Daily membership avoids reconstitution look-ahead; monthly floor evaluation avoids daily churn in the panel roster | house convention (PIT discipline) |
| Liquidity floor | **ADV ≥ $5M** — trailing 63-session median dollar volume, computed PIT at each monthly evaluation | NOT about our market impact (a ≤$2k position is <0.05% of $5M ADV): the floor exists because (i) the §3 cost model is only calibrated for reasonably-traded names, (ii) HXZ-style anomaly concentration below this line is substantially an untradeable-illiquidity premium, and a GO measured there would not be implementable even at our size at acceptable spread | proposed in `#231` M7 planning; magnitude anchored to NMV (cited) |
| Price floor | **≥ $5** at each monthly evaluation | Penny-stock exclusion convention: below $5 the $0.01 minimum tick is a structurally large fraction of price (≥20bps/tick), short-margin rules differ, and spread evidence does not extend there | microstructure convention (cited) |
| Minimum history | **≥ 252 sessions of bars** before a name enters any scored cross-section | mom_12_1 and the 52-week factors need a full year; matches C3's frozen convention | house convention |
| Panel window | **2014-01-01 → scan as-of date**; scored dates begin after the 252-session burn-in (≈2015-01) | ≥10 years ⇒ ~2,500 potential decision dates — comfortably above the n≥600 floor (§5d) even after regime cuts; covers ≥2 bear episodes (2020, 2022) for the regime-robustness leg | shared M-SIG sample-size default |
| Security types | Common equity only: **exclude** closed-end funds, SPACs, units, warrants, preferreds, secondary share classes (keep primary line only) | Non-operating vehicles are not the hypothesis; Norgate security-type flags make this mechanical | house convention |
| ADRs / foreign issuers | **Exclude** | Different disclosure regime (20-F/6-K cadence breaks the acceptedDate-lag discipline the value/quality factors rely on) + home-market gapping; Russell's US-home-country rule makes this nearly moot, but it is pinned so the fallback panel (§2), which is NOT Russell-screened, applies the same rule | house convention (PIT discipline) |
| REITs | **Exclude panel-wide** (GICS 60 / SIC 6798) | EY/accruals/GP-A are not comparable under REIT accounting (FFO vs EPS, payout-mandated balance sheets); standard exclusion in the accounting-anomaly literature. Cost: ~8% of R2000 breadth — accepted and stated | literature convention (cited) |
| Financials (non-REIT) | **Retain for price-family factors; exclude from value/quality factor cross-sections** | Fama-French/HXZ convention: accounting-based factors are not comparable for financials (leverage is the business, accruals undefined-ish); price factors (momentum/reversal) have no such problem — excluding financials panel-wide would gut ~15–20% of breadth for no measurement gain | literature convention (cited) |
| Biotech / binary-event names | **RETAIN in the panel**, with a MANDATORY ex-biotech sensitivity cut reported | Blanket exclusion would remove one of R2000's largest sectors, break comparability with the literature panels the priors come from, and constitute pre-emptive post-hoc selection. Binary-event risk is a POSITION-sizing concern for eventual trading, not a cross-sectional-measurement concern (rank IC on 800+ names is robust to idiosyncratic jumps). If a GO holds only WITH biotech and fails ex-biotech, the GO must be reported as fragile — the sensitivity is part of the frozen report format, not optional | judgment call, stated |
| Target panel size | **800–1,400 names per date** after floors + exclusions. **Hard bounds [500, 1,600]**: if the built panel falls outside, the build STOPS and this spec is amended (with the size evidence) BEFORE any factor is computed | A realized size wildly off the target means the floors are mis-specified — that must be fixed by amendment BEFORE evidence exists, not tuned against results | prereg discipline |

No sector residualization in the MVP: the production `sector_map` covers only the 104
universe, and inventing a new 1,400-name sector classification inside the scan would be an
uncontrolled instrument. The MVP scans RAW factors (§4); sector-concentration is reported as
a diagnostic only if the vendor's classification is available, else omitted — stated, not
silently skipped.

## 2. Survivorship protocol (frozen)

**Primary: constituency-by-date (no survivorship).** Membership at date t is the vendor's
point-in-time boolean at t, including names later delisted; delisted names' bars come from
the vendor's delisted-securities coverage (Norgate Platinum, per RS-3).

**Round-2 correction: delisting-return handling was materially wrong and is now frozen
properly.** The prior round specified "carry the last available price forward through a
forward-return window" as a "conservative simplification." This is WRONG for
bankruptcy/distress delistings specifically: it replaces what should be a large NEGATIVE
terminal return (the position going to near-zero) with a ZERO price-change after the last
quote, which can INFLATE (not flatter/deflate) a long-factor strategy's measured returns —
the opposite of conservative. The frozen handling is now:

1. **Preferred: vendor-provided delisting proceeds/returns, if available.** RS-3's Norgate
   Platinum entry documents "delisted securities" bar coverage but does not confirm whether
   that coverage extends to the actual delisting EVENT's cash-recovery/proceeds data (a
   distinct question from having historical bars up to the last trading day). The Norgate
   trial/POC (§6, item 1) must explicitly verify this as part of its acceptance test — this is
   now the fourth pass/fail criterion in §6's Norgate trial acceptance test, alongside the
   three already listed there.
2. **Frozen fallback convention if proceeds data is unavailable**: a name that delists for a
   REORGANIZATION/MERGER/ACQUISITION reason contributes the actual deal consideration if known,
   else the last available price (genuinely conservative for this delisting TYPE, since the
   position was not distressed). A name that delists for a
   BANKRUPTCY/LIQUIDATION/ADMINISTRATIVE-DELINQUENCY reason (i.e. any delisting NOT
   accompanied by a corporate action with disclosed consideration) is assigned a **-100%
   terminal return** for the remainder of the forward window from the last trading date — the
   empirically-defensible convention for a delisting type where the vendor cannot confirm a
   non-zero recovery, rather than silently assuming no further loss occurred. Delisting REASON
   classification uses whatever vendor field distinguishes these categories (verify during the
   Norgate trial; if the vendor cannot reliably distinguish delisting reason, ALL delistings
   without confirmed proceeds default to the -100% convention).
3. **Missingness and sensitivity reporting (mandatory in the scan PR's evidence)**: report the
   count and fraction of forward-return windows affected by each delisting-return path (vendor
   proceeds / disclosed consideration / -100% convention), and report the verdict's sensitivity
   to the -100% convention (e.g., recompute (a)'s point estimate with those observations
   excluded entirely, as a bounding check — does the family headline's GO/NO-GO status change).
4. **If none of the above can be made rigorous by scan time** (no vendor proceeds field
   confirmed, no reliable delisting-reason classification, and the sensitivity check itself
   cannot be computed), the affected forward-return observations are INADMISSIBLE — excluded
   from the panel entirely, with the resulting coverage loss stated explicitly in the scan PR,
   rather than silently reverting to the biased carry-forward convention this correction
   removes.

**Fallback if Norgate procurement slips** (RS-3 downgraded the purchase to trial/POC-first —
slip is a real possibility): build the panel from the EXISTING local daily-bar store
(umbrella `data/ohlcv/<T>/1d.parquet` — verified read-only this session: ~2,926 tickers
including small caps, e.g. ANDE/THRM with 2014-01→2026-05 history) filtered to CURRENT
Russell 2000 membership from a free current-day constituent list, same floors/exclusions as
§1.

**Round-2 correction: the survivorship bias direction is NOT identified, and the fallback
asymmetry claimed in the prior round was wrong.** The prior round asserted that conditioning
2014–2026 measurement on 2026 survival "mechanically inflates" momentum-, quality- and
value-factor ICs, citing PR #249's C3 doc §7 for the same direction. That citation is now
stale: C3's own round-2 correction explicitly WITHDREW that claim ("survivorship makes the
result conservative" was found UNSUPPORTED and removed) and states plainly that omitting
delisted/removed names can raise OR lower momentum IC, can alter sector residuals, and can
change regime-conditioned differences — in EITHER direction, depending on which names would
have been removed and when. The same reasoning applies here: survivorship changes ranks,
sector composition, cross-sectional dispersion, and BOTH the long and short legs; the sign is
not predictable in one direction for every family in §4.

Because the bias direction is uncharacterized, the fallback panel's role is restricted to
**pipeline feasibility testing and exploratory sensitivity analysis only**:

- **The fallback panel may be used to verify the scan pipeline runs end-to-end and to report
  exploratory, sensitivity-only readings** — informative context, never a decision input.
- **NEITHER a GO NOR a NO-GO computed on the fallback panel is decision-grade, and NEITHER may
  feed D3.** This replaces the prior round's asymmetric rule (which trusted a fallback NO-GO
  as decision-grade) — that asymmetry assumed a known bias direction that does not hold.
- **The only path to a decision-grade M7 verdict is the PRIMARY (constituency-by-date) panel.**
  If Norgate procurement slips past M7's early-Aug slot, M7's verdict is INCONCLUSIVE (not
  NO-GO) until the primary panel can be built — complete the Norgate trial/purchase and
  measure on the constituency-by-date panel under this same spec (same thresholds — no
  re-freeze). Reporting any fallback-panel result as an M7 GO or NO-GO is a spec violation.

The scan PR must state which panel (primary/fallback) it ran on, in its title and evidence
manifest. Fallback build-time note: the broad local harvest is stale (bars end 2026-05-08
for non-universe names); a refresh is a build-time task writing ONLY to experiment paths
(`data/exp/…` per the `RenQuant#430` protected-path contract), never canonical prod paths.

## 3. Cost model — frozen round-trip assumptions per liquidity bucket

Frozen BEFORE the scan; the `#231` M7 row's planning figure was a flat 25–40bps — refined
here into three ADV buckets. Charged per unit turnover: one-way cost = round-trip/2 per side,
cost per rebalance = Σ|Δw| × (RT(bucket)/2).

| Bucket | ADV (63d median $) | Frozen round-trip | Anchor (tier: EXTERNAL/CITED + our own POC-C) |
|---|---|---|---|
| A | ≥ $25M | **25 bps** | Upper small-cap/lower mid-cap quoted spreads ~10–20bps (NMV effective-spread tables; Corwin-Schultz magnitudes) + open-auction slippage per POC-C (our fills cross the spread at the open) |
| B | $10M – <$25M | **40 bps** | Mid-range R2000 quoted spreads ~20–35bps + the same open-auction regime |
| C | $5M – <$10M | **60 bps** | Low-ADV R2000 tail: quoted spreads commonly 30–60bps; NMV documents many published premia failing exactly here |

- **Bucket C deliberately EXCEEDS the plan's 25–40bps headline. Round-2 correction to the
  rationale**: the prior round claimed a too-high cost model "can only cause a safe false
  NO-GO." That is false decision theory — a false NO-GO has a REAL cost too, since it can kill
  a genuinely deployable, profitable opportunity; it is a different kind of error, not a
  costless one. The actual justification for bucket C's conservative value is evidentiary, not
  a claimed asymmetric-safety argument: the published spread evidence for the $5–10M ADV tail
  does not support 40bps for spread-crossing execution, and POC-C confirms this pipeline's
  execution IS spread-crossing (fills at the open, +23–49bps/entry measured on LARGE caps —
  small caps will not be cheaper). Sensitivity of the verdict to ±10bps per bucket remains a
  mandatory report-only diagnostic (below), which is the actual mechanism for surfacing
  whether the cost assumption is doing decisive work — not an appeal to one error direction
  being inherently safe.
- **Round-2 correction: gate (b) is now the sole cost-accounting gate (§5).** The L/S
  construct is no longer the primary gate — see §5(b)'s correction: the GATING net-return
  measurement is now a long-only top-decile-minus-benchmark construction with realized §3
  costs charged directly against realized turnover. The zero-borrow-fee decile L/S Sharpe is
  retained as a FACTOR-DIAGNOSTIC metric only (not gating), consistent with the shorting
  mandate making real small-cap shorts near-prohibited and small-cap borrow availability/fees
  being able to dominate an unrealistically-cheap short leg.
- These numbers may be revised ONLY by an amendment PR merged before the scan runs. After
  the scan, they are what they are — sensitivity of the verdict to ±10bps per bucket is part
  of the frozen report format (report-only, never re-gates).

## 4. The scan suite — committed scanners, enumerated factors, placebo convention

Reuse the EXISTING committed scanner patterns — no new methodology is invented for M7:

- `scripts/sighunt.py`: panel/caching/manifest contract (pinned `--as-of`, bars-cache +
  universe hashes, `manifest.json` with parameters + code commit), the ~5 canonical price
  factors, within-date shuffle noise floor (N_PERM≥200), non-overlapping-window headline ICs.
- `scripts/robustness.py`: Newey-West HAC t on overlapping daily ICs, two-half stability,
  yearly breakdown.
- `scripts/regimemom.py` / the C3 measurement harness: per-regime cuts using the production
  regime chain reconstruction. **This method is NOT point-in-time** — C3's own investigation
  (PR #249 §6) confirmed the regime labels come from a GMM artifact trained 2026-05-22 and
  today's pinned code/config replayed backward to 2016; dates before the training date are
  IN-SAMPLE for the GMM, and no production-emitted historical regime-label history or
  walk-forward-trained alternative exists anywhere in this codebase (#249 §6 searched and
  found none). Regime-derived cuts in this spec are therefore EXPLORATORY DIAGNOSTICS ONLY —
  see §5(c)'s correction below; they do not gate M7's verdict.
- `scripts/fundamentals_scan.py`: value/quality factor definitions + the
  `acceptedDate`→`filingDate` next-session lag discipline (period-date fallback PROHIBITED —
  the M-SIG r4 lookahead correction applies verbatim; observations with no genuine filing
  timestamp are inadmissible, with the SEC EDGAR `available_date` join as the fallback
  before inadmissibility).

**Factor families (k=4, frozen) — the canonical set that NULLed on large caps, with ONE
pre-declared headline factor per family** (the headline gates; siblings are diagnostics
only — this kills within-family cherry-picking):

| Family | Headline (GATES) | Siblings (diagnostic only) | Large-cap prior (tier: measured, retrospective) |
|---|---|---|---|
| MOM | `mom_12_1` | `mom_6_1`, `ma200_dist`, `pct_52w_high` | NULL on 104 universe (2026-06-28 scan). C3's regime-conditioned residual-momentum measurement on this cell is currently UNADJUDICATED (substrate contamination, PR #249) — not cited as a MISS or as any other settled prior |
| REV | `st_rev_21` | — | NULL on 104 universe |
| VAL | `value_earnings_yield` | `value_book_to_price`, `value_fcf_yield` | NULL on thin free-tier panel (`fundamentals_scan`) |
| QUAL | equal-weight quality composite per M-SIG C2 (GP/A, −accruals, −net issuance), or `quality_low_accruals` alone if GP/A+issuance coverage is inadequate down-cap — **which of the two runs is declared in the build PR BEFORE any IC is computed**, based on coverage counts only | `quality_roe`, `quality_gross_margin` | NULL on thin free-tier panel |

**Estimand and placebo (frozen, house convention):** daily cross-sectional Spearman rank IC
vs **fwd_60d** excess-vs-SPY (gating horizon; fwd_20d reported, never gates). The GATING
quantity is the **placebo-clean difference**: real IC minus shifted-label placebo IC per date
(label shifted +horizon within ticker, defined only where both exist — exactly C3's
convention), never absolute IC. The sighunt within-date shuffle floor is ALSO reported as
the scanner-native second placebo (a factor must clear its shuffle floor to even be
discussed, but the gate is the placebo-clean difference). Per-regime cuts (production regime
chain reconstruction) are mandatory diagnostics; the GATE is on the full pooled panel — the
down-cap hypothesis is not regime-conditional, and per-regime cells gate nothing (§5c uses
them only for robustness checks).

**CI machinery (frozen, shared M-SIG defaults):** moving-block bootstrap on the per-date
placebo-clean IC series, block=60 (the fwd_60d horizon), n_boot=2000, seeds {42,43,44} all
run and reported. **Multiplicity: Bonferroni k=4** across the four family headlines —
per-family one-sided α = 0.05/4 = 0.0125, i.e. a one-sided **98.75%** CI (mirrors M-SIG §2a's
reasoning: valid under any correlation structure, no step-down ordering needed). Seeds are a
robustness check on one corrected result, not extra looks.

**Prospectivity (round-2 correction — the novelty check alone is NOT sufficient).** The scan
PR must include the specific-combination novelty affirmation — no prior script in this repo's
history has computed these factor×down-cap-panel combinations (true today: every committed
scan ran on the 104/142-name large-cap watchlist). Per C3's own round-2 correction (PR #249
§8, which found the identical pattern insufficient for its own measurement), this affirmation
is NECESSARY BUT NOT SUFFICIENT for confirmatory status: "no identical prior script" only
rules out this EXACT combination having run before; it does not by itself establish that the
hypothesis, thresholds, transformations, universe, and replay convention were fixed BEFORE the
scan's results were observed. The actual mechanism that makes this preregistration confirmatory
is the machine-readable preregistration artifact (§7, below) merged into `main` BEFORE the
scan PR opens, with its merge commit's timestamp serving as the demonstrable freeze point —
the scan PR must cite that merge commit SHA and merge timestamp, and the runner (§6, item 3)
must consume the artifact directly and refuse to run against parameters that deviate from it.
The novelty affirmation remains a useful sanity check but is not, by itself, what makes this
prospective.

## 5. FROZEN GO/NO-GO thresholds for M7

**GO requires (a)+(b)+(c2)+(c3)+(d) simultaneously on at least ONE family headline, on the
PRIMARY (constituency-by-date) panel** (round-2 correction: (c1) is exploratory-only and does
not gate — see (c)'s entry). **NEITHER a GO NOR a NO-GO computed on the fallback panel is
decision-grade, and NEITHER may feed D3 under any circumstance** (§2: survivorship bias
direction is not identified for this measurement, so a fallback result cannot be trusted in
either direction — this is not an asymmetric rule; a fallback panel run has no D3 authority
at all, in either direction).

| # | Gate | Frozen value |
|---|---|---|
| (a) | Net-relevant placebo-clean IC | Pooled placebo-clean IC point estimate **≥ 0.02** on ≥1 family headline, AND that family's one-sided 98.75% (Bonferroni k=4) block-bootstrap CI lower bound **> 0**, on all three seeds {42,43,44} |
| (b) | Net long-only-vs-benchmark return (GATES) | **Round-2 correction — the zero-borrow-fee L/S Sharpe cannot gate D3.** The shorting mandate makes real small-cap shorts near-prohibited, and small-cap borrow availability/fees can dominate the short leg; a measurement that assumes zero borrow cost is not a deployable strategy and an acknowledged-optimistic number cannot authorize a structural decision. The GATING quantity is now: top-decile-minus-benchmark(SPY) LONG-ONLY portfolio, 60-session rebalance (3 staggered start offsets, averaged), costs charged per §3 buckets at realized turnover, capacity-checked against the realized position sizes this pipeline would actually take: annualized net Sharpe **> 0.5** point estimate, with block-bootstrap CI lower bound **> 0**. (Same structural-unmeetability note as before on requiring LB > 0.5 at ~10y of 60d periods — the LB>0 leg guards sign, the point estimate carries the bar.) The decile L/S Sharpe (zero-borrow-fee, as originally specified) is now DEMOTED to a FACTOR-DIAGNOSTIC metric only — informative context for D3 on the raw cross-sectional signal's long/short symmetry, never gating. If a future amendment wants to restore L/S as a gate, it must first add point-in-time small-cap borrow availability/fee data and explicit short-constraint modeling — out of scope for this fix |
| (c) | Regime robustness (not a single-regime artifact) | **Round-2 correction — (c1) demoted, (c2)/(c3) remain gating.** All per-regime robustness checks inherit C3's regime-label contamination (§4 above; production regime chain reconstruction is not point-in-time, and no PIT alternative exists in this codebase per #249 §6's search). Splitting: (c1) *(EXPLORATORY ONLY, does not gate)* placebo-clean IC with the largest regime cell (by date count) REMOVED — reported as a diagnostic, informs interpretation, never counted toward GO/NO-GO. (c2) two-half stability *(GATES, unchanged — this is a pure TIME split, not regime-label-dependent, so it carries none of C3's contamination)*: placebo-clean IC **> 0 in both halves** of the sample (robustness.py convention). (c3) yearly breakdown *(GATES, unchanged — also a pure calendar-time split, regime-label-independent)*: placebo-clean IC **> 0 in ≥ 60% of calendar years** with ≥100 clean dates |
| (d) | Minimum sample floors | **n ≥ 600** pooled clean decision dates (≥10 effective blocks at block=60); **≥ 200 names** in a date's cross-section for that date to count, panel-average **≥ 500**; a per-regime cell with **< 150** dates is reported but can neither pass nor fail anything; VAL/QUAL admissible-timestamp coverage **≥ 60%** of the panel×date grid, else that family is INCONCLUSIVE-by-coverage (recorded, does not vote) |

**Why the bar is 0.02, higher than the large-cap 0.015 convention (rationale, frozen with
the number). Round-2 correction: the cost-conversion justification is REMOVED — it
double-penalized costs against gate (b)'s realized-cost accounting. Costs are now charged
exactly ONCE, in gate (b) (§5) only. The IC threshold itself is derived from a
minimum-economic-effect argument, independent of cost:**

1. **Minimum economically meaningful raw signal quality, not a cost-conversion.** Gate (a)'s
   role is to establish that the RAW cross-sectional signal is strong enough to be worth
   testing for deployability at all, before gate (b) separately answers "is it profitable
   after realized costs." Setting the bar meaningfully above the large-cap 0.015 convention
   (rather than at it) reflects that a down-cap panel with 3-5x the large-cap cost base (§3)
   needs a correspondingly larger raw edge to have any chance of surviving gate (b)'s realized-
   cost net-return test — this is a STRUCTURAL prior about what's worth testing further, not a
   pre-computed cost offset. The +0.005 uplift over the large-cap convention is retained as a
   round, legible margin reflecting this structural prior, but it no longer claims to be a
   precise IC-unit conversion of §3's cost buckets — that precise question is gate (b)'s job.
2. **The C3 lesson**: apparent IC on a new panel includes placebo structure of unmeasured
   size (C3's residual-momentum measurement found +0.0275 of its raw bull-cell IC was
   entirely explained by its own label-shift placebo — an empirical fact independent of C3's
   verdict-classification correction elsewhere in this session). The gate is already
   placebo-clean, but the down-cap panel's placebo geometry (different breadth, different
   regime mix) is unmeasured until the scan runs — margin, not optimism, is the correct prior.
3. **McLean–Pontiff decay** (cited): literature small-cap premia read at ~half strength
   post-publication; a bar that a decayed edge cannot clear is the point, not a defect.

**The formula-based IC-equivalent cost haircut from the prior round's cost-wedge calculation
is retained as a mandatory REPORT-ONLY diagnostic** (it remains informative context for how
much of gate (a)'s margin over 0.015 "corresponds to" a cost-equivalent reading) — it is
explicitly no longer part of the frozen threshold derivation and must not be re-added to
either gate's pass/fail logic.

**KILL vs MISS semantics (frozen):**

- **Decisive NO-GO (KILL of the down-cap leg)**: every family headline's one-sided 98.75% CI
  UPPER bound < 0.02 — the panel affirmatively cannot support the bet.
- **MISS**: no family clears (a)–(d) but the KILL condition doesn't fire — recorded and
  dropped per M-SIG design rule 5. No re-run on the same panel without a fresh amendment PR
  stating a materially new hypothesis. (Note: C3, the M-SIG stack's other candidate, does NOT
  currently exemplify this outcome — its round-2 correction found its substrate
  future-contaminated and reclassified its verdict to UNADJUDICATED, not MISS; a MISS requires
  a validly-run test that failed to clear the bar, which is a different claim than "the test
  itself is not currently valid.")
- **INCONCLUSIVE-by-coverage/size**: (d) unmet for a family/panel — recorded; does not vote;
  fixing the coverage (e.g., better fundamentals data) and re-running is NOT a re-pitch,
  because no verdict was rendered.
- **The D3 decision consumes the recorded verdict as-is**: GO ⇒ D3's down-cap option is live
  (staged-migration RFC per `#231` §1.5 L1 — a future, separate decision; M7 GO authorizes
  nothing by itself). NO-GO/MISS ⇒ D3 falls to new-data-only and P(G106) reads 0.35–0.40 per
  the `#231` M7 row. **Round-2 correction**: any result computed on the fallback panel (GO,
  NO-GO, or MISS alike) does NOT feed D3 under any circumstance — per §2's corrected symmetric
  restriction, the fallback panel's only role is pipeline feasibility/exploratory sensitivity.
  A fallback result's only consequence is to trigger procurement completion + re-measurement on
  the primary panel (§2); M7's own status while awaiting that primary-panel result is
  INCONCLUSIVE, not any of GO/NO-GO/MISS.

## 6. Procurement + build checklist for M7 kickoff

1. **Norgate (per RS-3 r2/r3 — trial/POC-first, NOT a firm purchase)**: Windows/VM + plugin
   POC proving the per-security/date constituency boolean and delisted-securities bars can
   feed panel construction; export/licensing review (extracted panel must be persistable in
   our own stores or Norgate cannot be the primary source); 3-week trial acceptance test with
   pass/fail = [R2000 membership-by-date retrievable 2014→present; delisted names' bars
   present; parquet export permitted; **delisting proceeds/recovery data available and
   joinable to the panel, or confirmed absent so §2's frozen fallback delisting-return
   convention applies instead (round-2 addition)**]; only then the fixed-term commitment
   ($346.50/6mo or $630/12mo, non-cancellable, verify live pricing at checkout). If the trial
   fails or slips past M7's early-Aug slot ⇒ the §2 fallback protocol governs (pipeline
   feasibility + exploratory sensitivity only; M7's verdict is INCONCLUSIVE, not decided, until
   the primary panel exists).
2. **Panel build script**: `scripts/build_downcap_panel.py` (this repo, alongside the
   committed scanners). Output: umbrella `data/exp/downcap/panel_<asof>.parquet` + manifest
   (membership-source hash, universe roster hash, floors/exclusions applied, code commit) per
   the `RenQuant#430` protected-path pattern. NEVER canonical prod paths; never the live tree.
3. **Scan runner**: `scripts/m7_downcap_scan.py` reusing sighunt/robustness/fundamentals_scan
   internals + the C3 label-shift placebo + block bootstrap. Evidence to
   `doc/research/evidence/<date>-m7-downcap/` (results JSON with per-date IC series
   sufficient to recompute every bootstrap, manifest with input SHA-256s — C3's evidence
   contract).
4. **The scan PR** cites THIS document's merged commit SHA, states primary-vs-fallback panel
   in its title, carries the §4 prospectivity affirmation, and reports the §5 verdict in the
   frozen vocabulary (GO / NO-GO-KILL / MISS / INCONCLUSIVE-by-coverage) with all seeds, all
   sensitivity cuts (ex-biotech, ±10bps costs, fwd_20d), and the mandatory diagnostics.
5. **Fallback-path build task** (only if triggered): refresh the stale broad local bars
   (ended 2026-05-08) into `data/exp/` — a build-time step, read-only against canonical
   stores.

## 7. Machine-readable preregistration artifact (round-2 addition)

**Round-2 correction: this document's prose freeze is not, by itself, a reliable freeze
mechanism.** A prose specification, however precise, can silently drift from what an eventual
implementation actually does — a future scan script could deviate from a frozen threshold, a
factor formula, or an admissibility rule without that deviation being visible at review time.
The actual freeze mechanism is:

`doc/research/evidence/2026-07-02-rs5-m7-prereg/prereg_contract.json` — a machine-readable
artifact committed alongside this document, encoding every frozen parameter from §§1-5 in a
structured, loadable form: universe construction and admissibility rules (§1-2), the cost
model (§3), factor formulas and the estimand/bootstrap/multiplicity specification (§4), and
the full verdict logic including the round-2 gate corrections (§5). Its top-level fields
mirror this document's section structure so a reader can cross-check prose against contract
directly.

**This artifact's merge commit is the demonstrable freeze point for prospectivity (§4).** The
eventual scan runner (`scripts/m7_downcap_scan.py`, §6 item 3) MUST load this file at startup
and validate its own configuration against every declared field — any parameter the runner is
about to execute that deviates from what's declared here must cause the runner to REFUSE to
run, not silently substitute the runner's own default. If a genuinely new parameter needs
freezing that this artifact doesn't yet cover, that is itself evidence the artifact is
incomplete and needs an amendment PR before the scan runs, per this document's own §"Binding
design rules" amendment-before-not-after discipline.

## 8. What this spec does NOT authorize

- No production change of any kind; no change to the strategy-104 trading universe.
- No capital deployment, no position, no sizing change — M7 is a read-only screen.
- No purchase: Norgate spend follows RS-3's trial-first gate and its own sign-off path; this
  document only specifies what the purchased data must support.
- No model retrain, no new signal in the serving path — a GO here feeds D3, which feeds a
  staged-migration RFC, each a separate reviewed decision.
- No writes outside experiment paths (`data/exp/…`, `doc/research/evidence/…`); no live-tree
  operations.
