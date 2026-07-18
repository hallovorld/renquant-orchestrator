# Sentinel: LOUD small-n all-veto funnel rule (RFC pipeline#204 §2.3)

STATUS: delivered
WHAT: New check (e) in `ops/renquant104/rq104_degradation_sentinel.py` —
stage 4 of the approved VetoWeakBuys small-n guard rollout. Fires LOUD
when the latest live scan's buy funnel shows every scored candidate
vetoed by the rank floor (`veto:rank_score_below_floor` count ==
scored-candidate count > 0) at finite-scored n < N0_sentinel.
N0_sentinel = max(12, pinned `buy_floor_min_n` if valid per §2.2
[int in 2..30] else built-in 12) — read from the PINNED
renquant-strategy-104 runtime config (`RQ/.subrepo_runtime/repos/...`,
same resolution the run-surface drift scan uses), so the alarm never
goes quiet when the guard is absent, rejected, or deconfigured. Distinct
alarm key ("small-n all-veto funnel freeze"); never routes through the
launchd ack ledger, so historic acks cannot silence it.
WHY/DIR: GOAL-5 — the 2026-07-16/17 override sessions each produced an
n=5 scan where the self-referential mean+1σ floor exceeded the MAX
candidate score (all-veto by construction, ~1-in-5 per small-n session),
reading as a quiet no-trade day. Any recurrence must page.
EVIDENCE: 14 new module tests (AC-d synthetic fire / guard-valid fire /
normal-n 85-scored-67-vetoed quiet / deconfigured built-in-12 fire /
n=13 quiet, plus N0 resolution matrix, holding-only-run skip, legacy-DB
degrade, finite-n NULL exclusion); read-only replay against the live DB
fires on the real 2026-07-17 scan (5/5 vetoed, n=5, N0=12); full suite
4023 passed, 3 skipped, 0 failed (sentinel module: 36). [VERIFIED —
module tests + live-DB read-only replay + full `make test`]
NEXT: stage 5 = shadow-arm session with the pipeline guard active;
prune this rule's first real firing into the ops review cycle.
