# V6 verification — Phase −1 intraday-alpha soft NO-GO: UPHELD

S-REL audit item V6, STEP 2 (step 1 = the #267 durability recommit). Adversarial independent
recompute of the standing Phase −1 verdict
(`doc/research/2026-06-27-renquant105-phase-minus-1-results.md`): **σ_oc ≈ 152.5 bps std /
114–115 bps robust; net edge −6.4 bps @ IC 0.03 / −3.4 bps @ IC 0.05 vs the 11 bps
round-trip cost floor (breakeven σ_oc = cost/IC ≈ 367 / 220 bps) → soft NO-GO on intraday
open→close DIRECTIONAL alpha.** Merged plans rely on it (H2 non-goals, master-plan L3,
design-review amendment A4.2). Mandate: try to OVERTURN with fresh code on a different
substrate — NOT a rerun of their script.

**VERDICT: UPHELD.** Every load-bearing number reproduced (σ_oc to 0.01 bps, the algebra to
the rounding digit) from an independent implementation on the durable local bars; the
positive control proves the harness detects a decision-scale planted edge; the NO-GO is
robust across the plausible sensitivity region. One refinement, recorded precisely: under
maximal (live top-3) selection concentration the idealized flip boundary is **IC\* ≈ 0.031**
at the 11 bps cost floor — closer than the audit queue's "needs ~an order of magnitude"
framing (S-REL design §V6), though still strictly outside all evidenced territory (every
measured intraday IC to date is ≈ 0 / NULL). The reopening condition is sharpened
accordingly (§6).

| Load-bearing number | Theirs | Mine (independent) | Ruling |
|---|---|---|---|
| σ_oc std median (their window) | 152.5 bps | **152.51 bps** (n=1259 vs 1258) | reproduced |
| σ_oc robust MAD median | 114.0 bps | **114.00 bps** | reproduced |
| σ_oc robust IQR median | 115.1 bps | **115.1 bps** | reproduced |
| net edge @ IC 0.03 (σ 152.5, factor 1, cost 11) | −6.4 bps | **−6.42 bps** | reproduced |
| net edge @ IC 0.05 | −3.4 bps | **−3.38 bps** | reproduced |
| breakeven σ_oc @ IC 0.03 / 0.05 | 367 / 220 bps | **366.7 / 220.0 bps** | reproduced |
| breadth (valid names/session) | 142, all sessions | **142 on all 1259 dates** | reproduced |
| cost floor 11 bps conservative vs measured spread | ~6.2 bps RT | not re-measured (no quote substrate); floor logic verified conservative | stands, see §3 |

## 1. Method — independent, not a rerun (R1 protocol)

`scripts/v6_phase_minus_1_recompute.py` (this repo; sha256 in the evidence JSON). Shares no
code with `scripts/research_phase_minus_1_feasibility.py`:

- **Different substrate:** the durable local daily bars
  `/Users/renhao/git/github/RenQuant/data/ohlcv/<T>/1d.parquet` (open/close columns; through
  2026-07-02), NOT the Alpaca SIP API their run fetched. All 142 watchlist parquet files
  pinned by sha256 in
  `doc/research/evidence/2026-07-03-v6-phase-minus-1-recompute/verification.json`.
- **Different implementation:** own o→c validity filter, own quantile/MAD/IQR code
  (stdlib-only pure helpers, unit-tested), plus a winsorized-σ variant their script lacked
  (bad-print guard).
- **Universe:** the live pinned watchlist (142 names; live set == golden set verified by
  hash+set compare, same as their §1 claim). Every name has full bar coverage over their
  window — per-session breadth is 142 on every one of 1259 dates, matching their "all 142
  present" claim and implying set identity with the 2026-06-27-era universe.
- **Session-count boundary:** my window (2021-06-22..2026-06-26 inclusive) has 1259
  sessions vs their 1258 — a one-session fetch-boundary artifact (their 5y API window),
  immaterial at the 4th significant figure of the medians.
- Read-only throughout; no git anywhere near the umbrella tree; deliverables built in a
  fresh orchestrator worktree.

## 2. Check 1 — σ_oc: exact reproduction; window/universe sensitivity all hold

Primary (their window 2021-06-22..2026-06-27): **std median 152.51** (p25 130.2, p75 186.4,
mean 163.0, min 61.6, max 533.9), **MAD 114.00**, **IQR 115.1**, winsorized 151.9 — the
memo's row reproduces to 0.01 bps on every entry. Sensitivity:

| Window / universe | n dates | std median | MAD median |
|---|---|---|---|
| theirs (2021-06-22..2026-06-27) | 1259 | 152.5 | 114.0 |
| full history (2016-01-04..2026-07-02) | 2752 | 138.2 | 104.4 |
| last 8y | 2010 | 148.8 | 111.7 |
| last 3y | 753 | 149.3 | 111.3 |
| last 1y | 251 | 174.2 | 131.2 |
| today-5y (2021-07-03..2026-07-02) | 1254 | 152.7 | 114.5 |
| theirs, ex-ETF (134 names) | 1259 | 155.7 | 119.3 |
| theirs, full-coverage subset | 1259 | 152.5 | 114.0 |

No window or universe cut moves σ_oc anywhere near the 220–367 bps breakeven band — the
most favorable cut (last 1y, 174 bps) still leaves net edge negative at both anchors under
the frozen rule (0.05 × 174.2 − 11 = −2.3 bps). Longer windows are *lower*, not higher.
The measurement is not window-shopped.

**Substrate-independence caveat (honest):** the exact match implies the durable bars and
Alpaca's daily aggregates agree on the prints — this recompute is implementation- and
pipeline-independent, not vendor-triangulated; a shared-upstream bias in the official
open/close prints would not be caught here. Their 30-session causal check (09:35-ET entry,
minute bars) bounds that concern in the conservative direction (causal dispersion ~200 bps
> daily proxy), and was not re-run (no minute-bar substrate needed for this audit).

## 3. Check 2 — breakeven algebra and the cost proxy

Re-derived from first principles: per-trade expected gross edge = IC × σ_oc × factor
(Grinold conditional-expectation identity; factor = mean standardized score of the picks);
net = gross − round-trip cost; breakeven σ_oc = cost/(IC·factor); breakeven IC =
cost/(σ_oc·factor). The memo's §6 rows and 367/220 breakeven reproduce exactly (unit tests
pin them). The 11 bps cost floor is *conservative by construction*: their measured midday
median round-trip spread was ~6.2 bps and the floor keeps the documented prior that also
budgets impact/slippage. **Noted, not substituted:** real cost evidence now accumulates on
main — the S10 open-auction implementation-shortfall study
(`doc/research/2026-07-02-s10-open-auction-is.md`, fill-vs-VWAP with date-clustered CIs) and
the entry-timing shadow collectors. When those produce a measured round-trip cost, the
reopening inequality in §6 takes it directly; nothing here pre-empts it.

