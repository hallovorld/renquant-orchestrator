# renquant105 milestone H2 — execution timing + intraday risk (104 book, execution-only)

2026-06-27. Part of the renquant105 suite (master: `…-intraday-system.md`).
**This is the H2 (execution-timing/risk) experiment — independent of H1 (intraday alpha).**
**No change to selection, no change to size, no new round-trips.** H2 measures whether
*when* and *how* the existing daily-104 book's already-decided trades are executed can be
improved, and adds an intraday protective-exit (risk) leg. An H1 stop (master §7 / M1) does
**not** block H2 — H2 is the defensible residual that stands on its own.

## Objective + scope
Reduce the **realized implementation shortfall (IS)** on 104's **existing order intents** by
choosing an intraday execution **timing policy**, versus the current behaviour (a next-open
market order). Strictly **execution-only**:
- The set of names and the position sizes are **taken as given** from the 104 decision —
  H2 never re-ranks, never re-sizes, never adds a name. Turnover delta vs baseline ≈ **0**.
- The only degree of freedom is *timing within the session* (and the marketable-limit band),
  on the **open→close** intraday horizon (overnight excluded — the close→open gap is not an
  H2 surface).
- A second, separable leg is **intraday risk management**: sell-only protective exits on
  intraday signal decay / stop, which create **no new buys** and map to the kill-state
  machine (exits ALLOWED under `NO_NEW_RISK`; master reliability §3.2).
Explicitly **out of scope:** any new alpha signal, any new entry the 104 book did not
already decide, any size change. H2 does **not** depend on M1; it depends only on the 104
order-intent + fill record and on arrival-price capture.

