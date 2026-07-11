# Progress — PR #106 roadmap completion audit + cross-stock pilot (GOAL-7a)

DATE: 2026-07-10
BRANCH: `research/goal7a-106-audit-xstock` (isolated worktree off origin/main @ 40c51d33)

## What

1. **Audited every actionable lead in merged PR #106** (2026-06-12 model-capability
   roadmap; doc deleted from main in the 06-16 consolidation — recovered from git history
   incl. the #109 errata) and verified each against the repos today. Full lead-status
   table: `doc/research/2026-07-10-106-roadmap-audit-xstock-verdict.md` §1.
2. **Cross-stock attention lead**: headline (0.203) REFUTED (winner-picked; DOE full-run
   mean +0.0507, 12/25 negative — verified in the umbrella DOE driver.log). Dated evidence
   chain reconstructed (§2): #109 errata → #126 strict paired 3-seed (3/3 positive,
   suggestive) → umbrella #380/#382 scorer silently dropped the weights (deployable only
   since 06-16) → 06-16 campaign "helps but doesn't pass alone / B3<B2" → 06-23 re-scope
   to long-term. Verdict: not neglected; residue real but ~4× below the repaired gate's
   measured resolution → dedicated campaign refuted (§3).
3. **Executed the cheap remnant**: frozen 2-seed paired pilot (base vs `--cross-stock-attn`)
   on the CURRENT corpus vintage (frontier 2026-04-02, rail-derived cutoff 2026-03-30),
   exact weekly-rail recipe, local MPS, scratch outputs only, spec committed BEFORE the
   runs (§5; results §7). Pre-registered a weekly-rail ride-along spec with frozen
   promotion criteria (§6) — implementation is a separate follow-up PR, needs approval.
4. Added the VERDICTS.md row (same PR as the memo, per ledger rule).

## Boundaries honored

- No production path written (panel/SPY read read-only; outputs in session scratchpad).
- No git in the live umbrella tree or primary checkouts (worktree only).
- No Modal (blocked pending #463 follow-ups); local compute only.
- No merge; Codex review gate applies.

## Decision needed

Approve/deny the §6 ride-along wiring PR (opt-in env flag on the weekly rail). Nothing in
this PR changes any production behavior.
