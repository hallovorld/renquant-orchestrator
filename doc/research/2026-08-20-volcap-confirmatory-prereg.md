# The 60% realized-vol cap — frozen SCREEN prereg (contaminated; shadow-only consequence)

STATUS: **frozen prereg (docs only — the run happens AFTER this merges AND the
committed runner is reviewed).** DATE: 2026-08-20.

**GRADE, stated first because it bounds everything below: this is a SCREEN run
with confirmatory discipline, NOT a clean confirmatory.** The formation swept
2016-2026 outcomes to choose the direction and the arm, and the primary window
lies inside that history; no untouched historical holdout exists. Consequences
are asymmetric to match (§4a): a FAIL closes the line, a PASS authorizes only a
never-submits shadow lane whose PROSPECTIVE record is the untouched evidence.
A production cap change is not on the table here.

## 1. Why this exists, and the exposure ledger first

The operator observed that the book "trades the same few names" and asked whether
something is wrong upstream. Measured on the live 2026-08-19 run:

```
watchlist 145 -> no_artifact -4 -> 113 candidates
  RealizedVolGateTask: dropped 29/113 over the 60% annualized cap (window=60d)
  -> 84 scored -> funnel candidates_final=84, buys=1
```

**26% of candidates are removed before the model scores anything**, and the
removed set is a coherent style bucket, not a random slice: `AMAT(88%)`,
`AMD(79%)`, `ANET(61%)`, `APP(78%)`, `COHR(113%)` and 24 more — semis / AI /
high-beta growth. The drop count has been rising: 24/108 (08-05), 26/111
(08-11), 29/113 (08-19).

**FORMATION DATA (exploratory, committed in this PR as
`doc/research/data/2026-08-20-volcap-formation/`):** equal-weight forward
returns of the KEPT pool at seven cap levels, on non-overlapping blocks of the
2016-2026 daily panel, PIT vol (60d, ×√252, returns up to and including t).
Numbers from that run, h=20, 129 fixed non-overlapping blocks:

| cap | mean fwd ret | ret / block-to-block sd |
|---|---|---|
| 40% | +0.0126 | +0.276 |
| 50% | +0.0140 | +0.290 |
| **60% (current)** | **+0.0151** | **+0.302** |
| 70% | +0.0165 | +0.314 |
| 80% | +0.0169 | +0.314 |
| 100% | +0.0175 | **+0.317** |
| no cap | +0.0175 | +0.312 |

Paired on the same blocks, 100% vs 60%: **+0.0023, t=+2.18, 74/129 positive**
(h=60: +0.0071, t=+2.04, 22/42). Both return and the risk-adjusted proxy
improve monotonically as the cap loosens toward ~100%.

**Why that is NOT enough to change a live cap, stated up front:** seven
thresholds were swept with no multiplicity control, on an estimand chosen after
looking; t≈2.1 under those conditions is a lead, not a result. And a first,
narrower read of the same data (kept-vs-dropped cohorts) appeared to say the
OPPOSITE — it compared two runs whose block sets differed, which is exactly the
kind of artefact a frozen rule exists to prevent.

## 2. The estimand must be the TRADED one, and the formation estimand is not

The formation measured the **equal-weight mean of the whole kept pool**. The book
does not buy the pool — it buys the panel's top decile. Widening the pool changes
which names are IN the top decile, so a pool-level improvement does not imply a
book-level one, and could even reverse (the added high-vol names may crowd out
better picks).

