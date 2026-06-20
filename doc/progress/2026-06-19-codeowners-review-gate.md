# CODEOWNERS — make the Codex-review gate mechanical

STATUS:   in-progress (awaiting Codex review; not self-merged)
WHAT:     adds `.github/CODEOWNERS` = `* @hallovorld @haorensjtu-dev` so each agent's PR
          requires the OTHER agent's approval (mutual review, no self-approval deadlock).
WHY/DIR:  converts "Codex review is the gate" from convention (AGENT-RETROSPECTIVE §7
          caveat / §8) toward MECHANICAL policy — the contract's own thesis is "trust only
          controls that hold whether or not the agent cooperates."
EVIDENCE: both actors have valid code-owner access — hallovorld=admin, haorensjtu-dev=write.
          `[VERIFIED — gh api repos/.../collaborators/<u>/permission]`
NEXT:     **After this merges to main**, enable the setting (one admin PATCH):
          `gh api -X PUT repos/hallovorld/renquant-orchestrator/branches/main/protection/required_pull_request_reviews -f require_code_owner_reviews=true`
          (or via the existing ruleset). **Ordering is load-bearing**: enabling it before
          CODEOWNERS is on main locks all merges. Once enabled, flip AGENT-RETROSPECTIVE
          §8 from "convention" to "mechanical (enforced)". This is a tightening of
          protection, not a bypass.
