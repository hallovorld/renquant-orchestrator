# renquant105 — alpha-discovery plan (candidate table first, proportionate validation)

Status: **PROPOSAL** — 2026-06-28.

Reorganized around *finding* alpha, not vetoing it. Supersedes the closed
validation-heavy RFC #201 (which led with a CPCV/FWER/DSR framework before any
signal had been measured). The signal hunt already produced real numbers; this
doc transcribes and structures them.

Scan product shipped with this PR: `scripts/sighunt.py` (raw cross-sectional
rank-IC vs a within-date shuffle floor) and `scripts/robustness.py`
(Newey-West HAC t-stat + half-sample + yearly breakdown). Both are READ-ONLY:
no orders, no git, no canonical writes.

> **What this evidence IS — and is NOT.** This is a **current-watchlist,
> coverage-filtered, price-only RETROSPECTIVE DIAGNOSTIC**. It applies the
> *current* renquant-104 golden watchlist back to 2018 and keeps names by their
> *realized full-period* coverage. That is a **survivorship / look-ahead
> screen**: the universe is selected with knowledge of which names survived and
> stayed liquid through 2026, so it is biased *toward* names that did well. A
> true point-in-time eligible universe is not cheaply available here, so this
> diagnostic **cannot prove the absence of edge** — it can only say a signal
> failed to show a robust edge *under this biased screen*. Read every verdict
> below with that caveat.

---

## §1 Candidate alpha table — diagnostic measurement (read the caveat above)

Panel: 8-year daily, **2018-05-30 → 2026-06-26**, 134-name renquant-104 golden
watchlist (ETFs dropped, coverage > 0.55 — the *shared* threshold both scripts
use, recorded in `manifest.json`), non-overlapping forward windows,
split/dividend-adjusted Alpaca daily bars. **Survivorship-biased universe — see
the caveat above.** IC = cross-sectional Spearman rank-IC; t-stat on
**non-overlapping** windows (independent samples); net L/S = top-decile minus
bottom-decile per-rebalance return minus 11 bps round-trip cost; "× floor" =
|mean IC| ÷ placebo noise floor.

**Placebo noise floor** (200 within-date shuffles, |mean-IC| 95th-pct):
h5 = 0.0101, h20 = 0.0174, h60 = 0.0337. A signal must clear its horizon's
floor to be worth anything.

| signal | formula | horizon | mechanism | raw fields | exp. sign | mean IC | t | hit | net L/S | × floor | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **mom_12_1** | trailing 252d ret, skip last 21d | h5 | momentum / underreaction (Jegadeesh-Titman) | adj close | + | **+0.0274** | 1.88 | 0.575 | **+31 bps** | **2.73×** | **clears — but at h5 only; un-deflated t≈1.9** |
| mom_12_1 | (same) | h20 | (same, target horizon) | adj close | + | +0.0130 | 0.51 (NW≈0.95) | 0.557 | **+87 bps** | **0.74×** | **net L/S POSITIVE but IC FAILS the floor** (see note) |
| mom_6_1 | trailing 126d ret, skip last 21d | h5 | shorter-window momentum | adj close | + | +0.0180 | 1.29 | 0.552 | +22 bps | 1.79× | weak echo of 12-1 |
| ma200_dist | price / 200d SMA − 1 | h5 | trend / distance-from-mean | adj close | + | +0.0145 | 1.00 | 0.552 | +30 bps | 1.45× | weak |
| short_term_reversal | −1 × trailing 21d ret | h5 | 1-month reversal (Jegadeesh 1990) | adj close | + | +0.0055 | 0.44 | 0.485 | −43 bps | 0.55× | flat / wrong-sign at multi-day |
| pct_52w_high | price / trailing-252d high | h20 | 52w-high anchoring (George-Hwang) | adj close | + | −0.0216 | −0.78 | 0.455 | −124 bps | (wrong sign) | wrong sign on this universe |

