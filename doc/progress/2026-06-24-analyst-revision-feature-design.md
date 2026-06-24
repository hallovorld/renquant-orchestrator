# 2026-06-24 — Analyst estimate-revision feature (P1 design)

STATUS: design landed; code/data not started (operator-gated on MCP OAuth).

WHAT: Design doc `doc/design/2026-06-24-analyst-revision-feature.md` for adding
analyst estimate-revision as a model feature — data source (financial-analysis
MCP, PIT, not web-scraping), candidate features (consensus rating, implied
upside, dispersion, n_analysts, and the alpha: estimate-revision deltas /
up-downgrades), hard constraints (PIT discipline, placebo-clean WF validation
before production, explicit missing-coverage handling), and integration options
(overlay-first vs in-panel).

WHY-DIR: operator made analyst data P1 after the 2026-06-23 trade review showed
analyst targets reconcile to real account prices, so the lens is valid and
disagrees with the model usefully (model's vol-tilt picks have the least
forward upside; beaten-down names have the most). Estimate revisions are a
documented orthogonal alpha the model doesn't see; the cheap proxy (fundmom
#177) was rejected, so this needs its own validation.

EVIDENCE:
- `[VERIFIED]` 2026-06-23 review: account prices reconcile to live web analyst
  targets (CRWD $681 vs $673–718; SPG $217 vs $208–214; NFLX $72.82 → ~$112
  +54%) — confirming the lens is valid, motivating the feature.
- `[VERIFIED]` financial-analysis MCP servers (FactSet/S&P/Morningstar/LSEG) are
  connected in-session with authenticate/complete_authentication tools.

NEXT: (1) operator OAuths the MCP feed; (2) pull PIT consensus + revisions for
the watchlist; (3) build features + validate placebo-clean through the per-regime
WF gate as an overlay on the RAW model before any production integration.
