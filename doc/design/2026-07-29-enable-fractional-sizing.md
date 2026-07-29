# CORRECTION + reframe: the fractional switches are deliberately off, not forgotten

**Status:** this document REPLACES its own first revision, which was wrong on
its central factual claim. Kept as a visible correction rather than a silent
overwrite.

---

## 0. What I got wrong, and how

The first revision said `execution.fractional_shares` was **"absent entirely"**
from the live config, and framed the situation as *deployed-but-dark by
omission* — somebody built it and nobody opted in.

**That was read from the wrong file.** `scripts/daily_104.sh:113` resolves the
production config from the PINNED subrepo:

```sh
if ! PROD_STRATEGY_CONFIG="$(renquant_strategy_config "$SUBREPO_ROOT" strategy_config.json)"; then
    ...
    PROD_STRATEGY_CONFIG="$REPO_DIR/backtesting/renquant_104/strategy_config.json"   # fallback only
```

I read the **fallback**, `backtesting/renquant_104/strategy_config.json`. The
authoritative file is
`.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
(pinned HEAD `8402a62`).

They differ on every key this proposal turns on `[VERIFIED — both files read
this session]`:

| key | PINNED (authoritative) | fallback (what I read) |
|---|---|---|
| `execution.fractional_shares` | **present**, `enabled: false`, `min_notional: 1.0`, `min_fractional_trade_notional: 25.0`, `non_fractionable_tickers: []` | `null` |
| `sizing.one_share_floor_enabled` | **present**, `false` | `null` |
| `ranking.kelly_sizing.fractional` | **0.3** | 0.5 |

## 1. Three consequences

**(a) The `fractional=0.30` "discrepancy" does not exist.** The pinned config
says `0.3` and the runtime logged `fractional=0.30`. They agree. The review
asked for this baseline to be resolved before proceeding; it is resolved, and
it dissolves rather than resolves — I was comparing the log against a file the
live run does not load.

**(b) `min_notional` is not TBD.** The pinned config already declares
`min_notional: 1.0` and `min_fractional_trade_notional: 25.0`. The review's
request to choose it is already answered by the config's own authors.

**(c) The framing was wrong, and the true state is more defensible.** The
pinned config's own `_comment` says why it is off:

> keep it DEFAULT OFF until the **active-path capability gate**, **broker
> guard**, and **sizing-fidelity evidence** are all proven. While disabled, 104
> stays on the safe whole-share + A-3 fallback path.

and its `_provenance` assigns ownership: strategy-104 owns the enablement bit,
execution owns broker validation, pipeline owns sizing math, orchestrator owns
scorecard monitoring.

The `sizing` block is equally deliberate: one-share floor OFF, with a comment
citing *"Pipeline: 3 codex review rounds, 20/20 tests"* and an explicit
**enablement contract** at
`strategy-104 doc/progress/2026-07-12-one-share-floor-enablement.md`.

**So this is not an oversight to correct. It is a documented default-off with
three named preconditions and an enablement contract that already exists.**

## 2. Therefore the question changes

Not *"why was this never turned on"* but:

> **Have the three preconditions been met — active-path capability gate,
> broker guard, sizing-fidelity evidence — and does the enablement contract's
> checklist pass?**

That is a question for `renquant-strategy-104`, which owns the bit and the
contract. Per the review's repo-placement finding, the proposal belongs there,
against that contract, not here.

## 3. What survives from the first revision

The measurement does. It is independent of which file declares what, because it
reads what the live run actually DID:

- 2026-07-27: 4 candidates cleared every gate, 2 orders, **$463 of $9,301**
  cash `[VERIFIED — logs/daily_104/2026-07-27.log]`
- size-zero skips: 07-02 (2), 07-10 (1), 07-13 (2), 07-27 (2), 07-28 (1)
  `[VERIFIED]`
- **bought median $160.59 (n=33) vs skipped median $764.28 (n=11) — a 4.76x
  price gap** `[VERIFIED / DERIVED]`, orchestrator#608

That last one is the substantive argument, and it is an argument about whether
the preconditions are *worth clearing*, not about whether someone forgot a flag.

## 4. Disposition of this PR

This orchestrator PR should NOT carry the enablement proposal. It is reduced to
this correction record. The proposal, measured against
`doc/progress/2026-07-12-one-share-floor-enablement.md`, belongs in
`renquant-strategy-104` and should cite orchestrator#608 for the evidence
rather than restate it.

## 5. The lesson worth keeping

I asserted a config key was absent across two PRs and a review cycle without
checking which config the live run loads. `daily_104.sh` names it on line 113.
The rule I already have — *check which artifact before claiming* — exists for
exactly this, and reading a fallback file that happens to be named plausibly is
how it gets skipped.
