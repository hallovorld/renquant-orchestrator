# renquant105 Phase -1 — cheap, bounded, read-only feasibility (the FIRST gate)

2026-06-27. Part of the renquant105 suite (master: `…-intraday-system.md`).
**Status: EXECUTED — results in PR #199.** This is a **read-only, hard-time-capped** feasibility
probe that runs **BEFORE M0** and is wired as the **FIRST gate in the master DAG**. Its purpose is
to spend a few days of analyst time — not 10-17 weeks of build — to decide whether the full 105
stack is even worth standing up.

> ## ⛔ EXECUTED RESULT — STOP-for-ALPHA (net-edge gate), data-foundation GO (M0 dual-use)
> Phase -1 ran (PR #199, 142-name universe, 1258 sessions, read-only SIP/IEX, **no orders**). It
> measured σ_oc = **152.5 bps std / 114-115 bps robust** (causal event-time check 200.2 bps),
> breadth **142/session**, intraday coverage **142/142 (0% missing — REFUTES the "~50% no history"
> claim)**, cost band **~11 bps** (measured spread ~6 bps). Under the **CORRECTED net-edge gate**
> (this doc, "Stop/Go" below — NOT the original circular σ_oc-vs-its-own-prior gate, Codex round-4
> #2), the **measured net edge is NEGATIVE at plausible IC** (IC 0.03 → **−6.4 bps**, IC 0.05 →
> **−3.4 bps**; breakeven needs σ_oc ≥ 220 bps @ IC 0.05 / ≥ 367 bps @ IC 0.03). **⇒ STOP-for-
> ALPHA.** The literal "GO to M0" PR #199 printed came from the **original σ_oc ≥ 150 gate, which
> compared the estimate to its own assumed prior — a mis-specified gate**; that "GO" authorizes
> ONLY the **dual-use data foundation (M0)**, never tradable alpha. The H1 M1→M3 alpha stack is
> **PARKED** (master §0 banner). The active residual (M0 dual-use + H2 + safety) proceeds.

## Why this milestone exists (finding 9)
The full program (M0 → M0.5 → M1 → M2 → M3, plus H2) is **~10-17 weeks of work before any
credible alpha measurement**. Before committing that, we must spend a **bounded** amount of
effort to check that the cheap, decisive preconditions hold — using **ONLY existing historical
data already on disk** (no SIP purchase, no new ingestion, no model training, no orders). The
single most load-bearing assumption in §A is the open→close cross-sectional dispersion
`σ_oc ≈ 150-250 bps`, which the feasibility script currently **ASSUMES** (it is a PRIOR, not a
measurement). Phase -1 measures it (and three siblings) cheaply, so we do not build the full
stack on an unmeasured prior.

## Scope (hard boundaries)
- **Read-only.** Uses ONLY existing historical bars/fills already present (the parked intraday
  caches, the 104 fill history, daily bars). **No** new data subscription, **no** new ingestion
  cron, **no** model, **no** order (not even a paper order — this milestone places nothing).
- **Hard time/resource cap (PINNED):** **≤ 5 analyst-days of effort and ≤ 1 week wall-clock.**
  If the four measurements below cannot be produced within that cap on existing data, that is
  itself a STOP signal (the data foundation is not cheaply available → do not start M0).
- **No new claims of tradability.** Phase -1 produces *cheap measured bounds*, not the M1 GO
  estimand. A Phase -1 GO only means "the full stack is worth building"; it does **not** replace
  M1's frozen-policy replay.

## What Phase -1 measures — and what is NOT IDENTIFIABLE from existing data (finding 1)
**Identifiability boundary (Codex round-4 #1 — pinned).** Phase -1 uses ONLY parked OHLC caches,
old 104 fills, and daily bars. Three quantities the program cares about are **NOT identifiable**
from those inputs, and Phase -1 must NOT pretend to measure them:
- **Executable round-trip cost / fill dynamics are NOT identifiable from OHLC.** OHLC bars carry
  no executable bid/ask quote path, no queue position, no partial-fill probability; a single
  historical baseline fill does not identify a hypothetical intraday fill. ⇒ Phase -1 uses a
  **conservative cost BOUND** (quoted-spread-derived where a quote series exists, else a pinned
  conservative band), explicitly labelled a **bound, not a measured fill model**, and the GO test
  **keeps that cost uncertainty in the verdict** (it is charged at the conservative high end and
  the verdict is reported across the band, never at a single optimistic point). The calibrated
  stratified fill/cost model remains an **M0** deliverable; Phase -1 cannot produce it.
- **"≈4 independent bets/day" (N_eff) is NOT identifiable here** — it needs a signal/policy whose
  intraday + same-time-of-day dependence can be estimated, which Phase -1 (no model) does not
  have. ⇒ Phase -1 reports **raw breadth** (names clearing the liquidity floor with usable
  history) as an **upper bound on** effective breadth, explicitly NOT N_eff; the true N_eff is an
  M1 pre-registration output (M1 F1.7). (Measured raw breadth was 142; effective independent bets
  is strictly fewer and is NOT asserted by Phase -1.)

With that boundary fixed, Phase -1 measures (ONLY existing historical data):
1. **Basic intraday data availability.** On the existing parked caches: how many liquid large
   caps have usable intraday history, over what date span, at what NaN/gap rate. This is a
   *coverage census on data we already hold* — not the M0 point-in-time universe build.
   *(Measured: 142/142, 0% missing — REFUTES the design's "~50% no history" disable-cause.)*
2. **Causal open→close cross-sectional dispersion `σ_oc` (the number §A ASSUMES at 150-250 bps) —
   THE estimand that drives the net-edge gate.** Measure the realized cross-sectional std of
   **open→close** (overnight-excluded, session-aware) returns per session. Report the
   distribution (median, IQR, AND a robust estimator) across sessions, not a point value, AND a
   **causal event-time check** (entry at the first executable price after a hypothetical
   `first_eligible_fill_ts`) to confirm the dispersion is not an artifact of the opening cross.
   *(Measured: 152.5 bps std median / 114-115 bps robust; causal check 200.2 bps > daily 152.5, so
   σ_oc is NOT inflated by the open auction.)*
3. **Attainable RAW universe breadth (an upper bound on effective breadth — NOT N_eff).** The
   number of names that simultaneously clear a lagged-ADV liquidity floor AND have usable intraday
   history. This is the *headcount* that bounds the Fundamental-Law `√breadth` term from above; the
   actual N_eff (overlap-deflated) is an M1 output, not a Phase -1 measurement.
   *(Measured raw breadth: 142.)*
4. **Conservative executable-cost BOUND (a bound, not a fill model — see the identifiability
   boundary).** From the existing 104 fills + the quoted spreads in the historical bars, a *cheap
   conservative* round-trip cost band. This is a quick existing-data sanity **upper bound**, NOT
   the M0 calibrated stratified cost model. Purpose: charge the net-edge gate at a conservative
   cost and keep the uncertainty in the verdict. *(Measured: ~11 bps RT from ~6 bps spread — the
   GO test additionally stresses the conservative ~17 bps leg.)*

## Explicit stop/go criteria — a NET-EDGE gate with an uncertainty band (Codex round-4 #2)
**The original gate was circular and is REPLACED.** Round-4 #2: the prior "σ_oc median ≥ ~150 bps"
rule compared the estimate to its **own assumed prior** (the §A 150-bps lower edge) — passing it
told us only that the measurement landed near where §A guessed, NOT that a tradable edge exists.
"GO" out of that gate is therefore only a **data-foundation GO**, never an alpha GO. The decisive
gate is the **measured NET EDGE clearing cost with an explicit uncertainty band**, with every
term given an **exact definition, estimator, missing-data behavior, and a deterministic decision
function** (replacing the old `~30-40` / `~150` / `~4` / `~17` / "materially below" approximations).

### Exact definitions + estimators (no approximations)
- **`B` — raw breadth:** `B = | { names with a lagged-20d-ADV ≥ ADV_floor AND ≥ MIN_SESSIONS
  usable intraday sessions } |`. *Estimator:* count over existing caches. *Missing-data:* a name
  with < MIN_SESSIONS usable sessions is excluded from `B`. **`B` is an UPPER BOUND on effective
  breadth, not N_eff** (finding 1). *Pinned:* `ADV_floor = $50M/day`, `MIN_SESSIONS = 250`.
- **`σ_oc` — causal open→close cross-sectional dispersion (bps):** per session `s`, the
  cross-sectional standard deviation of the *causal* open→close return `r_{i,s}` (entry at the
  first executable price at/after a hypothetical `first_eligible_fill_ts`, exit at the close;
  overnight excluded). *Reported estimators (BOTH):* `σ_oc^std = median_s ( std_i r_{i,s} )` and a
  **robust** `σ_oc^rob = median_s ( 1.4826 · MAD_i r_{i,s} )`. *Missing-data:* a name without a
  valid open AND close on `s` is dropped from that session's cross-section; a session with < 10
  valid names is dropped from the median. **The gate uses the ROBUST estimator `σ_oc^rob`** (the
  conservative, fatter-tail-resistant choice), and reports the std estimator alongside.
- **`RT` — conservative round-trip cost BOUND (bps):** `RT = 2·(half_spread_q + slippage_floor +
  IEX_adverse_floor)`, where `half_spread_q` is the time-of-day-pooled quoted half-spread from the
  historical quote series (else the pinned conservative band). *This is a BOUND, not a fill model*
  (finding 1). *Pinned band:* charge the gate at **`RT_hi = 17 bps`** (the conservative leg) and
  report at `RT_base = 11 bps` so the cost uncertainty is carried into the verdict, never hidden.
- **`E_net(IC)` — measured net edge per top pick (bps), as a function of the assumed IC:**
  `E_net(IC) = IC · σ_oc^rob · factor − RT`, with `factor = 1.75` (top-decile truncated-normal
  conditional mean; the same prior multiplier §A uses, applied to the **measured** σ_oc). Evaluated
  on the **pinned IC grid** `IC ∈ {0.03, 0.05}` (the §A "optimistic" band) — **NOT** an IC fit by
  Phase -1 (Phase -1 has no model; IC is an assumed input swept over this grid). *Estimator:*
  closed-form from the measured `σ_oc^rob` and the cost bound. *Uncertainty band:* report
  `E_net` at `(σ_oc^rob, RT_hi)` AND at `(σ_oc^std, RT_base)` so the verdict spans the
  conservative-to-charitable corner.
- **`σ_oc^*(IC)` — breakeven dispersion:** `σ_oc^*(IC) = (k · RT) / (IC · factor)` with `k = 1.0`
  for break-even (and reported at the `k = 1.75` admission hurdle). The gate compares the
  **measured** `σ_oc^rob` against this **derived breakeven**, NOT against the §A assumed prior.

### Deterministic decision function (executed exactly — no post-hoc tuning)
```
data_foundation_ok  =  (B >= 30)                       # enough names to build M0 at all
                       and (coverage >= 0.95 on existing caches)
                       and (the four measurements completed within the <=5-day / <=1-week cap)

alpha_net_edge_ok   =  E_net(0.05) > 0  at the CONSERVATIVE corner (sigma_oc^rob, RT_hi)
                       # i.e. the measured robust dispersion clears the breakeven sigma_oc^*(0.05)
                       # even charged at the 17 bps cost leg, at the most optimistic plausible IC

decision:
  if not data_foundation_ok:        -> STOP (no buildable foundation)
  elif alpha_net_edge_ok:           -> GO  (data foundation AND a positive measured alpha edge)
  else:                             -> DATA-FOUNDATION GO / STOP-for-ALPHA
                                       (build M0 as DUAL-USE for H2 + a future un-park;
                                        DO NOT build the M1->M3 alpha stack — H1 alpha is PARKED)
```
The decision is a pure function of the measured `(B, coverage, σ_oc^rob, σ_oc^std, RT)` and the
pinned constants — there is **no free threshold chosen after seeing data**.

### Result of the executed run (PR #199), under the CORRECTED gate
`data_foundation_ok = TRUE` (B = 142, coverage = 142/142, completed in cap). But
`alpha_net_edge_ok = FALSE`: measured `σ_oc^rob ≈ 114-115 bps` (and `σ_oc^std ≈ 152.5`) is **below**
the breakeven `σ_oc^*(0.05) = 11/(0.05·1.75) ≈ 125.7 bps` at the base cost and far below the
`17/(0.05·1.75) ≈ 194 bps` (and `≈ 220 bps` at the k=1.75 hurdle) at the conservative leg; the
net edge is **negative at plausible IC** (IC 0.03 → −6.4 bps, IC 0.05 → −3.4 bps). ⇒ **DATA-
FOUNDATION GO / STOP-for-ALPHA.** This is exactly the outcome the corrected (non-circular) gate is
designed to surface, and it is consistent with PR #199's measured negative net edge. The original
σ_oc≥150 gate's "GO to M0" was the **data-foundation GO ONLY** — it never authorized tradable alpha.

**The binding stop rule:** if the available history's measured **net edge is non-positive at
plausible IC** (as here) **OR** it cannot satisfy the causal data contract (a non-look-ahead,
executable open→close return), **STOP building the H1 alpha stack.** Do NOT proceed to M1→M3 on
the assumption that M0/M1 will manufacture a dispersion the existing data already refutes. The
dual-use data foundation (M0) still proceeds for H2 + a reversible future un-park.

## Deliverables (DELIVERED — PR #199)
A short Phase -1 report: the intraday-coverage census (142/142), the **measured causal open→close
σ_oc distribution** (152.5 std / 114-115 robust / 200.2 causal, event-time-checked), the
raw-breadth count (142, an upper bound on N_eff — NOT N_eff), the conservative existing-data cost
bound (~11 bps), and the **deterministic decision-function output** against the corrected net-edge
gate above (**DATA-FOUNDATION GO / STOP-for-ALPHA**). Read-only analysis script + 18 network-free
tests + the research doc + a durable progress record (all in PR #199). No artifact any later
milestone depends on for correctness (M0 re-measures everything properly).

## Relationship to M0 / the DAG
Phase -1 is **upstream of M0** in the acyclic DAG (master §7): it is the **first gate**. Its
EXECUTED outcome is **DATA-FOUNDATION GO / STOP-for-ALPHA**: the **dual-use M0 data foundation
proceeds** (it serves H2 execution-timing AND a reversible future un-park), while the **H1 M1→M3
alpha stack is PARKED** (master §0 banner) because the measured net edge is negative at plausible
IC. A Phase -1 alpha-GO would have authorized M1→M3; this run did not clear the net-edge gate, so
it authorizes M0 (the proper point-in-time universe build + calibrated stratified cost model) **for
H2/dual-use only**. Phase -1 does **not** authorize any cross-repo topology change (that is the
umbrella ADR, finding 8) and creates no new pinned repo.

## Effort
**≤ 5 analyst-days, ≤ 1 week wall-clock (hard cap).** Read-only analysis on existing data only.
If it costs more than that, the answer is STOP.
