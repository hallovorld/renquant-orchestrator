# Main-Line Plan — **Get daily-full trading again, then raise win rate honestly**

**Date:** 2026-06-17 · **Owner:** orchestrator · **Supersedes** the scattered backlog
as the single source of truth for what we are actually driving.

> **True north:** daily-full puts on *real, gate-trusted* buys again — and once it
> trades, we raise the *live* win rate the honest way (selection, not curve-fitting).
> Everything here is ordered by **what actually unblocks live buys**, proven from
> the live DB, not from intuition.

## 0. The blocker, proven (not guessed)

Latest live run (2026-06-16), 4970 tickers, why no buys:

| block reason | count | meaning |
|---|---|---|
| **`no_model_signal`** | **3,920** | the active scorer emits no usable buy signal |
| `universe:no_artifact` | 315 | no scoring artifact |
| `universe:sharpe_*_below_0.5` | ~280 | hard 0.5 cutoff (rejects 0.492, 0.466 …) |
| `held_no_new_buy` | 70 | already held |

→ **0 candidates → 0 selected → 0 buys.** `buy_blocked=0`: it is *not* a flag; there
is simply no trusted model signal.

**Root cause (from `logs/weekly_wf_promote/`):** the weekly retrain→WF-gate→promote
pipeline has **FAILED every run since 2026-05-24** with:

> `WF result: manifest recipe mismatch … manifest artifacts do not match candidate
> recipe` → `VERDICT: FAIL — production unchanged.`

The WF gate is **correctly failing closed**: its historical WF manifest corpus does
not match the freshly-trained candidate's recipe, so it refuses to promote. No
promote → stale PatchTST (last `panel-transformer.json` = 2026-05-17, gated off) →
`no_model_signal`. **The gate is doing its job; the corpus/recipe parity is broken.**

This is the same class R4 (#384) addressed for the PatchTST manifest — but the weekly
promoter trains the **GBDT `panel-ltr.alpha158_fund`** path, whose manifest parity
must also be restored.

## 1. Main line (ordered by unblock value)

### 🔴 M1 — Restore the model-promote pipeline (THE critical path)
The only thing standing between us and live buys. Sub-tasks run concurrently:
- **M1a — Manifest⇄recipe parity for the production candidate.** Run `run_wf_gate.py`
  against a fresh candidate; read whether the manifest-parity + §5.2 sanity checks
  now pass post-R4. If the GBDT `alpha158_fund` path still mismatches, regenerate its
  WF manifest corpus with the matching recipe fingerprint (the R4 procedure).
- **M1b — 20d PatchTST candidate validation** (cheap falsification, *running now*):
  2 seeds × 2 disjoint OOS windows through the gate's own placebo method. Pass → a
  promotable candidate exists; fail → close the 20d line.
- **M1c — Fresh incumbent retrain** with `--val-days` (the stale-by-split-recipe fix)
  only if M1a/M1b don't already yield a gate-passing model.
- **M1d — Promote** whichever passes. **Operator sign-off required; never bypass the
  gate** (hard rule). Promotion is the one consequential step.

**Exit criterion for M1:** one model passes the full WF gate (WF 3-cut + §5.2 sanity)
and is promoted; `panel-transformer`/active scorer emits signals again.

### 🟠 M2 — Verify end-to-end buy flow
Once a model is live, confirm candidates actually become buys, i.e. the *secondary*
gates don't silently re-block: **RegimeModelAdmission** (`no_trade_stats:CHOPPY`) and
the **`universe:sharpe < 0.5`** cutoff (it currently rejects 0.492 — worth a look once
signals flow). Run a shadow daily-full and watch `n_buys > 0`.

### 🟡 M3 — Raise the win rate the honest way: meta-label *entry* filter
*After* M1/M2 (needs live trades). Today's 76% "win rate" is **backtest**; live is flat.
The legitimate lever is **selection**: extend the existing meta-label foundation
(#23/#24, `meta-label-exit.json`) from exit-only to an **entry** filter that only
greenlights high-P(win) setups. Trade fewer, better → higher precision *without*
curve-fitting exits. Judged on expectancy, not win rate alone.

### 🟢 M4 — Observability: live-only realized win-rate / P&L tracker
Parallel, cheap. The DB **commingles live and sim** trades (`source=None` on ~all
rows) — a data-integrity problem that makes "what is my real win rate?" unanswerable.
Build a clean **live-only** realized win-rate + expectancy + payoff report from
`LiveBroker`-sourced fills / `trade_evaluations`.

### 🔵 M5 — Safety: finish #26 intraday governor
Parallel, non-blocking. Primitive shipped (PR #390, flag-off, unwired). Remaining:
operator-chosen policy values + wiring into the intraday `SellOnlyPipeline` behind the
flag, shadow-validated. Matters once trading resumes.

## 2. Concurrency map (full speed)

| stream | task | blocks on | runs |
|---|---|---|---|
| **A (critical)** | M1a manifest⇄recipe parity / regen | — | now |
| **B** | M1b 20d validation | — | now (bg) |
| **C** | M4 live-only win-rate tracker | — | now (parallel) |
| **D** | M1c fresh retrain | A/B inconclusive | bg if needed |
| **E** | M3 meta-label entry filter (design→build) | M1/M2 trading | design now, build after |
| **F** | M5 #26 governor wiring | operator policy values | after sign-off |

Critical path = **A or B → M1d promote → M2 verify → live buys.** C/E/F parallelize
without touching the critical path.

## 3. Explicit non-goals (so we don't re-sprawl)
- **Multi-horizon sleeves: CLOSED** (PR #149 rejected — ITP pseudo-science at retail
  scale, wash-sale intractable, 5d×PatchTST mismatch, over-engineering for 0–1 sleeves).
  Reopen only per its narrow trigger. The only surviving thread is M1b (20d as a plain
  single-model swap).
- **No gate bypass, ever.** A model that can't pass the WF gate does not ship; the fix
  is corpus/recipe parity (M1a) or a better model, never `RQ_ALLOW_NO_WF`.
- **Win rate is not the target; expectancy is.** 65% win rate via tighter take-profits
  would *lower* expectancy — not pursued.
