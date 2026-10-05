# 2026-08-29 — GOAL-2v3 Stage I-2 preregistration (stacked meta-learner)

STATUS:    delivered (design only). The Stage I-2 prereg is frozen BEFORE any
           meta-learner is fitted; no harness, no fit, sealed window untouched.
           Prerequisite evidence record #1088 is MERGED and in this branch's
           ancestry (merged from main).

WHAT:      Adds `doc/design/2026-08-29-goal2v3-stage-i2-prereg.md`: inputs
           (re-fit base OOF predictions + prior-close slow state; s₀ is NOT a
           meta-feature), nested forward-chaining meta-folds M1..M4 over the
           I-1 OOF halves (meta-OOF period 2022-07-01..2024-06-30), one frozen
           learner (XGB depth 2 / 200 trees / seed 20260829), an unweighted
           z-sum diagnostic M0, a determinism guard (re-fit must reproduce the
           I-1 block-t to 4 dp), fail-closed binding to the I-1 bundle, and
           the pass bar P1 ∧ P2 ∧ P3 with an enumerated outcome register
           (PASS / FAIL-A / FAIL-B / REFUSED).

WHY/DIRECTION:
           The parent design (2026-08-27, §Stage I-2) fires I-2 when a
           conditioned base passes AND beats B0. That fired by the letter and
           by 0.087 block-t units, while the naive reference s₀ = −r13 scored
           above every learned base. A stack that beats B0 but not −r13 has
           earned nothing a one-line feature does not already deliver, so the
           bar is STRENGTHENED (P3 added; nothing removed) before observation.
           FAIL-A / FAIL-B pause the line for an operator decision instead of
           inviting a second, post-hoc design.

EVIDENCE:  §4(b) block — this PR makes no new model/data claim; it cites the
           merged I-1 record.
           - I-1 bundle (#1088, merged): run_id `i1-dev-20260829T113813Z-666484a7`,
             source commit 666484a7, `doc/research/data/2026-08-29-g2v3-i1/
             i1-dev-20260829T113813Z-666484a7/`; sha256 report.json
             `666d9c6a9a2286af4215399aebbd07a2fda8efafc6b5440d8d39ea6b9e1e1542`,
             audit gz `d124d8f2a8766edf7d4a6f767206444467f05fa3bb8dec1818a76b01b2cd3082`
             `[VERIFIED shasum on this branch after merging main]`.
           - 0.087 margin: `report.bases.B2.overall.block_t` = 3.5915,
             `report.bases.B0.overall.block_t` = 3.5042 → 0.0873
             `[VERIFIED report keys]`; `report.stage_i2_trigger.fired` = true.
           - s₀ observation: `report.s0_reference.overall.block_t` = 4.1861 vs
             bases 3.1837–3.5915; mean block IC B2 0.009603 < B0 0.010911
             (`report.bases.*.overall.mean_block_ic`) — B2's higher t is a
             variance effect, not a mean effect `[VERIFIED report keys]`.
           - Parent rule quoted verbatim in the prereg §0 from
             `doc/design/2026-08-27-goal2v3-intraday-granularity.md` (Stage
             I-2 trigger paragraph).

NEXT:      (1) codex review of this prereg; (2) harness PR
           `scripts/experiments/g2v3_stage_i2_stack.py` implementing it
           literally with the #1084 fail-closed standard (I-1 binding,
           determinism guard, dirty-tree / existing-bundle refusal, tests for
           P1/P2/P3 and the outcome register); (3) one `--dev-run` from a
           clean main worktree and a descriptive record PR quoting the
           outcome-register row with the margins as numbers. Decision owner if
           FAIL-A/FAIL-B: the operator.

Reviewer decision: whether P3 is an acceptable strengthening of the merged
design (adds a condition; removes none) and whether §2's nested layout is the
literal reading of "same OOF discipline".

Memory tier: MID (research line state); no LONG-ledger constraint changes.
