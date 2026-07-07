# Design: solve 104 / 105 cash drag with the right lever, in the right order

STATUS: design / RFC for cross-agent review. Docs only in this PR. No live behavior,
config, or capital-routing change ships here.
DATE: 2026-07-07
SCOPE: define the scientifically justified execution order for cash-drag work across
104 and 105, backed by measured evidence already on record. The goal is not to list every
possible knob; it is to stop solving the wrong problem first.

---

## 0. Executive decision

This RFC makes four decisions.

1. **104 primary fix = fractional shares.** The measured binding constraint is whole-share
   quantization on high-price names, not slot count.
2. **104 secondary fix = parking sleeve, but SGOV-first.** Residual idle cash should earn
   carry without silently turning the book into a benchmark-beta product.
3. **104 lane-A exposure knobs are downstream, not first.** `panel_buy_top_n`,
   `qp_cash_drag_lambda`, and similar levers should only be retested after the mechanical
   drag is removed. Otherwise we confound "more exposure" with "better plumbing."
4. **105 is NOT a live cash-drag implementation target yet.** 105 is still an
   operations-first, economics-unproven program. Forcing deployment before its economics are
   authorized would be cargo-cult optimization.

This narrows earlier cash-drag discussion into an execution order:

1. fix 104 sizing fidelity,
2. monetize residual idle cash conservatively,
3. then re-measure whether any exposure knobs still deserve to move,
4. and do not treat 105 as a production cash-deployment problem until 105 itself clears its
   own economics and rollout gates.

---

## 1. What the evidence already says

### 1.1 104 has a real cash-drag problem

Two independent records show that 104 is materially underdeployed:

- On **2026-06-29**, a real `daily-full` run deployed only **$827 of $8,730** buying power,
  with the live book sitting around **46% deployed / 54% cash**.
- The canonical KPI scorecard measured on **2026-07-02** from the latest canonical full run
  (**2026-07-01-live-01c54b39**) shows deployed fraction **0.2468**, trailing-5-session mean
  **0.2051**, and average cash weight **76.1%** across the last 10 canonical sessions.

So this is not a cosmetic issue. It is a first-order portfolio-efficiency problem.

### 1.2 The root cause is not "too few slots"

The most important evidence is the **2026-06-29 readonly 8/3 vs 10/4 replay** on the live
book:

- raising slots only added about **$427** of deployment,
- the marginal deployment went to **CVX + low-conviction ZM**,
- while **AVGO / BLK / GS** were selected but bought **0 shares** because their target
  notionals were below one whole share.

That is a clean diagnosis:

- the strategy wants some high-price names,
- the risk budget can afford their intended **dollar** exposure,
- but whole-share rounding turns those entries into zero,
- so the portfolio drifts toward lower-price names instead.

Later records are consistent with the same mechanism:

- **BLK** was blocked on **2026-07-01**,
- **BLK and AVGO** were blocked again on **2026-07-02**,
- the common reason was the same whole-share sizing failure (`size_insufficient_cash`).

This is not a "buy fewer names / buy more names" problem first. It is a **sizing fidelity**
problem first.

### 1.3 104 has a second problem after that: residual idle cash

Even perfect single-name sizing does not guarantee 100% deployment:

- reserves still exist,
- gates may still reject names,
- the book can still accumulate idle dollars between admissible opportunities.

That is what the parking sleeve is for. It addresses **residual idle cash**. It does **not**
fix the selection-by-share-price distortion above.

### 1.4 105 is not in the same state as 104

105 is not a mature live strategy with a proven edge that merely needs better capital usage.
The current 105 record says the opposite:

- the architecture RFC explicitly keeps **Stage 1 operations-only**, **default-OFF**, with a
  **frozen canary envelope** and **no expansion** without a separate authorizing decision;
- the same RFC records fractional shares as a **Stage-2 dependency, not a Stage-1 blocker**;
- the recommitted **2026-06-27 Phase -1 feasibility result** found measured net edge of
  **-6.4 bps at IC 0.03** and **-3.4 bps at IC 0.05** against an **11 bps** conservative
  round-trip cost, leading to the standing verdict: **soft NO-GO on intraday open->close
  directional alpha**.

So 105 has no legitimate "deploy more capital now" mandate. Its primary problem is still
"prove the economics and operating path," not "raise deployed fraction."

