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
- H2.1 **Per-order-intent data contract (the prerequisite — capture is a GAP today).** For
  every 104 order intent, persist a **bar-timestamped, session-aware** record:
  `decision/arrival timestamp`, **arrival mid price** (NBBO mid at the decision instant),
  the 104 **selection + size** (given, immutable), the intraday **IEX bars over the
  execution window**, and the **realized fill(s)** (price, qty, time, partial flags). The
  metrics suite lists arrival/decision-price capture + the IS module as **not built today**
  — H2 cannot start until this record exists. Overnight is excluded; all timestamps route
  through `live.clock` (reliability F38).
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
- H2.4 **Paired-block inference (finding 6).** The **same** intent priced under each policy is
  a **matched pair**; analyse the **IS difference** (policy − baseline) per intent, blocked by
  **session (or week)** to respect intraday + same-time-of-day autocorrelation. Report a
  **block-bootstrap 95% CI on the mean IS difference** (Kunsch moving-block). The sample bar
  is in **effective-independent observations** (block scheme), **not** raw order counts.
  Apply a **multiplicity correction** across the pre-registered policy set (the comparison is
  over K policies, so deflate the per-policy significance accordingly).
- H2.5 **Intraday risk-exit leg (sell-only, kill-state-aware).** Define explicit protective
  exits on intraday signal decay / σ-scaled stop for the existing book. These are **exits
  only** — they create no new positions and never re-enter. They map to `NO_NEW_RISK` /
  `CANCEL_OPEN_ORDERS` (master reliability §3.2): exits remain ALLOWED when buys are halted;
  `FULL_HALT` (broker/account-integrity only) is the sole state that also pauses exits.
**Non-functional:** reproducible; shadow-first (measured on 104's **real** intents in
replay/shadow before any live timing change); deseasonalized for the intraday U-shape;
all metrics **net of the M0-measured cost model**, never gross.

## Deliverables
The per-intent arrival/fill record + capture wiring (the **M2 implementation-shortfall
module**, consumed here); the frozen timing-policy replay harness; the **IS-difference
report** (per-policy paired-block mean + 95% CI, fill rate, opportunity cost, turnover
delta) with the multiplicity correction; the intraday protective-exit spec wired to the
kill-state machine; a go/keep-baseline recommendation per policy.

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
| **PROMOTE a timing policy** | paired-block 95% CI **lower bound > 0 bps IS improvement** vs next-open, **multiplicity-corrected** across the policy set; **AND** turnover delta ≈ 0; **AND** fill rate not degraded beyond the pre-registered bound; **AND** opportunity cost does not erase the spread saving |
| **KEEP BASELINE / KILL** | no policy beats next-open after costs **and** opportunity cost (CI lower bound ≤ 0), **OR** a policy's unfilled opportunity cost erases its spread saving, **OR** fill-rate degradation breaches the bound → keep the current next-open execution |
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
The 104 **order-intent + fill history**; **arrival-price capture** (the M2 implementation-
shortfall module — the binding prerequisite); the decision ledger (`GateRegistry.persist()`,
reliability §4); `live.clock` for session math; the M0-measured cost model for net-of-cost
accounting. **No dependence on M1 / H1** — H2 runs on 104's existing intents and can proceed
even if H1 is stopped.

## Risks (FMEA subset)
Arrival-price capture not yet built (H2.1 is the long pole, not the policies); **opportunity-
cost mis-accounting** making a missing-limit policy look free (mitigated by the H2.3 unfilled
rule); IEX off-NBBO / ghost prints contaminating the arrival mid (reliability F1/F5); fill-
rate degradation from over-patient limits (the deadline + cross rule bounds it); over-fitting
the policy window (mitigated by pre-registration + multiplicity correction); intraday exits
killing winners in benign regimes (the BULL_CALM panel-exit precedent — regime-gate per
reliability §4.3).

## Effort
~2–3 weeks once arrival-price capture (the M2 IS module) exists: the replay harness + the
paired-block analysis + the protective-exit spec. The data capture + the opportunity-cost
discipline, not the timing policies, are the work.

---
**H2 is the defensible residual deliverable:** if H1's UNDETERMINED prior (master §A) fails
to clear the measured bar in M1, H2 still delivers a clean, independently-validated
execution-timing + intraday-risk improvement on the existing 104 book — zero new round-trips,
no new alpha claim.
