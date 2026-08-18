# Design: the vol-gated bull deployment window — shadow first

STATUS: **design for review (docs only — NO code / config / behavior change).**
DATE: 2026-08-18. Authorized by the CONFIRMED vol-switch verdict (#1003, prereg #1001):
"authorizes ONLY a design PR for a vol-gated bull deployment window (shadow/sizing-first,
operator-gated; no direct production change)". This is that PR, and nothing more.

## 1. Bottom line

When trailing market volatility is elevated, the panel's top-decile selection carries a
confirmed positive spread (+0.184/60d NW t=+1.95, bootstrap q05>0, ON−OFF t=+2.38, on
data the hypothesis never saw) `[VERIFIED — prior work, #1003 committed results §1:
ON mean +0.18400, NW t +1.952 (df 18), boot q05 +0.02096, P2 block-t +2.378]`; in calm
markets nothing is certifiable. Today the book sits ~half cash in ALL bull states
because the WF gate (rightly) refuses an unconditional bull license. The window turns
the confirmed conditional into a mechanism: **a vol-window buy license active only when
ON ∧ not-BEAR**, deployed as a SHADOW lane first, which itself accrues the
pre-committed activation evidence (≥20 ON-state live sessions with positive realized
spread) `[DERIVED — #1001 prereg §5: the PARTIAL branch pre-commits "activation burden
doubles (… ≥40 live shadow sessions in ON-state with positive realized spread)", which
fixes the CONFIRMED-branch base burden at ≥20]` before any operator ask. Out-of-window
behavior is byte-identical to today.

## 2. The window (frozen semantics from #1001/#1003 — no re-derivation)

- **ON at date d ⇔ SPY 20-trading-day realized vol (close-to-close, annualized √252) >
  0.135** — the CERTIFIED threshold, verbatim `[VERIFIED — prior work, #1001 prereg §2:
  the exploratory upper-tercile boundary (all-days T3 edge 0.1375 / bull-only 0.1348)
  frozen as the rounded constant; #1003 results §1 ran it as the decisive fixed
  definition]`. (The expanding-tercile variant FAILED certification and is prohibited
  as an activation key — recorded bound `[VERIFIED — prior work, #1003 results §3:
  NW t +1.533 < crit 1.734, boot q05 −0.01098, P2 block-t +0.790]`.)
