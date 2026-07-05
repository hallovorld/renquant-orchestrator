# add outcome_observer to 104/107 as-built module tables

STATUS:   progress-doc gate fixed; content blocked on #351.
WHAT:     added `outcome_observer` entries to the 104/107 as-built module tables.
WHY/DIR:  the required `require-progress-doc` CI check was failing (no doc/progress
          artifact was included). Separately, Codex flagged that this doc describes
          outcome_observer as delivered module surface while #351 (the underlying
          implementation) is still blocked on a real Path B partial-write
          data-integrity bug and a data-source overclaim.
EVIDENCE: `gh pr view 351 --repo hallovorld/renquant-orchestrator --json reviewDecision`
          → CHANGES_REQUESTED at time of writing. `[VERIFIED — gh pr view, this session]`
NEXT:     rebase this doc's outcome_observer entries on #351 once it lands review-clean
          — do not merge this PR before #351 merges, per Codex's explicit ordering ask.
