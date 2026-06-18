# SHORT-TERM STATE — current working memory (disposable; rewrite freely)

> Tier: **SHORT.** Non-binding. Rewrite each session; do not let it become a log.
> Truth tags required. If a line conflicts with `long-term-agreements.md`, this file
> is wrong. Last updated: 2026-06-17.

## Live tree integrity
Restored. The rawlabel overwrite + 82 gutted R4 calibrators were reverted to committed
state; only legitimate live-state files dirty. `[VERIFIED — git status + 473-line restore]`

## Model evidence on hand `[VERIFIED unless noted]`
- prod PatchTST `panel-transformer.json` (05-17, 60d): `oos_mean_ic = −0.0246`.
- fresh rebuilds today: 60d `−0.0227`, 20d `−0.0196` (20d = worst direction).
- **B2 pruned 60d: best_val_ic seed45 `+0.0239`, seed44 `+0.0040`** (only positive variant);
  earlier placebo ratio ~2.8 `[GUESS — not re-verified today]`.
- per-feature audit (recent slice): KEEP = STD/MIN/KLEN families; PRUNE =
  IMXD/CORR/RANK/RSV/IMAX/gross_profitability/sue_signal.

## Operational
- autonomous agent-pr-loop: **STOPPED**.
- live account ~$10.5k, hwm 11079.22.

## Next bounded action (checkpointed; promotion needs operator sign-off)
Evaluate **B2** (best existing PatchTST) through the WF gate — does its positive val IC
survive the placebo? — OR train one smart-pruned 60d variant from the audit keep/prune
list. Either is bounded with a clear done-condition.