**FROZEN PRIMARY ESTIMAND**, stated as exact per-date arithmetic so it cannot
change character mid-corpus, and so the contrast is isolated to the cap and
nothing else [codex on orch#1017, rounds 1 and 2].

**Common, arm-independent objects — computed ONCE per date, BEFORE any cap is
applied, and reused byte-identically by both arms:**

- **U(d) = the COMMON PRE-CAP UNIVERSE** — every panel-usable name on date `d`,
  irrespective of vol. Both arms are subsets of it.
- **One score vector.** A single fitted model per refit date produces one score
  per name in `U(d)`. **The cap changes ELIGIBILITY ONLY** — never the fit,
  never the training sample, never the scores. If the fit moved with the arm,
  `B_cap100 − A_cap60` would be comparing two models, not one cap.
- **One DGTW benchmark.** The (vol × mom × beta) terciles and their
  self-excluded cell means are computed on `U(d)` and are the SAME numbers in
  both arms. They are NOT recomputed inside each capped pool — a benchmark that
  moves with the arm would confound the contrast with a change of yardstick.

**Per-arm, per-date statistic.** For arm `A` with cap `c_A`:

1. Eligible = `{ n in U(d) : vol60(n, d) <= c_A }`.
2. Top decile = the `ceil(0.10 * |Eligible|)` highest scores among Eligible;
   ties broken by ticker ascending.
3. `adj(n) = fwd60_excess(n) − cellmean(cell(n))`, the cell mean from `U(d)`,
   self-excluded, defined only where that cell holds ≥15 names in `U(d)`.
4. **statistic = mean(adj) over the top decile − mean(adj) over Eligible.**

**ADJUSTED-COVERAGE GUARD (fail-closed, arm-independent).** The instrument is
named "DGTW-adjusted", so it must actually be adjusted — in BOTH terms, not just
the numerator. A date is **DROPPED FROM BOTH ARMS** unless **≥80% of the names
in `U(d)` have a defined `adj`**. Because the guard reads `U(d)`, which is
computed before any cap, it is identical for both arms and cannot admit a date
into one and not the other, nor bias which names survive.

This replaces round 1's guard, which read only the top decile: the statistic
subtracts a whole-pool mean, so a date could pass on a clean numerator while the
denominator stayed an adjusted/raw mixture — the decisive quantity changing
character with nothing in the verdict rule noticing. Coverage over `U(d)`, the
per-date `|U(d)|`, and the dropped-date count are REPORTED with the verdict. If
fewer than the §4 minimum of complete blocks survive, the run is
**UNMEASURABLE** — neither PASS nor FAIL.

Two arms, identical in every other respect:

- **A_cap60** — candidates filtered at `vol60 > 0.60` (today's production rule)
- **B_cap100** — candidates filtered at `vol60 > 1.00`

Scores from the production recipe VERBATIM (artifact fingerprint `f8fb2259`,
172 features + norms + params, rank:pairwise), quarterly expanding refits with
the 60-trading-day embargo, fixed seed, no search — the reviewed refit engine
reused from the vol-switch runner (orch#1002/#1003 lineage), objective left AT
PRODUCTION. Cite-and-reuse, not rewrite.

**Why 100% and not the argmax of the sweep:** picking the sweep's best point is
the multiplicity error the sweep itself cannot escape. 100% is the endpoint of
the monotone trend and the weakest-assumption alternative ("cap essentially
off"); if the effect is real it must show there.

## 3. Frozen corpus, and an honest word about contamination

- **PRIMARY: 2017-01-03 .. 2023-09-29**, weekly cross-sections, h=60 labels —
  the same pre-exploration corpus the vol-switch line used, chosen so the
  geometry is already known and reviewed.
- **The formation sweep used 2016-2026, so it OVERLAPS this window, and that is
  fatal to any confirmatory claim.** A different function of the same outcome
  history is still the same outcome history: the sweep chose both the direction
  and the arm. What the frozen estimand, the two-point arms and the pre-fixed
  rule DO buy is protection against the remaining degrees of freedom — they stop
  the run being tuned after the fact. They do not manufacture error control that
  the data cannot supply. Hence §4a: FAIL closes, PASS only reaches a shadow
  lane, and the untouched evidence is prospective by construction.
- **SECONDARY (reported, never decisive): 2023-10-01 .. 2026-03-31**, the
  segment the formation's block set barely reaches at h=60.
- Universe: the production panel (292 tickers). Survivorship DECLARED and
  uncorrected; it plausibly flatters the high-vol arm specifically, since a
  name is likelier to leave the watchlist after a bad high-vol episode. So
  B_cap100 should be read as an upper bound.

## 4. Frozen decision rule (one shot; no re-runs; no threshold search)

Geometry counted BEFORE the rule, from the committed vol-switch formation
artifact: the primary corpus yields **28 complete non-overlapping 60-td blocks**
(the count orch#1007 measured on the identical grid).

- **P1 (primary, one-sided):** paired per-date `B_cap100 − A_cap60`, aggregated
  to those blocks, with **CI90 lower bound > 0** under BOTH Newey-West(1)
  block-t AND a stationary bootstrap (E[blk]=2, 10,000, seed 0). The bar is
  inherited verbatim from model#75's frozen rule — the same bar orch#1007 used.
  Disagreement between the two legs = FAIL.
- **Guards, fail-closed:** ≥15 complete blocks; ESS ≥ 6 after ρ̂₁; the
  winsorized ±0.50 SD paired difference must carry the same sign (anti-lottery,
  the column orch#1007's erratum showed matters); positive control = the
  unconditional primary-corpus spread must be positive before any arm is read.
- **Verdicts, pre-frozen:**
  - **P1 PASS** → authorizes ONE thing: a **`shadow_cap100` lane** (the standard
    never-submits lane pattern, own config, own sink) whose prospective record
    is what may later support a production change. **It does NOT authorize a
    production config change.**
  - **P1 FAIL** → the line CLOSES. The 60% cap stands, and the "it cuts all the
    AI names" observation is recorded as true-but-not-costly at the traded
    estimand.

### 4a. Why a PASS cannot authorize a production cap change [codex on orch#1017]

The first draft let P1 PASS authorize a live config PR. **That was wrong and is
withdrawn.** The formation swept 2016-2026 outcomes to choose BOTH the direction
(loosen) and the arm (100%), and the primary window sits inside that same
outcome history. Changing the estimand from pool-mean to top-decile DGTW does
**not** restore confirmatory error control when the same outcomes selected the
hypothesis — a different function of contaminated data is still contaminated.

There is no untouched historical holdout available: the sweep consumed the whole
panel. The only clean evidence is **prospective**. So the consequence chain is
staged, matching the vol-window precedent (#1003 confirmatory → #1004 shadow
lane → operator-gated activation on the lane's own record):

```
this prereg (contaminated, so: a SCREEN with confirmatory discipline)
  -> PASS: shadow_cap100 lane, never submits, logs would-be picks + outcomes
  -> the lane's PROSPECTIVE record is the untouched evidence
  -> only then a production cap proposal, operator-gated
```

A FAIL still closes the line, and that asymmetry is deliberate: contaminated
evidence can kill a hypothesis it cannot license.

## 5. What this deliberately does not test

Sizing. If high-vol names are admissible but should be smaller, that is a
different change with a different estimand, and conflating it here would make
a PASS unactionable. Also untested: any cap between 60% and 100%, and any
regime-conditional cap — both are searches, and this prereg buys exactly one
comparison.

## 6. Execution contract

Runner committed AND REVIEWED before the run (its own PR; byte-identity gate on
the reused definitions, one-shot marker, §4 guards as hard assertions, per-date
embargo assertion, block geometry recomputed and compared against §4's frozen
count). Results as their own PR: verdict first, block tables for both corpora,
the winsorized column, full provenance tags.
