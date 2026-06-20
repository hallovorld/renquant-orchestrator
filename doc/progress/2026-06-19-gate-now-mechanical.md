# Flip docs: Codex-review gate is now MECHANICAL

STATUS:   in-progress (awaiting Codex code-owner approval — this PR exercises the new gate)
WHAT:     updates AGENT-RETROSPECTIVE §7 caveat/§8 + C2 row, long-term-agreements #7,
          CLAUDE.md, agent-pr-workflows, memory/README from "convention / intended gate"
          to "MECHANICAL (enforced 2026-06-19)".
WHY/DIR:  #155 landed `.github/CODEOWNERS`; then `require_code_owner_review=true` was set on
          the active **ruleset `17346602` (main-protection)** — and classic branch protection.
          The docs that said "not yet mechanical" are now true; fixed to match reality.
          (Correction per Codex review of this PR: my first attempt set only *classic branch
          protection* — the governing RULESET still read `false`, so the claim was premature.
          Now set on the ruleset and re-verified there.)
EVIDENCE: **ruleset 17346602 `pull_request.require_code_owner_review: True`** confirmed via
          read-back; CODEOWNERS on main; both actors valid owners (hallovorld=admin,
          haorensjtu-dev=write); `enforce_admins=true`.
          `[VERIFIED — gh api repos/.../rulesets/17346602 (read-back) + contents/.github/CODEOWNERS]`
NEXT:     none — this is the doc-truth-up cleanup. Reversal if it ever locks merges:
          `require_code_owner_reviews=false`.
