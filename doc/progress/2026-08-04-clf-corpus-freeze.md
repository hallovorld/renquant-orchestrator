# 2026-08-04 — clf corpus freeze preregistration (orchestrator#788 closure of design gaps)

Adds `doc/research/2026-08-04-clf-corpus-freeze.md`: the frozen build plan for
`walkforward_clf_top_decile_fwd60_v1`. Key decisions and their measured bases:

- **Preserved dated vintage copy is the contract** — measured today that Job
  B's sha-of-live-path vintage (`55811f63…`) is unrecoverable (live panel now
  `870f68eb…`); a sha of a mutable path proves what was read, not what can be
  re-read.
- Window grid = the 43 post-seam Stage-2 cutoffs verbatim; pre-seam out of
  scope (same unpreserved-vintage problem).
- Trainer invocation frozen verbatim (the 08-01 `--train-cutoff` handle,
  leak-safe truncation placement); staging-dir isolation so the live panel
  cannot be read by accident; `refuse_non_shadow` handled mechanically and
  recorded in the claim.
- Acceptance ≥42/43 (final-window refusal designed); segment-only pooling;
  placebo = the gate's 120d convention; no promotion interest licensed.
- Cost basis measured: ~5-minute local build (probe: 6 s/window warm,
  5.94 GB peak).

Execution happens only after this merges (freeze-then-run).
