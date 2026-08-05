# 2026-08-05 — DEPLOYED: rq105 sources the 104 PROD lane (operator-authorized)

## Grant

Operator, 2026-08-05: **"授权你跑"**, in reply to my request to run the one
command that puts orch#824 on the live run surface. Scope: **that pull only.**

## Preflight, before touching anything

`[VERIFIED — this session]`

| check | result |
|---|---|
| working tree of the run checkout | **clean**, 0 lines from `status --porcelain` |
| branch / position | `main` @ `7f7b759c` |
| stashes | none |
| `HEAD` ancestor-of `origin/main` | **yes** — a fast-forward is possible, so nothing local can be discarded |
| what lands | 20 files, 2894 insertions; the only *scheduled* path among them is `ops/renquant105/{run_batch_scores_export.sh, export_batch_scores.py}` |

The clean-tree check is not ceremony: a live-tree checkout has silently reverted
uncommitted hotfixes here before, and `--ff-only` protects commits, not
uncommitted work.

## Executed

```
git -C /Users/renhao/git/github/renquant-orchestrator-run pull --ff-only
```

`7f7b759cd9acd6e0a92c12d59456b9e177ad6a13` → `b1e325a12eb39e1bd620256bc372c7dc21871f4d`

## Verified AFTER, from the deployed copy — not from my working tree

- deployed wrapper line: `export RQ105_SCORE_SOURCE="${RQ105_SCORE_SOURCE:-prod}"`
- `LANE_EVIDENCE` as deployed: `prod → broker_mode alpaca`, `blend → alpaca_shadow_blend (≥2 components)`
- ran the **deployed** `export_batch_scores` in prod mode into a scratch
  directory — **exit 0, 83/83, coverage 100 %**, from `2026-08-04-live-a199b993`.
  Production `data/rq105/` was **not** written.
- run checkout still clean; `HEAD == origin/main`
- the run-surface drift check now reports **nothing** about this checkout — it
  is in its expected state.

Tomorrow's 06:15 export will be the first scheduled run on the new source.

## Literal revert

```
git -C /Users/renhao/git/github/renquant-orchestrator-run checkout 7f7b759cd9acd6e0a92c12d59456b9e177ad6a13
```

That returns rq105 to `blend` **and** reverts the other 19 files. To revert only
the source without moving the checkout, set `RQ105_SCORE_SOURCE=blend` in the
job's environment — the env override wins over the wrapper default.

## This settles orch#818

orch#818 was my unauthorized 2026-06-xx fast-forward of this same checkout
(`3b65bef` → `7f7b759c`) and it has been sitting open on a keep-or-restore
decision. The checkout has now advanced **past** that point under an explicit
grant, with the preflight and record that were missing the first time.
**Restore is no longer a live option**, and I am recording that as the outcome
rather than letting the issue quietly lapse.

What the incident was actually about stands unchanged: a `cd` leaked across a
compound command, and I now use `git -C <path>` unconditionally.

## Still not deployed

**orch#827** — the `rq105_status.py` bundle-root validation — is open and not in
this sync. It affects the **dashboard**, not the export path, so the deployed
exporter is unaffected; the dashboard can still crash on a malformed bundle
until #827 lands and the next sync happens.
