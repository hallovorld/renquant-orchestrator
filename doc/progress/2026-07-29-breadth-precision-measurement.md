# Relocate breadth-precision measurement to renquant-model

STATUS:   delivered (relocation). Removes
          `doc/research/2026-07-29-breadth-does-not-buy-evaluation-precision.md`
          and `tools/breadth_precision_verify.py` from this repo. The memo
          now lives byte-identical in `hallovorld/renquant-model#97`. This
          PR is reduced to this progress doc documenting the relocation.

WHAT:     Round-2 review (BLOCKER) found the memo and its verifier are
          model-evaluation research, not orchestration: they read the clf
          43-fold score corpus, compute per-date IC under cross-sectional
          subsampling, fit a variance model, and probe the production
          panel for survivorship. Both prior MED findings on this PR
          (reviewable derivation, per-number provenance) were already
          resolved in-place before this BLOCKER; the relocation carries
          that fixed content forward unchanged — `renquant-model#97`
          re-ran the verifier against the same sha256-pinned inputs before
          committing and confirmed the tables match exactly.

WHY/DIR:  Per the umbrella multi-repo code-placement rule (model research
          -> `renquant-model`, never the orchestrator), this repo does not
          own model-evaluation evidence. Same pattern as the
          capacity-power-memo relocation
          (`doc/progress/2026-07-25-capacity-power-memo.md`, this repo) and
          the factorial-HFR study before it. GOAL-6 sequences Stage 1
          (830-name PIT panel) into Stage 2 "breadth retraining", partly on
          the premise that width improves measurement; the relocated memo
          measures that premise directly and finds it correct in direction
          but roughly an order of magnitude too small to matter — time (11
          independent 60-day blocks), not width, is the binding constraint,
          and the unused history is survivorship-contaminated (0 ticker
          exits over 10.3 years), which is exactly the defect Stage 1
          removes. That strengthens Stage 1's case; it does not weaken the
          programme.

EVIDENCE: n/a

NEXT:     This PR now carries no model/data claim of its own — the
          relocated claim and its §4(b) evidence block are in
          `renquant-model#97`'s progress doc
          (`doc/progress/2026-07-29-breadth-precision-measurement.md` in
          that repo). Review continues there. If GOAL-6 Stage 2 scoping
          needs this number, cite `renquant-model#97` directly; nothing
          further pending in this repo for this memo.
