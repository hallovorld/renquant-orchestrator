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

## 2026-07-11 r3 addendum: label-availability cutoff + honest umbrella scoping

Codex round-2 (2026-07-11T08:11:56Z), one remaining blocker: §6a treated the 16-week
scoring window as ~80 forward ΔIC observations available at an E+16w readout, but the
estimand is `fwd_60d_excess` — a 60-business-day-forward label. At E+16w only the first
~20 business days of the cohort have mature labels; the rest would require look-ahead.
The stated 60-session block bootstrap literally cannot form one block from ~20
observations, so the "80 observations, 1.3 blocks" power note was materially wrong at
the stated readout date.

Fixed in `doc/research/2026-07-10-106-roadmap-audit-xstock-verdict.md` §6a.1/§6a.3: added
an explicit inclusion rule (`score_date + 60 business days <= as_of_date`) and moved the
readout date from E+16w to **E+16w+60 business days** (≈32 weeks after enable) — the
point at which the FULL 16-week scoring cohort's labels have genuinely matured. At that
corrected date the ~80-observation / ~1.3-block count is valid; every window extension
(if the small-n refusal fires) applies the same +60bd wait before its own readout.
`VERDICTS.md`'s row and the progress-doc bullet above were phrased loosely ("fixed
16-week window") — not literally wrong, but the readout timing needed the same
correction; `VERDICTS.md`'s reopening-condition cell now states the corrected date
explicitly.

Also replaced the `RenQuant scripts/promote_shadow_patchtst.py` local-path reference
(§6a.6) with the actual citation: `renquant-orchestrator doc/design/2026-06-30-shadow-
scorer-freshness.md` §5 (RFC r2, orchestrator PR #212), which documents that the script
is INTENTIONALLY umbrella-owned per that RFC's own ownership split (§5) — not a
mis-scoped runtime dependency. Made explicit that this is a deployment-time-only
operational gate invoked after §6a.3's analysis independently produces a GO verdict from
pinned artifacts; no computation in the protocol itself reads or executes umbrella code.
