# LONG-TERM AGREEMENTS — binding constraint ledger (C4)

> Tier: **LONG.** Changes **only on an explicit operator decision.** Codex review
> **rejects** any PR that violates an item here. On conflict, this file wins over
> mid/short-term memory. Reversals are recorded here, never silently dropped.

| # | agreement | since |
|---|---|---|
| 1 | **Never bypass the WF gate or branch protection.** A model that can't pass does not ship; fix the corpus/recipe or the model — never `RQ_ALLOW_NO_WF` / admin-merge. | standing |
| 2 | **Production paths are read-only.** Never write `data/*.parquet`, `strategy_config.json`, live model artifacts, committed WF corpora, `live_state.*` — or anything the live tree's scheduled jobs consume. Experiments live in isolated clones/worktrees only. | 2026-06-17 |
| 3 | ~~XGB / GBDT is VETOED as a pitch.~~ **SUPERSEDED 2026-06-21 by operator decision:** "把xgb模型回归prod，把正在开发的patchtst放到shadow … 用最新数据重训xgb … self audit … 如果通过的话，重新用xgb run daily full once to validate E2E." XGB is now the directed **production primary**; the veto is lifted. | 2026-06-17 → reversed 2026-06-21 |
| 4 | ~~PatchTST is the chosen model to make work.~~ **SUPERSEDED 2026-06-21:** PatchTST moves to **shadow** (still under development); XGB is prod primary (agreement #3). | 2026-06-17 → reversed 2026-06-21 |
| 5 | **Report bottom-line-first** (`AGENT-RETROSPECTIVE.md` §4a); **no "X works/fails" without the §4b evidence block.** | 2026-06-17 |
| 6 | **Every PR carries `doc/progress/<date>-<slug>.md`** (C5). No progress doc ⇒ Codex rejects. | 2026-06-17 |
| 7 | **Never self-merge.** Codex approval is the **mechanical** merge gate for Claude PRs — `.github/CODEOWNERS` + `require_code_owner_reviews=true` + `enforce_admins=true` (2026-06-19, #155) require the *other* agent's approval; admins can't override. Design docs are not merged while under discussion. | standing |
| 8 | **Docs/PRs/commits in English; chat in Chinese.** | standing |
| 9 | **Never delete/empty the umbrella** at `/Users/renhao/git/github/RenQuant`. | standing |

_Reversals: (none yet)._