- **Window = ON ∧ ¬BEAR**: the hard-BEAR override retains absolute precedence (the
  certified estimand included BEAR days, but deploying in BEAR is governed by G-B
  policy, not this design; the bull-only formation cut also cleared, t=+3.10, committed
  in the #1001 formation artifact `[VERIFIED — prior work, #1001 committed exploratory
  memo conditional_results.txt, BULL-ONLY section, spyvol20 T3_high y_z10 t=+3.10]`).
  The window can only ADD buy admissibility on
  ON∧¬BEAR days; it can never remove a protection, relax a cap, or touch the sell side.
- The window key is a raw PIT scalar — no regime-detector dependence; it survives the
  pending regime-repair program unchanged.

## 3. The mechanism (what changes inside the window; nothing changes outside)

Inside the window, the daily decision gains a **vol-window license**: the top-decile
(by served panel score) becomes buy-admissible under the EXISTING sizing/caps/tax/
wash-sale/QP machinery — i.e., the license substitutes only for the missing
regime-admission evidence, exactly the slot the WF gate's bull refusal leaves empty.
Everything downstream (Kelly/conviction sizing, per-name caps, cash floor, tax gates,
QP) applies unchanged. Outside the window: no license, today's behavior byte-identical.
Deliberately NOT in scope: sizing multipliers (the exploratory "size up in high vol"
idea stays deferred until the shadow record exists), sell-side changes, BEAR behavior,
any change to the WF gate itself.

## 4. Shadow-first rollout (the only implementation this design authorizes)

**Stage S (shadow lane, the deliverable):** a `shadow_vol_window` lane in the daily-full
— the standard lane pattern (own config, own sink, never submits) — running the EXACT
in-window mechanism: each session it logs window state (vol20 value, threshold verdict,
BEAR override), the would-be licensed top-decile, would-be orders after the full
downstream funnel, and (via the established readout pattern) realized forward outcomes.
Its ledger accrues the ACTIVATION EVIDENCE per the frozen burden: **≥20 ON-state
sessions with positive realized top-decile spread** `[DERIVED — #1001 prereg §5, base
of the doubled PARTIAL burden; see §1 tag]` (the survivor-free leg no backtest
can supply). ON-state sessions arrive only when the market provides them — the calendar
is not ours to choose; at current vol the lane may idle for weeks, which is correct
behavior, not a defect.
**Stage A (activation): OPERATOR-GATED, not part of this design's authorization.** When
the burden is met, a separate activation proposal presents the shadow record; the
operator decides. Until then the production book is untouched.

## 5. Acceptance criteria

- AC1: the lane config + license mechanism land behind the lane's own flag (default
  ON for the lane, which never submits); prod lanes byte-identical (test-proven).
- AC2: per-session ledger rows carry window state + would-be picks + funnel outcomes,
  hash-chained per the house ledger contract; scorer-identity monitoring covers the lane.
- AC3: the activation-evidence counter is computed by the ledger's own readout (the
  #213-style pattern). The counter implements the pre-committed burden — ≥20 ON-state
  sessions with positive realized top-decile spread `[DERIVED — #1001 prereg §5; see
  §1 tag]` — and its DECISIVE per-session readout is pinned to the CERTIFIED horizon:
  **realized h=60 top-decile spread**, matching the certification's estimand
  (`fwd_60d_excess` label, 60-trading-day blocks) `[VERIFIED — prior work, #1001
  prereg §3 (60-td blocks); #1003 results §8 pins (served-artifact label
  fwd_60d_excess, lookahead 60)]`. Each ledger row ALSO records the realized h=20 spread
  as a velocity diagnostic — earlier visibility, never decisive. Horizon-dependence is
  measured in this system, not hypothetical: `tail_q90_60d` passed all three screen
  criteria at h=20 (Δ +0.01154, block-t +1.586, 55.1% positive blocks) and failed
  decisively at the trained h=60 (Δ −0.00801, block-t −0.717) on the same corpus
  `[VERIFIED — prior work, #999 committed results §§1–2]`, so a 20-day readout cannot
  stand in for a 60-day certification; the counter must count the certified thing.
  Baseline deviation, declared: the certified construction benchmarks DGTW-adjusted
  spreads; the lane readout benchmarks vs the lane's own universe mean as an
  operational simplification. The activation ask must restate this deviation and show
  BOTH horizons; the counter remains an operational burden, not a statistical
  certification.
- AC4: a kill-switch env (lane-scoped) documented in the runbook.

## 6. Honesty ledger

- The certification is corpus-bound (survivor panel; fixed threshold; h=60 estimand
  `[VERIFIED — prior work, #1001 prereg §3 (60-td blocks); #1003 results §8 pins
  (label fwd_60d_excess, lookahead 60)]`).
  The shadow burden exists precisely because of that — activation evidence is live and
  survivor-free by construction.
- The certified ON mean is tail-driven: winsorizing at ±0.50 SD takes it from +0.1840
  to +0.0361 `[VERIFIED — prior work, #1003 results §1, P1 anti-lottery leg]`. A
  per-session counter over ~20 sessions is therefore variance-dominated by whether
  tail sessions land in the window — one more reason the counter is operational
  evidence toward an operator decision, never a re-certification.
- The counter's decisive readout is the certified h=60 horizon; h=20 is recorded but
  never decisive, because the two horizons are measured to disagree in this system
  (AC3's #999 citation).
- The window does NOT restore buying in calm bull (nothing certifiable there — the
  cash-in-calm posture the operator accepted stands).
- ON∧BEAR days are excluded from the license by policy precedence, though they were in
  the certified estimand — stated, not hidden; G-B owns that column.
- This design authorizes the SHADOW lane only. Activation is a separate operator
  decision with the pre-committed burden.

## 7. Plan

This design PR → codex approve → impl PRs: (1) lane config (strategy-104) + license
mechanism behind the lane flag (pipeline) with byte-identity tests for prod lanes;
(2) lane wiring in the daily-full + ledger/readout (orchestrator ops); each codex-gated;
deploys operator-gated as always.

## Corrections (review round 1, 2026-08-18)

- **AC3 estimand re-pinned.** The original AC3 froze an unsourced readout definition —
  realized h=20 spread vs universe mean — found in neither #1001 nor #1003 (codex MED 2)
  and at a horizon the certification never measured (identity-review comments on this
  PR). The decisive readout is now the certified h=60 horizon; h=20 is demoted to a
  non-decisive velocity diagnostic recorded in the same ledger rows; the universe-mean
  baseline is declared as an operational deviation from the certified DGTW-adjusted
  construction, to be restated in the activation ask.
- **Provenance tags added** to every restated number (codex MED 1, LONG row 10); the
  ≥20-session burden is tagged `[DERIVED]` because #1001 §5 states it only as the base
  of the doubled (≥40) PARTIAL burden.
- **§6 gained the tail-driven-variance bullet** (winsorized ON mean +0.0361 vs +0.1840
  raw) and the horizon-correspondence bullet.
