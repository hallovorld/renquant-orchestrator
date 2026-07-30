# Relocate the scorer-attribution probe to renquant-model

STATUS:    delivered (relocation). Removes
           `scripts/scorer_attribution_probe.py`, its tests, and
           `doc/research/2026-07-29-scorer-attribution-volatility-and-profitability.md`
           from this repo. The work now lives, rescoped, in
           `hallovorld/renquant-model#103`. This PR is reduced to this
           progress doc.

WHAT:      Codex BLOCKER: the probe parses a production model artifact and
           implements model-attribution semantics — model-factory
           responsibilities, not daily orchestration. Per the umbrella
           multi-repo code-placement rule, this completes the move.

           The same review also required a substantive rescope, which
           travelled with the relocation rather than being fixed twice.
           Probe B draws each feature INDEPENDENTLY
           (`rng.normal(size=(n_baselines, n_features))`), while real feature
           vectors are strongly correlated — so it samples off-manifold
           points and measures model-wide MARGINAL SENSITIVITY, not
           attribution of any historical score. The claim that AAPL was
           "marked down for rallying calmly" is WITHDRAWN as an identified
           cause and restated as a hypothesis, with the three reasons the
           method cannot settle it. Verified against the code before
           accepting the finding.

WHY/DIR:   Per the umbrella multi-repo code-placement rule (model research
           and model-artifact semantics -> `renquant-model`, never the
           orchestrator), this repo does not own model-attribution tooling.

EVIDENCE:  n/a

NEXT:      This PR carries no model claim of its own — the relocated probe,
           its 8 tests, and the rescoped findings are in
           `renquant-model#103`. Review continues there. The actionable
           follow-up identified by the rescope is retaining per-day feature
           vectors, without which real per-name attribution is impossible.
