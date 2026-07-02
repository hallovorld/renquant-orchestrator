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
- **C3 resolved as MISS today (2026-07-02, PR #249)** — regime-conditioned residual momentum,
  the first formally-voting M-SIG candidate, recorded a genuine, adequately-sampled miss
  (conditioned placebo-clean IC −0.0040 vs a +0.015 bar; 1,833 clean dates). The M-SIG stack
  now rides entirely on C4 (trend-scanning label, gated on S3) and C2 (quality, gated on the
  N3 coverage verdict) — G106 still requires 2 of 3 GO votes, and one of the three is already
  spent. **That raises D3's dependence on the down-cap leg**: if either C4 or C2 also misses,
  M7 is the largest remaining IC+BR upside in the plan (`#231` M7 row: NO-GO drops P(G106) to
  0.35–0.40). This spec exists so that when M7 runs (early Aug per RS-5's due date), its
  verdict is decision-grade rather than another retrospectively-argued number.
- **The C3 lesson binds this spec directly**: C3's raw bull-cell IC (+0.0253) looked
  promising and was ENTIRELY explained by its placebo (+0.0275). Overlapping-horizon label
  structure inflates apparent IC; a NEW panel (down-cap) has an UNMEASURED placebo structure.
  Every gate below is therefore stated on placebo-clean differences, and the headline IC bar
  is set ABOVE the large-cap 0.015 convention (see §5 rationale).

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
the vendor's delisted-securities coverage (Norgate Platinum, per RS-3). Delisting returns:
a name that delists inside a forward-return window contributes its last available price to
that window's return (a conservative simplification vs modeling delisting proceeds — stated;
CRSP-style delisting-return adjustment is out of MVP scope and its absence slightly FLATTERS
long-side factors, which the §5 bar's margin absorbs).

**Fallback if Norgate procurement slips** (RS-3 downgraded the purchase to trial/POC-first —
slip is a real possibility): build the panel from the EXISTING local daily-bar store
(umbrella `data/ohlcv/<T>/1d.parquet` — verified read-only this session: ~2,926 tickers
including small caps, e.g. ANDE/THRM with 2014-01→2026-05 history) filtered to CURRENT
Russell 2000 membership from a free current-day constituent list, same floors/exclusions as
§1. **The bias, documented now**: conditioning 2014–2026 measurement on 2026 survival
excludes delisted losers, which mechanically inflates momentum-, quality- and value-factor
ICs (the C3 doc §7 records the same direction on the 142-name panel). Therefore, on the
fallback panel:

- **Any positive result is an UPPER BOUND on the true panel's result.**
- **Only a NO-GO is decision-grade on the fallback** — if a factor cannot clear the frozen
  bar even WITH survivorship help, it is dead, and that verdict feeds D3 normally.
- **A fallback "GO" is NOT decision-grade and may NOT feed D3.** Its only permitted
  consequence is: complete the Norgate trial/purchase and RE-MEASURE on the
  constituency-by-date panel under this same spec (same thresholds — no re-freeze). This
  asymmetry is frozen; reporting a fallback GO as an M7 GO is a spec violation.

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

- **Bucket C deliberately EXCEEDS the plan's 25–40bps headline.** Rationale, stated plainly:
  a cost model frozen too LOW manufactures a false GO — the expensive error, since GO feeds
  D3 (a structural decision). Frozen too HIGH it can only cause a false NO-GO, the safe error
  direction under prereg (and D3's fallback, new-data-only, remains live). The published
  spread evidence for the $5–10M ADV tail does not support 40bps for spread-crossing
  execution, and POC-C confirms this pipeline's execution IS spread-crossing (fills at the
  open, +23–49bps/entry measured on LARGE caps — small caps will not be cheaper).
- No shorting-cost/borrow modeling in the MVP: the L/S construct in §5(b) is a measurement
  device, not a product; small-cap borrow is expensive and scarce (and the shorting mandate
  makes real shorts near-prohibited anyway). Instead §5(b) reports BOTH the L/S Sharpe (net,
  frozen costs, zero borrow fee — stated as optimistic on the short leg) AND the long-only
  top-decile-minus-benchmark variant as a diagnostic. Gating stays on the L/S number per the
  frozen rule; the long-only read is context for D3, not a gate.
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
  regime chain reconstruction (C3 doc §6's method + its stated fidelity limitations).
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
| MOM | `mom_12_1` | `mom_6_1`, `ma200_dist`, `pct_52w_high` | NULL on 104 universe (2026-06-28 scan; C3 MISS on the residual×regime cell) |
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

**Prospectivity:** the scan PR must include the C3-§8-style affirmation — no prior script in
this repo's history has computed these factor×down-cap-panel combinations — before its result
may be treated as confirmatory. (True today: every committed scan ran on the 104/142-name
large-cap watchlist.)

## 5. FROZEN GO/NO-GO thresholds for M7

**GO requires (a)+(b)+(c)+(d) simultaneously on at least ONE family headline, on the PRIMARY
(constituency-by-date) panel.** On the fallback panel only NO-GO is decision-grade (§2).

| # | Gate | Frozen value |
|---|---|---|
| (a) | Net-relevant placebo-clean IC | Pooled placebo-clean IC point estimate **≥ 0.02** on ≥1 family headline, AND that family's one-sided 98.75% (Bonferroni k=4) block-bootstrap CI lower bound **> 0**, on all three seeds {42,43,44} |
| (b) | Net long–short Sharpe | Decile L/S on the clearing headline, 60-session rebalance (3 staggered start offsets, averaged), costs charged per §3 buckets at realized turnover, zero borrow fee (stated optimistic): annualized net Sharpe **> 0.5** point estimate, with block-bootstrap CI lower bound **> 0**. (Requiring LB > 0.5 at ~10y of 60d periods is structurally unmeetable — stated honestly; the LB>0 leg guards sign, the point estimate carries the bar.) Long-only top-decile-minus-SPY net Sharpe reported as diagnostic, never gates |
| (c) | Regime robustness (not a single-regime artifact) | All three, point-estimate checks (per-regime cells are too small for corrected CIs — stated): (c1) placebo-clean IC with the largest regime cell (by date count) REMOVED stays **≥ 0.01** (half the bar) with unchanged sign; (c2) two-half stability: placebo-clean IC **> 0 in both halves** of the sample (robustness.py convention); (c3) yearly breakdown: placebo-clean IC **> 0 in ≥ 60% of calendar years** with ≥100 clean dates |
| (d) | Minimum sample floors | **n ≥ 600** pooled clean decision dates (≥10 effective blocks at block=60); **≥ 200 names** in a date's cross-section for that date to count, panel-average **≥ 500**; a per-regime cell with **< 150** dates is reported but can neither pass nor fail anything; VAL/QUAL admissible-timestamp coverage **≥ 60%** of the panel×date grid, else that family is INCONCLUSIVE-by-coverage (recorded, does not vote) |

**Why the bar is 0.02, higher than the large-cap 0.015 convention (rationale, frozen with
the number):**

1. **Costs**: §3's frozen round-trips (25–60bps per ~60-session holding) are 3–5× the
   large-cap cost base; converting cost to IC units via the decile-spread mapping
   (spread ≈ IC × σ_cs × 3.51; small-cap σ_cs(60d) ≈ 15–20%) prices the §3 model at roughly
   0.005–0.008 IC-equivalent — the +0.005 bar uplift is the cost wedge, kept legible as one
   round number rather than a panel-dependent formula. The formula-based IC-equivalent cost
   haircut at the realized bucket mix is a mandatory diagnostic in the report.
2. **The C3 lesson**: apparent IC on a new panel includes placebo structure of unmeasured
   size (C3: +0.0275 of "IC" was pure placebo). The gate is already placebo-clean, but the
   down-cap panel's placebo geometry (different breadth, different regime mix) is unmeasured
   until the scan runs — margin, not optimism, is the correct prior.
3. **McLean–Pontiff decay** (cited): literature small-cap premia read at ~half strength
   post-publication; a bar that a decayed edge cannot clear is the point, not a defect.

**KILL vs MISS semantics (frozen):**

- **Decisive NO-GO (KILL of the down-cap leg)**: every family headline's one-sided 98.75% CI
  UPPER bound < 0.02 — the panel affirmatively cannot support the bet.
- **MISS**: no family clears (a)–(d) but the KILL condition doesn't fire — recorded and
  dropped per M-SIG design rule 5, same as C3. No re-run on the same panel without a fresh
  amendment PR stating a materially new hypothesis.
- **INCONCLUSIVE-by-coverage/size**: (d) unmet for a family/panel — recorded; does not vote;
  fixing the coverage (e.g., better fundamentals data) and re-running is NOT a re-pitch,
  because no verdict was rendered.
- **The D3 decision consumes the recorded verdict as-is**: GO ⇒ D3's down-cap option is live
  (staged-migration RFC per `#231` §1.5 L1 — a future, separate decision; M7 GO authorizes
  nothing by itself). NO-GO/MISS ⇒ D3 falls to new-data-only and P(G106) reads 0.35–0.40 per
  the `#231` M7 row. A fallback-panel GO ⇒ procurement + re-measure only (§2).

## 6. Procurement + build checklist for M7 kickoff

1. **Norgate (per RS-3 r2/r3 — trial/POC-first, NOT a firm purchase)**: Windows/VM + plugin
   POC proving the per-security/date constituency boolean and delisted-securities bars can
   feed panel construction; export/licensing review (extracted panel must be persistable in
   our own stores or Norgate cannot be the primary source); 3-week trial acceptance test with
   pass/fail = [R2000 membership-by-date retrievable 2014→present; delisted names' bars
   present; parquet export permitted]; only then the fixed-term commitment ($346.50/6mo or
   $630/12mo, non-cancellable, verify live pricing at checkout). If the trial fails or slips
   past M7's early-Aug slot ⇒ the §2 fallback protocol governs.
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

## 7. What this spec does NOT authorize

- No production change of any kind; no change to the strategy-104 trading universe.
- No capital deployment, no position, no sizing change — M7 is a read-only screen.
- No purchase: Norgate spend follows RS-3's trial-first gate and its own sign-off path; this
  document only specifies what the purchased data must support.
- No model retrain, no new signal in the serving path — a GO here feeds D3, which feeds a
  staged-migration RFC, each a separate reviewed decision.
- No writes outside experiment paths (`data/exp/…`, `doc/research/evidence/…`); no live-tree
  operations.
