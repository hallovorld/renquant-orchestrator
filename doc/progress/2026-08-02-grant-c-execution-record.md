# 2026-08-02 — Grant C execution record: momentum pipeline landed on the run surface

STATUS: complete (steps a–c executed and verified; step d armed on review; step e queued behind d)

WHAT: The operator-approved Grant C batch (orch#747, approved verbatim "做!") was
executed on the serving machine. This document is the CONTAINMENT-PROTOCOL (b)
durable record: exactly what changed, in order, with literal reverts. The
companion diff in this PR removes the two now-satisfied PENDING narrative
comments from `ops/launchd_manifest.json` (requirement (c): the reviewed
surface tracks reality in the same batch).

WHY/DIR: GOAL-7 slice 5 (model#195 architecture, model#197 build order). The
momentum TRAIN/TEST/TRADE pipeline was fully merged but dark; Grant C turns on
the weekly TRAIN job and publishes the first artifact so the s104 shadow entry
(s104#77) resolves at merge time. Shadow lane only — zero capital moves.

EVIDENCE:
- artifact: scratchpad `grant-c-step2.log` (full timestamped trail, 18:21–18:26Z);
  dated wrapper log `RenQuant/logs/rq104/momentum_train_2026-08-02.log`
- prod or exp: production run surface (umbrella + orchestrator-run + launchd),
  executed under the operator grant
- existing data: first momentum artifact
  `backtesting/renquant_104/artifacts/momentum/2026-08-02/momentum_residual_v0.json`
  (envelope `content_sha256 a824c480cd9c…`, 144/144 names) + genesis ledger row
  (`row_index 0`, `artifact_content_sha256 a824c480cd9c…`, `prev_row_sha null`)
- best-known?: yes — pins, job state, and artifact hashes all read back from the
  machine after each step, not asserted
- scope: run-surface landing only; no strategy behaviour change (shadow config
  merges separately as s104#77 = step d)

Steps as executed (all times 2026-08-02 UTC):

1. **(a) Pin advance** — RenQuant#551 MERGED 18:21:26Z (squash `557a4ad2`);
   codex approved; both designed CI gates answered in-PR (snapshot regenerated
   from s104 pin `3bfd5abc`; parity allowlist +`portfolio.py`
   +`walk_forward/leakage_guard.py` with provenance comments).
2. **(b) Machine sync** — umbrella: found stranded on branch
   `goal7/momentum-ledger-pointer-gate-rule` @ `28ab622a` (a #549-era leftover
   fully contained in origin/main; branch↔main delta = 4 files, none dirty);
   checked out `main`, ff-only pulled to `557a4ad2`.
   REVERT: `git -C RenQuant checkout goal7/momentum-ledger-pointer-gate-rule`.
   Runtime: `subrepo_assemble.py --sync --runtime-root .subrepo_runtime/repos`
   (canonical per umbrella Makefile:42) → 5/5 pins verified: model `e1f83f8c`,
   pipeline `60871e24`, s104 `3bfd5abc`, base-data `f8514066`, common `ef7726dd`.
   REVERT: restore previous lock (`fc1c50e9`'s copy) + re-run assemble.
   Post-sync `render_strategy_104_snapshot.py --check` on the live tree:
   **exit 0** (committed snapshot byte-matches the live render; no doctor alarm).
   Two misfires during the step, both corrected and logged in the same trail:
   (i) first assemble ran with the wrong `--runtime-root` level and created 9
   stray top-level clones — all verified porcelain-clean and minutes old, then
   removed; (ii) the runtime model clone was dirty with one machine-regenerated
   `README.md` (derived from `sim_runs.db`) — diff saved to scratchpad, then
   discarded to let assemble's designed dirty-refusal clear.
   orchestrator-run: ff-only pulled `2f014b8c` → `0e9aa266`.
   REVERT: `git -C renquant-orchestrator-run checkout 2f014b8c`.
3. **(c) Weekly job install + first artifact** — manifest preconditions
   verified (wrapper executable; pinned train CLI present), then plist copied
   to `~/Library/LaunchAgents/` and `launchctl bootstrap gui/502` at 18:26:12Z
   (Saturday 05:00 schedule).
   REVERT: `launchctl bootout gui/502/com.renquant.momentum-train-weekly &&
   rm ~/Library/LaunchAgents/com.renquant.momentum-train-weekly.plist`.
   Wrapper run once by hand: rc=0, dated log with terminal marker, artifact +
   genesis ledger row published (hashes above; artifact additive — no revert
   needed).
4. **(d) s104#77** — DO-NOT-MERGE banner replaced with the preconditions-met
   evidence block; codex approval requested; merge watcher armed (merges only
   on APPROVED + green CI).
5. **(e) queued** — second s104 pin advance after (d) merges, regenerating the
   snapshot with the momentum shadow kind.

Manifest change in this PR: the `_install_precondition_comment` and
`_pending_install_comment` keys under `com.renquant.momentum-train-weekly` are
deleted — both described a pre-install world that no longer exists (the job is
bootstrapped and its first dated evidence log exists). The entry itself, its
`evidence_glob`, schedule comment, and `program_args_sha256` are untouched, so
the daily drift scan now judges the job by its real firing evidence instead of
reporting `UNJUDGEABLE_NO_PLIST`.

NEXT: (d) merges on codex approval → step (e) pin advance (snapshot then
declares shadow kinds `['xgb','momentum_residual']`); Saturday 05:00 first
scheduled firing; the shadow sentinel picks up the momentum lane automatically;
step-5 cleanup of the s104-side `_2026_08_02_pending_first_artifact` narrative
key rides the step (e) PR.
