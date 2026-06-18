# AGENT STATE — refer every session (short-term memory · mid-term plan · long-term agreements)

> The agent has **no persistent executive across turns** (see `AGENT-RETROSPECTIVE.md`
> §1). This file is that executive, externalised. Read it at the start of every
> session; update the **short-term** section as state changes; never silently
> contradict the **long-term agreements** — they are binding constraints, not notes.
> Tags: `[VERIFIED <how>]` = checked this against ground truth; `[GUESS]` = not.
> Last updated: 2026-06-17.

---

## A. LONG-TERM AGREEMENTS (binding; do not violate, do not re-litigate)

These are the operator's standing decisions/vetoes — the constraint ledger (C4).

1. **Never bypass the WF gate or branch protection.** A model that can't pass does not
   ship; fix the corpus/recipe or the model, never `RQ_ALLOW_NO_WF` / admin-merge.
2. **Production paths are read-only.** Never write `data/*.parquet`, `strategy_config.json`,
   live model artifacts, committed WF corpora, or anything the live tree's scheduled
   jobs consume. Experiments live in isolated clones/worktrees only.
3. **XGB / GBDT is VETOED as a pitch.** Do not propose switching to it. (It is recorded
   here only as a fact, not a recommendation.)
4. **PatchTST is the chosen model to make work.** The path is feature/architecture work
   (pruning the slow-drift family), NOT switching models.
5. **Report bottom-line-first** (template, `AGENT-RETROSPECTIVE.md` §4a); **no "X works/
   fails" without the §4b evidence block.**
6. **Every PR carries a `doc/progress/<date>-<slug>.md`** (§4c). No progress doc ⇒ reject.
7. **Never self-merge.** Design docs are not merged while under discussion.
8. **Docs/PRs/commits in English; chat in Chinese.**
9. **Never delete/empty the umbrella at `/Users/renhao/git/github/RenQuant`.**

## B. MID-TERM PLAN (the direction; where work is heading)

**North star:** daily-full trades again, driven by a model with genuine **positive real
cross-sectional IC** that passes the WF gate — then raise *live* return (payoff, not
hit-rate). Main-line plan = PR #150.

- **The binding problem = the model has no current edge.** PatchTST (prod + fresh
  rebuilds) has *negative* recent OOS IC; the gate correctly blocks it. This is the one
  thing standing between us and live buys. `[VERIFIED]`
- **The lever = feature pruning** (slow-drift family drives the placebo *and* drags IC
  negative). The pruned **B2** variant is the only one with positive val IC. Direction:
  find the feature subset with positive *aligned* IC **and** low placebo (per-feature
  audit, then retrain) — as a **bounded, checkpointed** task, not open-ended autonomy.
- **Machinery is ready:** the WF gate works end-to-end for PatchTST (config parity +
  manifest auto-match); a passing model promotes via the 3-key horizon contract. `[VERIFIED]`
- **Win-rate reality:** live hit-rate is already ~83%; the real lever is **payoff 0.89**
  (winners exited ~8d on a 60d strategy). Tool: PR #393. `[VERIFIED]`
- **Open PRs:** #150 (main-line plan), #393 (live win-rate tracker), #390 (intraday
  governor primitive, flag-off), #153 (this control contract). All await operator review.

## C. SHORT-TERM MEMORY (current state; update as it changes)

- **Live tree integrity:** restored. The rawlabel overwrite + 82 gutted R4 calibrators
  were reverted to committed state; only legitimate live-state files dirty. `[VERIFIED]`
- **Model evidence on hand** `[VERIFIED unless noted]`:
  - prod PatchTST `panel-transformer.json` (05-17, 60d): `oos_mean_ic = −0.0246`.
  - fresh rebuilds today: 60d `−0.0227`, 20d `−0.0196` (20d = worst direction).
  - **B2 pruned 60d: best_val_ic seed45 `+0.0239`, seed44 `+0.0040`** (the only positive);
    its placebo ratio was ~2.8 in earlier runs `[GUESS — not re-verified today]`.
  - per-feature audit (recent slice): KEEP signal-carriers = STD/MIN/KLEN families;
    PRUNE placebo-drivers = IMXD/CORR/RANK/RSV/IMAX/gross_profitability/sue_signal.
- **Loop:** the autonomous agent-pr-loop is STOPPED.
- **Next actionable (bounded):** evaluate **B2** (best existing PatchTST) through the WF
  gate — does its positive val IC survive the placebo? — OR train one smart-pruned 60d
  variant from the audit. Either is checkpointed; promotion needs operator sign-off.

---
*Maintenance: §A changes only on an explicit operator decision. §B tracks the roadmap.
§C is rewritten freely as work proceeds. If §C ever contradicts §A, §A wins and §C is wrong.*
