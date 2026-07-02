# RS-2 lane-A timing recommendation — research PR

STATUS:   research recommendation under the delegated-decision protocol (operator NOTIFIED;
          docs only; the config PRs themselves follow the normal control plane).
REVISION: r2.
WHAT:     `doc/research/2026-07-02-rs2-lane-a-timing.md` — RS-2 deliverable (#231 §6): split
          lane A by admission semantics. A-1 (qp_cash_drag_lambda 0→0.05, un-disabling the
          solver's shipped default) + A-3 (one-share floor, artifact removal) = PREPARE +
          SHADOW SEPARATELY now, each per its own preregistered protocol — NO LIVE ENABLE
          until each experiment's operational/risk gate clears (both carry genuine, if
          likely small, incremental risk — neither is "zero-risk"). A-2 (top_n 3→5–6) =
          DEFER behind its own dedicated frozen marginal-rank test (not merely D1-or-M3).
WHY/DIR:  descriptive measurement (NOT a statistical claim — see r2): the floor-clearing
          pool LOOKS ~80–88% thin-margin post-retrain in the sampled runs (mu within 25% of
          the 0.03 floor; 07-01: 15/17) — suggestive that the conviction floor separates
          little among admitted names, motivating caution on A-2 (M3 haircut unbuilt, D1
          verdict unrendered), but not itself a validated indistinguishability claim. At
          top_n=6 worst case ≈ +3 thin-margin entries/day ≈ +9pp/day unvalidated exposure.
          Deployment AC unaffected: lane B carries ≥60% per POC-B's ~40–43% lane-A ceiling.
EVIDENCE: descriptive SQL (in-memo, unspecified run selection, no CI/regime breakdown —
          caveated in r2) over runs.alpaca.db; POC-B ceilings; OXY forensics (2026-07-01).
          The S-TC buy-side 0.09 citation is REMOVED per r2 (retracted by #234).
NEXT:     Codex review; then two config PRs (A-1 sweep harness + A-3 pipeline change) enter
          the normal review lane; A-2 waits on D1/M3 and is re-cut as its own PR then.

ROUND 2 (Codex CHANGES_REQUESTED, 2026-07-02): 6 findings, all addressed in
`doc/research/2026-07-02-rs2-lane-a-timing.md`.
1. Removed the "buy-side TC 0.09" citation — #234's corrected revision (same review round)
   retracted that number (its admission/sizing split had misclassified `blocked_by` values,
   forcing a spurious "100% blocked" result); #234 now reports zero validated sizing-TC
   days, all exploratory. A-1/A-3 no longer claim to "repair a measured TC deficit."
2. A-3 reclassified from "zero-risk ordering fidelity" to a genuine model-selection-adjacent
   change: a one-share floor changes WHICH names get selected, not just relative order,
   affecting concentration/cash-use/exposure and in some states adding net exposure.
3. A-1 reclassified from "zero incremental model risk" to genuine (bounded) incremental
   model risk: caps bound per-name loss, they do not prove unchanged risk/expectancy.
4. The "thin-margin" SQL/finding relabeled as a descriptive score-density observation, not a
   statistical indistinguishability claim — the query leaves `<full runs>` unspecified, has
   no canonical one-run-per-day selection, and reports no CI or regime breakdown.
5. A-2's gate changed from "D1 OR M3" to its own dedicated frozen marginal-rank test
   (forward net return, turnover/cost, concentration, regime stability for the 4-vs-6
   comparison specifically) — an aggregate model verdict doesn't establish incremental
   pick-4-to-6 value.
6. A-1 and A-3 downgraded from "ENABLE NOW" to "PREPARE + SHADOW separately, own
   preregistered protocol, NO LIVE ENABLE until each gate clears," per #228 §1.2's
   one-change-at-a-time requirement — added explicit baseline/immutable-sessions/estimand/
   non-inferiority-thresholds/stop-rule/rollback for both, matching #228's actual format.
   Made explicit that a 10-session shadow run validates plumbing/constraint-binding
   behavior, not a 60-day economic outcome.
STATUS updated: recommendation is now "prepare and shadow separately now; no live enable
until each experiment's preregistered operational/risk gate clears," matching Codex's
requested language exactly.
