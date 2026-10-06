# 2026-10-05 — review queue: a head this agent already reviewed is never re-queued (codex approved s104#107 22×)

STATUS:   delivered, awaiting review — zero reviews at head.
WHAT:     `agent_workflows.build_queue(workflow="review")` now skips a PR when
          this agent has an effective review of EITHER verdict on the current
          head (`has_head_review_from_agent`), not only after a
          CHANGES_REQUESTED. A new head re-opens review as before. One new
          predicate, one call-site change, one regression test.
WHY/DIR:  root cause of the reviewer-quota burn. A PR that is approved but
          carries a contract finding (e.g. a production-path write that the
          merge workflow refuses by design) is "approved and not clean", so
          `peer_approved and not findings` did not skip it and no
          CHANGES_REQUESTED existed to skip it either → the reviewer was
          dispatched at the same head every cycle. The finding is the
          author's (fix workflow), not the reviewer's.
EVIDENCE: see §4(b) below.
  artifact:      src/renquant_orchestrator/agent_workflows.py, tests/test_agent_workflows.py (84 passed on this branch).
  prod or exp:   exp — queue logic; effective on the next loop cycle after merge + -run sync.
  existing data: renquant-strategy-104#107 head 377c75e0 carries 22 APPROVED reviews by haorensjtu-dev between 2026-10-05T10:53Z and 2026-10-06T02:29Z (one per loop cycle), its contract finding being `writes protected production path configs/strategy_config.json` [VERIFIED: gh pr view --json reviews + contract_findings() on the live fetch, 2026-10-05 21:3x PDT]. The codex account hit its 5-hour Plus window limit the same evening.
  best-known?:   yes — anti-vacuity: the new test fails against origin/main's module (1 failed) and passes on this branch.
  scope:         orchestrator queue logic only; no data/config/state touched.
NEXT:     merge, -run sync; the two production-path PRs (s104#107, RenQuant#644) stay for the operator's manual merge by design.