## 4. Check 3 — the IC premise (the adversarial angle, quantified)

The strongest overturn attempt is not σ or the algebra (both reproduce) but the **pinned
EDGE_FACTOR = 1.0**: it was conservative for the original GO question, but for the promoted
NO-GO it *understates* gross edge under concentrated selection. Monte Carlo order-statistic
ceilings for n=142 (200k trials, seeded): top-decile mean z ≈ **1.74**, top-3 mean z ≈
**2.34** (the live `panel_buy_top_n = 3` case), top-1 ≈ 2.63. Breakeven IC =
cost/(σ_oc·factor):

| factor \ cost | 11 bps | 22 bps | 40 bps |
|---|---|---|---|
| 1.0 (frozen rule), σ std 152.5 | **0.072** | 0.144 | 0.262 |
| top-decile ideal 1.74 | 0.041 | 0.083 | 0.150 |
| top-3 ideal ceiling 2.34 | **0.031** | 0.062 | 0.112 |
| 1.0, σ robust 114.0 | 0.096 | 0.193 | 0.351 |
| top-3 ceiling, σ robust | 0.041 | 0.083 | 0.150 |

So at the *idealized ceiling* (exact tail linearity of E[r|z], universe-median cost applied
to the three most extreme names), breakeven IC ≈ 0.031 — inside the memo's own 0.03–0.05
anchor band, i.e. the flip is NOT "an order of magnitude" away as the S-REL audit queue
phrased it. **Why this does not overturn:** (i) there is **no evidenced intraday o→c IC at
any level** — S9 Track-A conditional NULL, the 2026-06-28 minute-feature IC scan NULL, live
model IC ≈ 0; the 0.03–0.05 anchors were always hypothetical; (ii) the ceiling's two
assumptions fail conservatively in reality — empirical fractile payoff decays in the
extreme tail (effective factor < 2.34), and the 3 most extreme movers cost more than the
universe median (at 22 bps even the ceiling needs IC ≥ 0.062); (iii) at the robust σ the
entire grid at factor 1.0 is negative through IC 0.08. No plausible, let alone evidenced,
IC flips the verdict.