## Requirements
**Functional:**
- H2.1 **Per-order-intent data contract — DELIVERED BY H2.0, NOT by M2 (finding 2 — breaks the
  round-3 cycle).** For every 104 order intent, the **bar-timestamped, session-aware** record
  (`decision/arrival timestamp`, **arrival mid price** = NBBO mid at the decision instant, the
  104 **selection + size** given/immutable, the intraday **IEX bars over the execution window**,
  the **realized fill(s)**) and the IS module are produced by the **independent H2.0 milestone**
  (an M0/M0.5-class observability/TCA milestone — master §7.0 DAG + M0 doc), which runs
  **PARALLEL to M0 and does NOT depend on M1/M2-H1**. H2 therefore no longer waits on M2: the
  round-3 contradiction ("M2 is entered only if M1 passes" yet "H2 needs M2's IS module" yet "H2
  runs even if M1 kills H1") is resolved by moving capture into H2.0. All records are
  **event-time-contract bound** (finding 1: arrival/fill marked at `first_eligible_fill_ts`, not
  the closed bar). Overnight excluded; all timestamps via `live.clock` (reliability F38).
- H2.2 **Pre-registered timing-policy set (fixed BEFORE any run — no post-hoc selection).**
  Compare the **baseline = current 104 next-open market order** against a **small, frozen**
  set of timing policies applied to the **same** intents, e.g.: (a) **TWAP** over the first
  N minutes; (b) **marketable-limit at arrival ± band** (limit = NBBO ± cap bps, the F32
  slippage-band control); (c) **VWAP-tracking** over a fixed window; (d) **wait-for-spread-
  tighten** with a hard deadline then cross. The policy list, their parameters, the window,
  and the deadline are **pre-registered**; no policy is added or tuned after seeing results.
- H2.3 **Implementation-shortfall accounting with explicit opportunity cost (Perold).**
  `IS = (exec_price − arrival_mid)·side + delay_cost + opportunity_cost(unfilled)`. A limit
  policy that **misses or partially fills must be charged** the realized adverse move on the
  unfilled quantity to the session-close benchmark — otherwise timing looks free precisely
  when it failed. **Unfilled-handling rule (pre-registered):** an intent not filled by the
  policy deadline is marked-to the **session-close** price and the residual shortfall booked
  as opportunity cost; a partial fill books filled-IS on the filled qty + opportunity cost on
  the remainder. Fill rate and opportunity cost are first-class metrics, not footnotes.
- H2.4 **Paired-block inference + PRE-REGISTERED power/family-wise alpha — SINGULAR choices
  (finding 5, Codex round-4: ONE correction, ONE dependence model, fixed BEFORE data).**
  The **same** intent priced under each policy is a **matched pair**; analyse the **IS
  difference** (policy − baseline) per intent.
  - **ONE hierarchical dependence model (pinned, NOT a fallback choice):** the binding dependence
    is **the calendar trading session** (intraday + same-time-of-day autocorrelation clusters
    within a day, then sessions are treated as the independent block). The block IS the calendar
    session — **there is NO week-block alternative**. If the per-session sample is below the
    pre-registered min, the experiment is declared **UNDERPOWERED → do-not-run / re-scope** (the
    same M1 F1.7 fallback), **never** silently switched to a week block (round-4 #5: choosing the
    block after seeing the sample changes inference). Report a **block-bootstrap 95% CI on the
    mean IS difference** (Kunsch moving-block, session blocks) over **effective-independent
    observations**, not raw order counts.
  - **ONE family-wise multiple-comparison correction (PINNED — not "or"):** over the **K
    pre-registered timing policies** (TWAP / VWAP / marketable-limit / wait-for-spread), control
    FWER at **α_FWER = 0.05** by the **studentised max-statistic on the paired session-block
    bootstrap** — the single correction, fixed before any run (it respects the cross-policy
    correlation the bootstrap already carries). **Holm–Bonferroni is NOT used** (the round-3
    "Holm-Bonferroni OR studentised max" choice is removed; a policy "wins" only after this one
    haircut).
  - **Power against a minimum economically-meaningful IS improvement (PINNED):** powered
    (1−β = 0.80, α_FWER = 0.05) to detect a **≥ 2 bps per-intent** IS reduction (pinned — the
    smallest reduction worth changing execution for), using the paired-difference variance; the
    required effective-N per policy is pre-registered, with the M1 F1.7 underpowered fallback.
- H2.5 **Intraday risk-exit leg (sell-only, kill-state-aware).** Define explicit protective
  exits on intraday signal decay / σ-scaled stop for the existing book. These are **exits
  only** — they create no new positions and never re-enter. They map to `NO_NEW_RISK` /
  `CANCEL_OPEN_ORDERS` (master reliability §3.2): exits remain ALLOWED when buys are halted;
  `FULL_HALT` (broker/account-integrity only) is the sole state that also pauses exits.
- H2.6 **Counterfactual fills are NOT observable from bars + one factual fill — a CONSERVATIVE
  FILL MODEL is REQUIRED (finding 4, Codex round-3).** The per-intent record (NBBO arrival mid
  + IEX bars + the realized baseline fill) does **NOT** determine the counterfactual TWAP / VWAP
  / marketable-limit / wait-for-spread outcomes: it does not give **queue position**,
  **partial-fill probability**, the **executable NBBO path**, or **counterfactual market
  impact**. Opportunity-cost marking (H2.3) corrects one bias but does not make the
  counterfactual fills observable. Therefore H2 requires:
  - **Quote/trade-level replay + a conservative fill model.** Replay each candidate policy
    against the **quote/trade tape** (not just OHLC bars), with a fill model that is
    **queue-position aware** (a limit at the NBBO is filled only after the resting queue ahead
    clears), models **partial-fill probability**, walks the **executable NBBO path** (marketable
    limits cross to the executable side; passive limits depend on the touch), and charges a
    **conservative market-impact** term. "Conservative" = biased AGAINST the policy (lower fill
    rate / worse price than the optimistic mid) so a promotion is not a simulator artifact.
  - **Calibrate the fill model on randomized / paper shadow orders — NESTED SEPARATELY from
    policy evaluation (finding 5, Codex round-4).** Fit the queue/partial/impact parameters on
    **paper or randomized shadow orders** (zero live capital) placed across H1/H2-representative
    times and order shapes (the same zero-live-risk discipline as M0). **The probes/sessions used
    to FIT the fill-model parameters are a DISJOINT set from the intents/sessions used to EVALUATE
    a timing policy** — the same data must NEVER both calibrate the fills and score the policy
    (that double-uses the data and leaks the fill fit into the IS-difference). Concretely: the
    fill-model fit is an **inner nesting** (its own probe set / its own folds); policy evaluation
    runs on the **outer**, held-out intents only. This nesting is part of the pre-registration.
  - **Validate predicted fill/slippage OUT-OF-SAMPLE.** On **held-out** probes (disjoint from the
    fit set above), the model's predicted fill rate + realized slippage must match the measured
    outcomes within a bounded error (calibration slope ∈ [0.7, 1.3]) before the fill model is used
    in the comparison.
  - **Propagate fill-model UNCERTAINTY into the paired CI (H2.4).** The fill model's parameter
    uncertainty is carried through into the paired-block bootstrap (e.g. resample fill-model
    draws jointly with the block bootstrap), so the IS-difference CI reflects fill uncertainty,
    not just sampling noise.
  - **KILL/GUARD (gating):** if counterfactual fills are **not identified out-of-sample** (the
    fill model fails its OOS calibration, or its uncertainty makes the IS-difference CI lower
    bound ≤ 0), **H2 does NOT promote** any timing policy — promoting on an unvalidated fill
    model would be promoting a **simulator artifact**. Keep the baseline next-open execution.
**Non-functional:** reproducible; shadow-first (measured on 104's **real** intents in
replay/shadow before any live timing change); deseasonalized for the intraday U-shape;
all metrics **net of the M0-measured cost model**, never gross.

## Deliverables
The per-intent arrival/fill record + capture wiring (the **H2.0 implementation-shortfall
module** — owned by H2.0, consumed here AND by M2; finding 2); the **quote/trade-level replay +
the conservative, OOS-validated fill
model** (queue-position aware, partial-fill probability, executable-NBBO path, conservative
impact — H2.6) with its calibration/validation report; the frozen timing-policy replay harness;
the **IS-difference report** (per-policy paired-block mean + 95% CI **with fill-model uncertainty
propagated**, fill rate, opportunity cost, turnover delta) with the **family-wise-α multiplicity
correction**; the intraday protective-exit spec wired to the kill-state machine; a
go/keep-baseline recommendation per policy.

## Metrics / KPIs
| Metric | Definition | Direction |
|---|---|---|
| **IS reduction** | baseline IS − policy IS (bps), paired-block, CI-bounded | > 0 to promote |
| **Fill rate** | filled qty / intended qty under the policy | ≥ baseline − bound |
| **Effective spread paid** | realized half-spread vs quoted | lower is better |
| **Realized-vs-arrival slippage** | exec_price − arrival_mid (bps) | lower is better |
| **Opportunity cost (unfilled)** | adverse move on unfilled qty to session close (bps) | must not erase spread saving |
| **Turnover delta vs baseline** | round-trips added by H2 | ≈ **0** (hard — H2 adds none) |

## Acceptance / promotion / kill criteria (table)
*Sample bars are effective-independent observations (block scheme), not raw order counts.*
| Decision | Condition |
|---|---|
| **PROMOTE a timing policy** | paired-block 95% CI **lower bound > 0 bps IS improvement** vs next-open, **family-wise-α-corrected** across the K policies (H2.4); **AND** the **conservative fill model is OOS-validated** (H2.6) with its uncertainty propagated into the CI; **AND** turnover delta ≈ 0; **AND** fill rate not degraded beyond the pre-registered bound; **AND** opportunity cost does not erase the spread saving |
| **KEEP BASELINE / KILL** | no policy beats next-open after costs **and** opportunity cost (CI lower bound ≤ 0), **OR** the **fill model fails OOS calibration / counterfactual fills are not identified** (H2.6 — would promote a simulator artifact), **OR** a policy's unfilled opportunity cost erases its spread saving, **OR** fill-rate degradation breaches the bound → keep the current next-open execution |
| **Live gating** | a promoted policy is first proven in **shadow/replay on 104's real intents**; only then is a live timing change enabled, behind the same arming discipline + kill-state machine (a live change is itself gated, never a default) |
| **Risk-exit leg** | protective exits validated to fire on decay/stop without killing winners (decision-ledger killed-winner audit, reliability §4.3); exits ALLOWED under `NO_NEW_RISK` |

## Expected outcome (预期) + kill condition
A measured, paired-block verdict on whether intraday timing reduces IS on the **existing**
104 trades, plus a validated intraday protective-exit leg — both **independent of H1**. The
honest expectation is a **modest** IS reduction (a few bps) from spread/timing on the most
liquid names, with the marketable-limit + opportunity-cost discipline preventing the
"limit-that-misses looks free" trap. If **no** policy beats next-open after opportunity cost,
the correct outcome is **keep the baseline next-open execution** — that is a clean negative
result, not a failure. H2 ships zero new round-trips regardless.

## Dependencies / inputs
The 104 **order-intent + fill history**; **arrival-price capture + the IS module** (owned by
the **independent H2.0 milestone**, master §7.0 / M0 doc — the binding prerequisite, parallel to
M0, **NOT** owned by M2; finding 2); the decision ledger (`GateRegistry.persist()`, reliability
§4); `live.clock` for session math; the M0-measured cost model for net-of-cost accounting.
**No dependence on M1 / M2 / H1** — H2 depends only on H2.0 + M0 and can proceed even if H1 is
stopped (the DAG is acyclic; master §7.0).

## Risks (FMEA subset)
Arrival-price capture not yet built (the **H2.0** capture milestone is the long pole, not the
policies — but H2.0 is independent of M1/M2, finding 2); **counterfactual
fills not identifiable from bars + one factual fill (finding 4)** → promoting a **simulator
artifact** (mitigated by the H2.6 conservative, OOS-validated, queue/partial/impact fill model
with uncertainty propagated, and the no-promote-on-unvalidated-fills kill); **opportunity-cost
mis-accounting** making a missing-limit policy look free (mitigated by the H2.3 unfilled rule);
IEX off-NBBO / ghost prints contaminating the arrival mid (reliability F1/F5); fill-rate
degradation from over-patient limits (the deadline + cross rule bounds it); over-fitting the
policy window (mitigated by pre-registration + family-wise-α multiplicity correction); intraday
exits killing winners in benign regimes (the BULL_CALM panel-exit precedent — regime-gate per
reliability §4.3).

## Effort
~2–3 weeks once arrival-price capture (the **H2.0** IS module, finding 2) exists: the replay harness + the
paired-block analysis + the protective-exit spec. The data capture + the opportunity-cost
discipline, not the timing policies, are the work.

---
**H2 is the defensible residual deliverable:** if H1's UNDETERMINED prior (master §A) fails
to clear the measured bar in M1, H2 still delivers a clean, independently-validated
execution-timing + intraday-risk improvement on the existing 104 book — zero new round-trips,
no new alpha claim.
