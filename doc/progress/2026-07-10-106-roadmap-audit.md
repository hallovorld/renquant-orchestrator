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
3. **Executed the cheap remnant**: frozen 2-seed paired **TARGETED CONFIRMATION** (base
   vs `--cross-stock-attn`) on the CURRENT corpus vintage (frontier 2026-04-02,
   rail-derived cutoff 2026-03-30), exact weekly-rail recipe, local MPS, spec committed
   BEFORE the runs (§5). r2 (Codex): seeds 44/45 were pre-known-positive from #126, so
   this is vintage-robustness evidence only — never a replication.
   **Result: 2/2 paired deltas POSITIVE** (+0.0207 / +0.0172, mean +0.0189, 8/8
   per-regime deltas ≥ 0; a base-arm dead seed recurred, the cross-stock arm produced
   none) → per the frozen rule the ride-along recommendation STANDS under the §6a
   protocol. **The n=2 result justifies NO live or shadow promotion.**
4. Added the VERDICTS.md row (same PR as the memo, per ledger rule).

## r2 (2026-07-11) — Codex CHANGES_REQUESTED, all four objections addressed

1. Run reclassified as a targeted confirmation on pre-known seeds; selection bias stated
   plainly (§5); deterministic independent seed rule preregistered (§5a:
   sha256("d6-xstock-ridealong-2026") → 4294, 6313, 5809, 8531, 2601).
2. Evidence sealed out of the scratchpad: content-addressed run bundle in
   **renquant-artifacts PR #14** (commit `82ad63ee8`,
   `store://experiments/xstock-pilot-20260711/RUN-LOCK.json`, fingerprint
   `sha256:86b06dec…`; 20 blobs sha256-listed in STORE-MANIFEST.json; val-preds parquets
   make every reported number independently recomputable; checkpoints excluded by policy,
   hashes recorded; 22/22 artifacts-repo tests pass). Memo §7 cites the bundle; scratchpad
   paths removed from the evidence chain.
3. Input/code identity rebound to pinned artifacts + exact commits (corpus content sha256
   + recipe owner renquant-base-data `transformer_corpus.py` @ `fef604bff`; 9-repo runtime
   pin map, renquant-model `84a3c1864` with trainer byte-identical to `45e42a1e3`); the
   umbrella-working-copy consumption is recorded as a limitation of THIS run; the §6
   wiring requirement mandates pinned-artifact resolution.
4. §6a analysis protocol replaces "≥8 weekly pairs": fixed 16-week window + single
   readout date, weekly val-side series demoted to monitoring-only (98% overlap → not
   independent trials), confirmatory estimand = deduplicated FORWARD-session paired ΔIC
   with 60-session moving-block bootstrap (extend-don't-relax on small-n refusal),
   no-peeking rule with logged-downgrade, independent-seed secondary set every 4th week,
   OOS gate named = `promote_shadow_patchtst.py` §3.4 (fail-closed, artifact + current
   panel), kill rule at readout.

## Boundaries honored

- No production path written (panel/SPY read read-only; outputs in session scratchpad).
- No git in the live umbrella tree or primary checkouts (worktree only).
- No Modal (blocked pending #463 follow-ups); local compute only.
- No merge; Codex review gate applies.

## Decision needed

Approve/deny the §6 ride-along wiring PR (opt-in env flag on the weekly rail). Nothing in
this PR changes any production behavior.