## 5. Check 4 — POSITIVE CONTROL: the harness detects a planted decision-scale edge

Planted **+30 bps** mean o→c on a seeded 30-name marked subset of the REAL 1259-date
cross-section; marker-indicator signal (noised, implied IC ≈ 0.063 — decision scale, not
10×); identical top-3/IC estimator on both arms; frozen detection rule (net > 0 AND gross
t ≥ 3):

| arm | gross (bps) | t | net vs 11 bps | mean IC | fires? |
|---|---|---|---|---|---|
| null (unplanted, noise signal) | +0.34 | +0.08 | −10.66 | +0.0016 | no (clean) |
| planted +30 bps | **+35.33** | **+8.74** | **+24.33** | +0.0632 | **yes** |

MDE(gross, t=3) ≈ 12.3 bps over 1259 dates. The mechanism-off arm (plant = 0) does not fire
(committed test). **PASS** — the NO-GO is not a blind-harness artifact (λ-round-1 class
excluded). Committed as a network/data-free pytest fixture
(`tests/test_v6_phase_minus_1_recompute.py`, 22 tests) per R2/AC4. The planted arm also
validates the §6 identity empirically: realized gross ≈ plant, and detection sits exactly
where IC × σ × factor − cost predicts.

## 6. Check 5 — sensitivity grid and the flip boundary (the reopening condition, precise)

Full grid σ {152.5 std, 114.0 robust} × factor {1.0, 1.74, 2.34} × cost {11, 22, 40} × IC
{0.01, 0.03, 0.05, 0.08}: **9 of 72 cells net-positive, all requiring IC ≥ 0.05 under
idealized concentration or IC = 0.08**; at the frozen rule (factor 1.0) the only positive
cell is (cost 11, IC 0.08, σ std) at +1.2 bps; at robust σ and factor 1.0 **zero** cells
are positive anywhere in the grid. The verdict is robust across the plausible region.

**Flip boundary (exact):** net > 0 ⟺ **IC × σ_oc × factor > cost_roundtrip**, i.e.
IC\* = cost/(σ_oc·factor). At measured σ_oc and the 11 bps floor: IC\* = **0.072** under
the frozen factor-1.0 rule; **0.041** at the top-decile ideal; **0.031** at the absolute
idealized top-3 ceiling (doubling with cost). **Reopening condition (R4, sharpened from
the #267 header):** a NEW frozen prereg presenting either (i) an evidenced, PIT-clean
intraday o→c IC ≥ 0.031 *together with* demonstrated tail linearity at top-3 concentration
and a measured concentrated round-trip cost ≤ 11 bps, or (ii) any evidenced (IC, cost,
factor) triple satisfying IC × σ_oc × factor > cost with σ_oc re-measured at that date.
Absent an evidenced IC, no cost improvement alone can reopen (at IC = 0 every cell is
−cost). This supersedes the looser "IC far above the 0.03–0.05 band" phrasing — the honest
bar is lower than that phrasing at maximal concentration, and higher than it at the frozen
rule.

## 7. Evidence boundary (R3)

- Daily-OHLC o→c proxy on the pinned 142-name universe; today's live set (== golden,
  verified) — era set-identity inferred from exact breadth/σ agreement, not from a frozen
  2026-06-27 universe snapshot (none exists on main; reconstructing it would require git in
  a primary checkout, which is forbidden).
- Substrate is pipeline-independent but plausibly vendor-shared with the original (§2
  caveat); the causal/minute-bar leg and the quote-spread leg were NOT re-measured.
- The concentration factors are idealized joint-normal ceilings (MC, seeded), used only to
  bound the flip boundary from the adversarial side — not as evidence any realizable
  strategy attains them.
- No intraday IC was measured here (none exists to measure); check 3 is conditional algebra
  on the anchors plus the standing NULLs.
- Survivorship: today's watchlist applied to the full history (same choice as the original;
  biases σ_oc slightly *down* if anything — delisted/volatile names excluded — which is
  conservative for the NO-GO's dispersion leg but anti-conservative for none of the
  conclusions, since higher σ_oc alone cannot flip the verdict without an evidenced IC).

## 8. Reproduce

```bash
/Users/renhao/git/github/RenQuant/.venv/bin/python \
  scripts/v6_phase_minus_1_recompute.py \
  --json doc/research/evidence/2026-07-03-v6-phase-minus-1-recompute/verification.json
python -m pytest tests/test_v6_phase_minus_1_recompute.py -q   # 22 network/data-free tests
```