---

## 2. The theory: separate the three different things people call "cash drag"

The discussion has mixed three distinct mechanisms:

1. **Sizing-fidelity drag**: the strategy decides a name deserves `$X`, but whole-share
   rounding turns that into either `$0` or `>X`.
2. **Residual-idle-cash drag**: after all admissible single-name decisions, leftover cash
   sits uninvested.
3. **Exposure-policy drag**: the strategy is deliberately conservative because window size,
   penalties, or gates admit fewer dollars to active names.

These are not interchangeable.

### 2.1 Fractional shares fix (1), not (2) or (3)

Fractional shares are the right primary lever because they:

- remove zero-drop on high-price names,
- remove the one-share round-up overshoot of A-3,
- reduce selection bias toward cheap names,
- preserve the existing admission logic,
- and directly improve the realized-notional-vs-target-notional error.

They do **not** solve idle cash that remains after all single-name buys are done.

### 2.2 Parking sleeve fixes (2), not (1)

A sleeve turns otherwise idle cash into a conservative carry instrument.

It does **not** repair the fact that BLK/AVGO-class targets are currently getting rounded to
zero. A sleeve can coexist with bad single-name sizing. That is why it is second, not first.

### 2.3 Exposure knobs are about (3), and therefore must come later

Changing `panel_buy_top_n`, `qp_cash_drag_lambda`, or other exposure knobs before fixing (1)
and (2) creates bad attribution:

- if deployment rises, was it because plumbing improved or because we forced more exposure?
- if PnL changes, was it sizing fidelity, carry, or simply more capital pushed into a weak
  ranking?

For a strategy whose ranking quality is still under active scrutiny, that is not a clean
experiment. The right order is to remove **mechanical drag first**, then retest policy knobs
on the new baseline.

### 2.4 105 should not optimize deployment ahead of authorization

For 105, "cash drag" must be decomposed differently:

- before a live alpha path is authorized, undeployed cash is not necessarily a bug;
- it may be a deliberately conservative byproduct of an operations-only canary;
- forcing deployment early would convert an unproven research lane into accidental
  production exposure.

So for 105 the correct near-term goal is **measurement compatibility** with the 104 fixes,
not live cash deployment.

---

## 3. The actual plan

## 3.1 Phase 1: implement 104 fractional shares as the main fix

This is the first implementation wave after this design merges.

### Required cross-repo sequence

| Order | Repo | Change | Why it is required |
|---|---|---|---|
| 1 | `RenQuant` umbrella active path | preserve fractional fill quantities end-to-end on the real commit path; enforce capability gate before live emission; fail closed if fractional exposure would be unprotected | the historical blocker was not sizing math, it was that the active path still truncated / could not safely carry the lifecycle |
| 2 | `renquant-execution` | use the existing fractional validation / no-submit contract on the live broker path, not a parallel ad hoc path | prevents unsupported fractional orders from reaching the broker as accidental HTTP 400s |
| 3 | `renquant-pipeline` | wire the already-designed stage-2 fractional sizing path and ledger fields into the active runtime surface; keep default OFF | the sizing logic and tests already exist; the implementation task is active-path completion and verification |
| 4 | `renquant-strategy-104` | add the config block default-OFF, then enable only after the capability gate is proven and pinned | strategy config must never activate unsupported execution behavior |
| 5 | `renquant-orchestrator` | scorecard / monitoring additions for sizing-fidelity and unsupported-fractional failures | this repo should own the evidence loop and rollout visibility |

### What Phase 1 must prove

Fractional shares are not justified by PnL first. They are justified by **mechanical error
reduction** first.

Acceptance criteria:

- `size_insufficient_cash` for fractionable names falls to **0** on canonical full runs.
- median `abs(realized_notional_planned - target_notional) / target_notional` is **<= 1%**
  on fractionable entries.
- no residual fractional dust remains after a full sell / exit lifecycle.
- no unsupported fractional entry reaches the broker.
- no regression in stop protection, live-state accounting, or cash accounting.

### What we are explicitly NOT doing in Phase 1

- We are **not** leading with the one-share floor (A-3). It is now a fallback, not the main
  fix, because the measured overshoot can be huge and fractional shares solve the same entry
  problem without oversizing risk.
- We are **not** changing `top_n` or `qp_cash_drag_lambda` in the same wave.

