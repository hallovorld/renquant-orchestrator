# Design v4 — Short Capability, Minimal

**Status:** design / awaiting review (no code change)
**v4 rationale (self-audit):** v3.1 rebuilt, on the short side, the exact
pathology this account just recovered from on the long side: stacked
overlapping gates (the false-BEAR cascade: 5 filters → zero buys; the exit
pile-up: 4 rules → winners force-sold). v4 applies the lesson: **fewest
mechanisms that bound ruin; one owner per decision; add only on evidence.**
Mechanism count: v3.1 ≈ 30 → v4 = 8.

---

## 1. What shorting is for here (unchanged, evidence-ranked)

Insurance (Phase A) > efficiency (Phase B) > conviction shorts (shelved).
Basis: Drechsler & Drechsler; Muravyev et al. 2025 (ETB-universe single-name
short alpha ≈ 0, our E1 concurs); Clarke–de Silva–Thorley (efficiency);
Moreira–Muir / Faber (hedging). See the literature-review doc.

## 2. Phase A — Index hedge (the deliverable). 4 mechanisms, no more.

1. **Trigger (ONE):** `hard_bear` active (we already compute it, post-#112
   trend-gated). No second or third trigger in v1 — the vol-managed variant
   is an E6 sensitivity, adopted later only if the replay shows it clearly
   better.
2. **Position:** short SPY, notional = 0.5 · β_book · NAV (β = 60d OLS),
   capped by the ≤20%-NAV margin budget. One instrument, one h.
3. **Exit:** trigger clear for 2 consecutive sessions → unwind. (Inherent
   PDT safety: multi-day by construction.)
4. **Account breaker:** maintenance-margin utilization > 70% → unwind.

No hard stop, no profit lock, no event vetoes — a hedge losing money while
the long book gains is the product working. **Gate:** E6 replay on this
exact config (2022 bear, 2025-04 dip, dead window, full year; PASS = stress
MaxDD cut ≥ 25%, bull drag ≤ 2%/yr). Then config-gated implementation
(`risk.hedge.enabled`, default OFF) → 2-week paper shadow → operator go.

## 3. Phase B — Efficiency extension (110/10). 4 mechanisms.

1. **QP owns it:** allow a bounded negative sleeve (short leg ≤ 10% NAV,
   per-name ≤ 3%, ETB names only) with borrow cost (1%/yr) in the objective.
   Entries/exits/rotation are just QP rebalancing — no separate exit chain.
2. **Hard stop per short name:** +15% adverse → cover (the one ruin-bound).
3. **Earnings veto:** no short over earnings (±3d) — gap ruin-bound.
4. **Account breaker:** shared with Phase A.

**Gate:** E8 replay (with/without sleeve, identical inputs; PASS = net IR up,
MaxDD not worse, turnover ≤1.5×). Runs only after the long-side WF gate is
green — the sleeve finances longs, so the longs must be certified first.

## 4. Phase C — Conviction shorts: shelved, undesigned.

One sentence of policy, no machinery: **revisit only if E5 (short-interest
dynamics, post-FINRA-backfill) passes its pre-registered bar; design the
mechanism then, against that evidence.** Operator constraints recorded for
that future design: max 2 names, very high bar, default NO. (The v2/v3
17-mechanism chain is archived in git history, deliberately not carried.)

## 5. Experiments that remain

| Exp | What | When |
|---|---|---|
| **E6** | hedge replay of §2's exact config (+ vol-managed as sensitivity) | now |
| **E8** | 110/10 QP replay | after long-side gate green |
| **E5** | FINRA backfill → short-interest event study | after backfill |

E1 done (failed, archived). E2/E3/E4/E7 dropped — not deprioritized,
**dropped**; they can be reproposed only with a new evidence-based rationale.

## 6. Operator questions
1. Phase-A instrument: short SPY vs long SH? (recommend short SPY — no
   daily-reset drag; SH fallback if margin account is a blocker)
2. Margin budget: keep 20% or cut to 10% for v1? (recommend 10% for v1)
3. Short-term-gains tax on covers: acceptable? (hedge gains will be ST)
