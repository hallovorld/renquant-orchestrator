# 2026-08-02 — Grant C execution record: partial landing, step (c) REVERTED on review

STATUS: partial (steps a–b landed and verified; step c executed OUT OF ORDER at
18:26Z and REVERTED at 18:49Z per the codex review; steps c–e now blocked
behind three named gates)

WHAT: The operator-approved Grant C batch (orch#747, approved verbatim "做!")
was partially executed on the serving machine, then corrected. This document
is the CONTAINMENT-PROTOCOL (b) durable record: exactly what changed, in
order, with literal reverts — including the revert that was actually executed.

WHY/DIR: GOAL-7 slice 5 (model#195 architecture, model#197 build order). The
codex post-merge review of the batch (recorded on this PR and in the gate
issues below) corrected the order: three protections must merge with green
checks BEFORE the first-artifact/live-loader and s104#77 steps —
- renquant-pipeline#254: a certified momentum ledger that disappears before
  load must produce STATE_LOAD_FAILED, never ShadowNotYetPublished;
- RenQuant#550: the #549 ledger-pointer artifact-gate exception must be
  restricted to the momentum contract (any-`.jsonl`-plus-pending-key currently
  bypasses the identity gate);
- orchestrator#758: the shadow scorer sentinel must watch the momentum lane
  (and drop the retired PatchTST lane) before the lane can go dark silently.

EVIDENCE:
- artifact: scratchpad `grant-c-step2.log` (full timestamped trail 18:21–18:49Z
  including the revert); dated wrapper log
  `RenQuant/logs/rq104/momentum_train_2026-08-02.log`
- prod or exp: production run surface, executed under the operator grant;
  step (c) reverted under the codex review of this PR
- existing data: first momentum artifact
  `backtesting/renquant_104/artifacts/momentum/2026-08-02/momentum_residual_v0.json`
  (envelope `content_sha256 a824c480cd9c…`, 144/144 names) + genesis ledger row
  0 — left in place as additive data with ZERO consumers (s104#77 unmerged);
  noted for the re-run: the train CLI's artifact-exists refusal (exit 4) is
  date-scoped, so a future scheduled firing is unaffected
- best-known?: yes — every state below read back from the machine after each
  step, not asserted
- scope: run-surface landing + its revert; no strategy behaviour change

Steps as executed (all times 2026-08-02 UTC):

1. **(a) Pin advance — LANDED** — RenQuant#551 merged 18:21:26Z (squash
   `557a4ad2`); both designed CI gates answered in-PR (snapshot regenerated
   from s104 pin `3bfd5abc`; parity allowlist +`portfolio.py`
   +`walk_forward/leakage_guard.py` with provenance comments).
2. **(b) Machine sync — LANDED** — umbrella: found stranded on branch
   `goal7/momentum-ledger-pointer-gate-rule` @ `28ab622a` (a #549-era leftover
   fully contained in origin/main; branch↔main delta = 4 files, none dirty);
   checked out `main`, ff-only pulled to `557a4ad2`.
   REVERT: `git -C RenQuant checkout goal7/momentum-ledger-pointer-gate-rule`.
   Runtime: `subrepo_assemble.py --sync --runtime-root .subrepo_runtime/repos`
   (canonical per umbrella Makefile:42) → 5/5 pins verified: model `e1f83f8c`,
   pipeline `60871e24`, s104 `3bfd5abc`, base-data `f8514066`, common `ef7726dd`.
   REVERT: restore previous lock (`fc1c50e9`'s copy) + re-run assemble.
   Post-sync `render_strategy_104_snapshot.py --check` on the live tree:
   exit 0. Two misfires during the step, both corrected and logged in the same
   trail: (i) first assemble ran with the wrong `--runtime-root` level and
   created 9 stray top-level clones — verified porcelain-clean and minutes
   old, then removed; (ii) the runtime model clone was dirty with one
   machine-regenerated `README.md` (derived from `sim_runs.db`) — diff saved
   to scratchpad, then discarded to clear assemble's designed dirty-refusal.
   orchestrator-run: ff-only pulled `2f014b8c` → `0e9aa266`.
   REVERT: `git -C renquant-orchestrator-run checkout 2f014b8c`.
3. **(c) Weekly job — EXECUTED OUT OF ORDER, THEN REVERTED** — installed and
   bootstrapped 18:26:12Z; wrapper run once by hand (rc=0, artifact + genesis
   ledger row above). The codex review of this PR held the step against the
   corrected batch order (gates above still open), so the documented revert
   was executed at 18:49:12Z: `launchctl bootout
   gui/502/com.renquant.momentum-train-weekly` + plist removed; verified no
   longer loaded. The manifest/test PENDING_INSTALL markers are RESTORED
   UNTOUCHED in this PR (zero net diff vs main on those surfaces) and remain
   the designed reminder until the gates land.
4. **(d)/(e) BLOCKED** — s104#77 stays held (its auto-merge watcher was
   disarmed 18:49Z) and the second s104 pin advance stays queued until #254 +
   #550 + #758 merge green.

Also in this PR: `ops/renquant104/rq104_shadow_scorer_sentinel.py` fallback
contract gains `not_yet_published` — fallout of the LANDED step (a) pin
advance (pipeline#253's serving handler added the state); the sentinel imports
the producer at runtime so serving behaviour was already correct, only the
asserted-equal fallback literals lagged, caught by this PR's own CI.

NEXT: land #254 (agent-built PR incoming) + #758 (agent-built PR incoming) +
#550 (personal, the #549 gate design) → re-run step (c) exactly as documented
(install, bootstrap, verify; the existing artifact/ledger stay valid) → then
(d) s104#77 on approval → (e) second s104 pin advance + snapshot regen →
delete the PENDING markers in the same batch as the re-executed install.
