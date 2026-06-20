# Flip docs: Codex-review gate is now MECHANICAL

STATUS:   in-progress (awaiting Codex code-owner approval — this PR exercises the new gate)
WHAT:     updates AGENT-RETROSPECTIVE §7 caveat/§8 + C2 row, long-term-agreements #7,
          CLAUDE.md, agent-pr-workflows, memory/README from "convention / intended gate"
          to "MECHANICAL (enforced 2026-06-19)".
WHY/DIR:  #155 landed `.github/CODEOWNERS`; then `require_code_owner_reviews=true` was
          enabled on main-protection (enforce_admins already true). The docs that said
          "not yet mechanical" are now stale — fixed to match reality (no over/under-stating).
EVIDENCE: `require_code_owner_reviews: True` confirmed via read-back; CODEOWNERS on main;
          both actors valid owners (hallovorld=admin, haorensjtu-dev=write).
          `[VERIFIED — gh api branches/main/protection + contents/.github/CODEOWNERS]`
NEXT:     none — this is the doc-truth-up cleanup. Reversal if it ever locks merges:
          `require_code_owner_reviews=false`.