---

## 3.2 Phase 2: implement a conservative parking sleeve for residual idle cash

Once Phase 1 is live or merge-ready, we implement the second lever: carry on residual idle
cash.

### Vehicle choice: SGOV first, not SPY first

The sleeve should go live as **SGOV-only first**.

Reason:

- the problem being solved here is idle-cash carry, not benchmark replication;
- SGOV improves carry without turning the book into a large implicit equity-beta position;
- SPY sleeve performance would be heavily confounded with market direction and could mask
  whether 104 alpha is actually working.

SPY or split sleeves are not banned forever. They simply require a separate explicit risk
decision because they change the portfolio's beta profile, not just its carry profile.

### First live sleeve contract

Recommended first live contract:

- `vehicle = SGOV`
- shadow first, live later
- sweep only cash above:
  - operational reserve,
  - pending order headroom,
  - and same-session planned equity buys
- sell sleeve first to fund admitted single-name buys
- no benchmark-beta claims

### Phase 2 acceptance criteria

- idle cash at close is reduced to the reserve band on canonical full runs,
- sweep/fund round trips reconcile cleanly,
- sleeve never blocks admitted single-name buys,
- no hidden leverage or buying-power contract violations,
- sleeve attribution is visible separately from alpha positions.

---

## 3.3 Phase 3: only then revisit 104 exposure-policy knobs

After fractional shares and the SGOV sleeve are both measured on a stable baseline, then and
only then revisit:

- `qp_cash_drag_lambda`
- `panel_buy_top_n`
- any remaining sizing-stack floors or de-throttling rules

At that point the experiment is much cleaner because:

- zero-drop is gone,
- residual idle cash has a separate owner,
- and any further deployment increase can be attributed to policy, not plumbing.

This phase should answer a narrower question:

> after removing mechanical drag, is the strategy still too conservative for good reasons,
> or just accidentally conservative?

That is a real experiment. Doing it earlier is not.

---

## 3.4 105 plan: compatibility and instrumentation, not live deployment

For 105, this RFC deliberately does **not** authorize a live cash-drag implementation wave.

Instead:

1. **Do not expand capital exposure for 105 on cash-drag grounds.**
2. **Do make 105 compatible with the 104 fractional / sleeve contracts** so 105 does not fork
   its own sizing or cash-handling semantics later.
3. **Do add measurement fields** when 105 work resumes, so its canary captures:
   - target notional,
   - realized notional,
   - whole-share zero-drop count,
   - residual idle cash at decision time,
   - and whether a candidate was fractionable.

That gives 105 a clean future decision surface without pretending today that the right answer
is "deploy more."

### Explicit 105 rule

No 105 live-capital expansion should be justified by deployment-efficiency arguments until both
of these are true:

- the 105 economics have a recorded authorizing decision,
- and the 105 rollout phase has advanced beyond operations-only canary status.

Until then, "cash drag" on 105 is primarily a measurement and architecture-prep question.

---

## 4. Why this order is the efficient one

This order is not just more correct. It is also faster.

- The fractional chain already has substantial design and test work across repos.
- The sleeve already has shadow code.
- The measurement for both already exists or is close.
- The most expensive mistake now would be spending another cycle on `top_n` / penalty knobs,
  then discovering we only papered over whole-share distortion.

The efficient path is:

1. finish the mechanical fix whose root cause is already measured,
2. add conservative carry for residual idle cash,
3. then re-open policy knobs from a less contaminated baseline.

---

## 5. Non-goals

This RFC does not authorize:

- a bundled "turn every cash-drag knob at once" rollout,
- a SPY-first sleeve rollout,
- a 105 deployment push before 105 economics are authorized,
- or a claim that higher deployment by itself implies higher expected value.

Those are exactly the shortcuts this design is trying to prevent.

---

## 6. Merge and implementation rule

After this design PR merges:

1. implementation starts with the 104 fractional chain,
2. sleeve work proceeds in parallel or immediately after, but SGOV-first,
3. lane-A exposure experiments stay blocked until the new baseline exists,
4. 105 receives compatibility / instrumentation work only unless a separate 105
   authorization artifact says otherwise.

That is the whole point of this RFC: not just to say "cash drag is bad," but to define the
only execution order that respects both the theory and the measured evidence.