**Note on the h20 mom_12_1 cell — do not collapse it into "broad failure."**
It is *not* a clean negative: its net top-decile-minus-bottom-decile L/S is
**positive (+87 bps after cost)**, but its rank-IC (+0.0130) **does not clear
the placebo IC floor (0.74×)** and its NW t ≈ 0.95. So the directional tilt is
not worthless — it just is not *statistically distinguishable from the shuffle
noise floor* on the IC metric under this diagnostic. Stated honestly: "positive
net L/S, IC not above floor," not "no signal."

**Momentum regime-flips sign yearly** (mom_12_1 yearly mean IC):
positive +0.046 / +0.046 / +0.031 / +0.173 in 2022 / 2023 / 2024 / 2026,
**negative** −0.064 / −0.065 / −0.028 in 2019 / 2021 / 2025. The edge is
conditional, not constant.

---

## §2 Verdict (scoped to THIS diagnostic)

These **five canonical price-trend factors did not show a robust unconditional
20/60d cross-sectional edge UNDER THIS diagnostic** (current-watchlist,
coverage-filtered, price-only, survivorship-biased — §1 caveat). This is **not**
a claim that "price-trend is exhausted" or that the universe has no edge in
general — a biased retrospective screen cannot establish that. mom_12_1 is the
only pulse: it clears the floor **only at h = 5** (short-term drift, borderline
un-deflated t ≈ 1.9), and at the target **h = 20** it has positive net L/S
(+87 bps) but an IC that does not clear the floor (0.74×, see the note above).

The apparent 5-year (2021–26) h20 momentum signal was a **bull-momentum REGIME
ARTIFACT under this screen**: the IC cleared the floor (1.24×) when fit on
2021–26, but fell to 0.74× the moment the panel was extended to the full 8
years. The lightweight screen — minutes of compute — caught this. That is the
evidence that proportionate validation is sufficient *for triage*: a heavyweight
CPCV/FWER/DSR rig was never needed to decide this signal does not warrant
further work right now.

---

## §2b Structural HYPOTHESIS (not a proven conclusion) — large-caps + price-trend

