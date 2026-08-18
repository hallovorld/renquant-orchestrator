# G-I `tail_q90_60d` — frozen screen spec (doc only)

STATUS:    frozen experiment spec for review. Docs only — no training, no scoring, no
           code. The run happens only after this merges AND the committed runner is
           separately reviewed (the #990 freeze-then-review-then-run lesson, applied
           prospectively).

WHAT:      Commit `doc/research/2026-08-18-gi-tailq90-screen-spec.md`: the 4th screen
           candidate — quantile regression (q=0.90) on the EXISTING panel/label,
           targeting the account's proven tail skill. Frozen: candidate = prod recipe
           VERBATIM (172 features + norms + params + fwd_60d_excess label, pinned by the
           served artifact's fingerprint f8fb2259) with exactly ONE delta
           (objective → reg:quantileerror, quantile_alpha 0.90); PIT scoring calendar
           (31 quarterly refits 2018-Q2..2025-Q4, expanding window, 60-trading-day
           embargo C+60≤d); corpus/estimand/triage-rule inherited from #987 (paired
           cross-sections per the #990 fix; block-t≥1.0 rule) with ONE declared delta —
           **h=60 primary / h=20 informational**, aligned to the trained 60d label
           (REVISED per codex review 2026-08-18: an earlier draft inherited h=20
           primary verbatim, a horizon mismatch) — and #987 §2's REVISED survivorship
           semantics carried intact (direction UNKNOWN; strictly triage-only, no kill
           without a point-in-time-universe rerun; the withdrawn "kills valid" claim is
           NOT reinstated); new-family one-shot budget + corpus-exposure ledger
           (2nd family on this corpus; the screen admits nothing and kills nothing);
           the declared high-ρ risk (shares features+label with multifactor_core) and
           the ρ-reference refit provision.

WHY/DIR:   Operator-directed 2026-08-18 ("深度分析具体原因,提出改进方案和解决方案,开工")
           after the emitter family screened 0/3. Root-cause item 3 of that analysis:
           the highest-prior candidate (tail-skill-targeted) was sequenced LAST and never
           built — corrected here. The candidate's prior is declared BEFORE any run.

EVIDENCE:
  artifact:      the spec + this doc. No code, no run, no live change.
  prod or exp:   neither — spec only.
  existing data: [VERIFIED] served-artifact facts frozen into §2: label_col
                 fwd_60d_excess, lookahead 60, 172 feature_cols, params dict
                 (rank:pairwise, max_depth 5, eta/subsample/colsample/min_child_weight/
                 seed), config fingerprint f8fb2259 — read from
                 artifacts/prod/panel-ltr.alpha158_fund.json 2026-08-18. Corpus/rule
                 facts inherited verbatim from merged #987/#990/#992.
  best-known?:   yes — exactly ONE delta from production (the objective), so any screen
                 difference attributes to the objective, not to recipe drift; the
                 zero-new-architecture constraint is honored (existing label, no new
                 data prep — the 20d-label variant was explicitly rejected for that
                 reason and the rename tail_q90_20d→tail_q90_60d is recorded); the
                 known failure mode (high ρ vs multifactor_core) is declared
                 prospectively; power context at the PRIMARY h=60 endpoint
                 (n_eff≈16, 29 non-overlapping blocks [VERIFIED — prior work,
                 #987 §4]) declared as annotation-grade — acceptable only because
                 outcomes are non-final triage, never kills.
  scope:         "freezes the tail_q90_60d screen. Authorizes, AFTER merge + a reviewed
                 runner PR: ~31 local deterministic refits + the ONE scoring run,
                 read-only inputs, isolated worktree, results as a separate PR. Nothing
                 else: no admission, no serving change, no deploy, no new data source."

TESTS:     none — doc-only PR.

NEXT:      codex review → runner PR (reviewed BEFORE execution) → the one run → results
           PR. In parallel: #985 item-1 plane consolidation is being implemented (its
           own PRs); the serving-plane power-map re-derivation follows it.
