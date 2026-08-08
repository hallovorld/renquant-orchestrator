# §10 confirmatory run — KILL. The 75/25 blend reverses sign out of sample.

The preregistered protocol (orch#912, frozen before the data existed) executed
with zero live choices. **Verdict: the primary fails three of four steps on the
governing row. Per §10.2: keep the panel alone. Per §1: that is a successful
outcome, and this record is the deliverable.**

## What ran

| element | value |
|---|---|
| panel arm | the bt#110 emitted WF replay matrix (point-in-time, 1685 dates, lane `wf_replay_panel`, run `wfreplay-2026-08-08`; config recorded on orch#905 before compute) |
| challenger arm | slow momentum (v0 252/21) Stage −1 replay raw scores |
| labels | `ticker_forward_returns.fwd_20d`, read-only |
| primary | `0.75·rank(panel) + 0.25·rank(slow)`, whole book, paired ΔIC vs panel alone |
| paired dates | **280** (∩ of replay panel, momentum replay, ≥30 common labelled names) |
| purge (§10.3 r2) | label-interval overlap vs the 33 hypothesis dates → **2 contaminated, 278 retained** (the replay ends 2026-05-07; the hypothesis window starts 2026-05-04) |

Derivation artifacts are IN THIS PR (the #911 review requirement):
`data/2026-08-08-s10-confirmatory-rows.csv` (280 rows: date, ic_p, ic_b, delta,
r_top3, contaminated) and `data/2026-08-08-s10-confirmatory-derivation.py`.

## The governed row (purged, n=278, n_eff=13.9)

| §10.2 step | frozen rule | measured | verdict |
|---|---|---|---|
| 1 measurability | `sd(Δ, ddof=1) <` re-derived bound `0.05·√n_eff/2.8` | 0.0558 vs 0.0666 | **PASS** |
| 2 effect | mean Δ > 0, adj t ≥ 2.0, block-bootstrap CI > 0 | **−0.0108**, t −0.72, CI [−0.0250, +0.0024] | **FAIL** |
| 3 economics | transfer clears AND meanΔ·β̂ > round trip | β̂ +3115 bps/IC (adj t **+3.17**, clears); implied **−33.7 bps** | **FAIL** |
| 4 level guard | mean IC_blend ≥ mean IC_panel | +0.0323 vs +0.0431 | **FAIL** |

Full-sample row (descriptive, 280 dates): same shape (−0.0101, all three fail).
`[VERIFIED — derivation script output, this session; reproducible from the
committed CSV for steps 1/2/4 and from the CSV's r_top3 column for step 3]`

## What this means

**The hypothesis was noise, and the machinery caught it.** On the 33-date
served overlap the blend showed mean Δ +0.0204 (t +0.50 — recorded as
undetectable at the time). On 278 point-in-time paired dates the sign
REVERSES: −0.0108. The diagnostic generated; the confirmatory killed; nothing
was retried at another weight — exactly the §10.2 "no substitutions" clause.

Two subsidiary findings, both useful beyond this kill:

1. **The transfer machinery is now validated at the frozen convention.**
   β̂ = +3115 bps of top-3 `fwd_20d` per 1.0 IC with adjusted t = +3.17 ≥ 2.0
   on 278 dates — IC on this book does move realised top-3 return. The §4.3
   gate that was NOT CLEARED at 33 dates clears at this depth. Any future
   challenger inherits a working economics gate.
2. **The replay panel is a stronger champion than the served sample
   suggested**: mean IC +0.0431 on these 278 dates vs +0.0223 on the 33
   served dates. A stronger champion is intrinsically harder to improve by
   blending — consistent with, though not proof of, the sign reversal.

## Status of the MoE line after this record

| branch | status |
|---|---|
| switching, whole-book & per-sector | dead (Stage −1, orch#911) |
| 75/25 slow blend (the §10 primary) | **KILLED by this run** |
| fast clock in a blend | dead (negative Δ, orch#911) |
| "rb" as a challenger | **not a model** — `rb_mom`'s components are panel+clf+slow-momentum `[VERIFIED — strategy_config.shadow_blend_rb_mom.json]`; there is no separate mean-reversion scorer to replay |
| clf (fwd60) | the one unexplored challenger; must follow §10.4's standing pattern (diagnostic → dated amendment → purged confirmatory) with horizon handling stated first |
| the panel | **remains champion everywhere — the §1 successful outcome** |

The served-matrix emitter (bt#110) and the frozen §10 machinery are the
durable assets: any future challenger now has a paved, preregistered path from
idea to verdict in one day.
