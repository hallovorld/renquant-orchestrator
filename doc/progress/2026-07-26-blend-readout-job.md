# 2026-07-26 — blend readout job (pipeline#213 piece 3/3)

STATUS:    script + tests + plist file; NOT installed by this PR
WHAT:      ops/renquant104/rq104_blend_readout.py — daily post-run job: joins
           candidate_scores (prod) with the shadow clf comparison (MLflow),
           computes the FROZEN blend z(prod)+z(clf), appends both arms' top-10
           to an append-only ledger (data/rq104_blend_readout/, additive),
           back-fills realized fwd_20d spreads from ticker_forward_returns at
           maturity, and ALARMS (exit 2) when a live run exists but the shadow
           leg is silent (GOAL-1 AC3).
EVIDENCE:
  artifact:      tests/test_rq104_blend_readout.py — 4 passed (frozen-blend
                 equivalence; deterministic tie-break; idempotent append;
                 all-or-nothing maturity fill)
  prod or exp:   ops script; reads prod DBs read-only; writes ONLY the new
                 additive ledger dir
  existing data: pipeline#213 frozen readout governs; INFO/GATE reads are
                 separate ANALYSIS runs over this ledger
  best-known?:   v1 shadow-table locator scoped in-code (TODO tightened after
                 first live session's artifact layout is observed)
  scope:         launchd INSTALL deliberately excluded — the manifest entry and
                 launchctl load land together at the operator-pre-granted
                 activation batch (manifest==live atomicity per the drift check)
NEXT:      merge -> activation batch (load + manifest entry, pre-granted) after
           the operator executes the config step.