A **hypothesis** consistent with the published literature, *not* a conclusion
this diagnostic can prove: the universe is only **~134 liquid US large-caps**,
and cross-sectional price-trend anomalies (momentum / reversal) are documented to
be **weaker in large-caps** and to concentrate in smaller-cap and broader
universes. That is consistent with what we saw above, so a reasonable working
hypothesis is that this universe is a **comparatively inhospitable place to look
for cross-sectional PRICE alpha**. But this is a survivorship-biased,
price-only retrospective screen — it **cannot establish** that the price-trend
family is "exhausted." What we can honestly say is narrower: **two direct
diagnostic tests (the canonical-factor table §1/§2 and regime-conditioning §3
lead #1) did not surface a robust price-trend edge here.** On that basis — *not*
on a claim of proven exhaustion — we deprioritize further price-trend mining and
look first at a different, orthogonal family.

---

## §3 Forward leads — the discovery loop continues here

### Lead #1 — regime-conditioned momentum: **TESTED → NO.**

The hypothesis was that the yearly sign-flip means 12-1 is *conditional*, not
dead — gate the tilt on a regime that pays momentum and it stabilizes. Tested
directly with a PIT SPY trend×vol regime label over the 134-name 8y panel
(`scripts/regimemom.py`). It does **not** rescue the signal:

- **UP regime is just the unconditional average.** UP-trend covers 81% of
  history (~75-day runs); its fwd_20d IC is **0.0184, NW t 0.87** —
  indistinguishable from ALL (0.0188) and not significant. Conditioning on trend
  buys nothing.
- **Decisive cross-check: the yearly sign-flip SURVIVES inside UP-trend.** 2021
  was 100% UP-trend yet momentum IC = **−0.065** (the worst year of the panel);
  2025 was 83% UP and also negative. The trend regime therefore does **not**
  isolate the momentum-paying state — the flip is *orthogonal to trend*, so a
  trend gate cannot remove it.
- **The one live 20d cell is not usable.** UP_CALM shows IC 0.051 / +262 net bps,
  but (a) its NW t is **1.86** as 1 of ~7 cells with no multiplicity control →
  exploratory, not a finding, and (b) its mean run-length is **15.4 trading days
  < the 20-day holding horizon** — the regime turns over before the position
  matures, so you cannot hold the trade without whipsaw.
- Note: risk-management overlays (e.g. Barroso–Santa-Clara vol-scaling) *size*
  the momentum bet; they do not fix a sign-flipping cross-sectional IC.

### Lead — orthogonal signals (the live lead; different family)

We have **not found a robust price-trend edge here** (§2 / §3 lead #1 — *not* a
proof of exhaustion), and the Fundamental-Law breadth argument favors adding a
*low-correlation* source rather than mining the same family harder. On that
basis the next lead is **orthogonal signals** — analyst-estimate revisions /
earnings-surprise PEAD / fundamental quality. These are documented to work in
large-caps and are low-correlation to price-trend, so by the Fundamental Law of
Active Management orthogonal breadth is worth more even at low IC.
**Prerequisite, non-negotiable:** a cheap **point-in-time data audit** of the
FMP/analyst harvest first — publication timestamps, revision history,
coverage-by-date, lag, survivorship — *before any IC claim*. A naive non-PIT
analyst IC is self-deception.

---

## §4 Proportionate screen

Every candidate gets the **same cheap screen** the hunt used: raw
cross-sectional IC vs a within-date shuffle floor, plus regime / half-sample
stability, plus net-of-cost top-decile L/S. Only a candidate that survives this
cheaply — **stable across regimes and net-positive** — earns heavier
validation, and only then. We do **not** pre-build CPCV / FWER / DSR. This is a
solo agile project; validation is proportionate to it.

---

## §5 Reproduce the candidate table (one command)

The scan is pinned: pass an explicit `--as-of`, an explicit cache, and the
shared `--coverage` threshold. **No `datetime.now`.** When `--bars-cache` points
at an existing parquet and `--refresh` is omitted, the cache is read **without
instantiating the Alpaca client or requiring credentials**:

```bash
# regenerate the §1 candidate table (no credentials needed if the cache exists):
python scripts/sighunt.py \
    --as-of 2026-06-26 \
    --bars-cache /tmp/sighunt/bars.parquet \
    --out /tmp/sighunt \
    --coverage 0.55

# the robustness follow-up on the IDENTICAL panel (same --coverage; reuses
# manifest.json's kept_symbols so both scripts test the exact same cross-section):
python scripts/robustness.py \
    --as-of 2026-06-26 \
    --bars-cache /tmp/sighunt/bars.parquet \
    --out /tmp/sighunt \
    --coverage 0.55
```

**Output artifacts** (written to `--out`):
- `results.csv` — the ranked candidate table (the §1 numbers).
- `placebo_floor.json` — the per-horizon within-date shuffle noise floor.
- `manifest.json` — as-of, universe-config hash, bar-cache hash, the
  kept-symbol list + its hash, all parameters (coverage, horizons, cost,
  permutations, seed), and the code commit. Both scripts key off the same
  `coverage` so the panel is identical and auditable.

**External requirements to reproduce from a clean checkout:**
- **With the cache present** (`/tmp/sighunt/bars.parquet`, or any parquet you
  pass to `--bars-cache`): **no credentials** — the panel is read from the
  cache. This is the path the numbers above were transcribed from.
- **Without a cache** (first pull, or `--refresh`): requires
  `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` in the environment (READ-ONLY market
  data) and network access; the freshly pulled panel is then written to the
  cache path for subsequent credential-free reruns.
- The universe comes from the renquant-104 golden watchlist json (`--config`,
  default `backtesting/renquant_104/strategy_config.golden.json`); its hash is
  recorded in the manifest.

Reminder (§1 caveat): even reproduced exactly, this is a **survivorship-biased
retrospective diagnostic** and cannot prove the absence of edge.
