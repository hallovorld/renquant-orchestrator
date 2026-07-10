# Deployment theory: beta/alpha separation — research

**Date**: 2026-07-09
**Status**: Research memo r1 (theory complete; empirical section pending — 6-arm
tuning-subset replay running)

## Bottom line

The 65% cash drag is a CATEGORY error, not a calibration error: the system makes
beta exposure conditional on alpha confidence. Theory (Merton separation,
Grinold-Kahn, Moreira-Muir vol-managed portfolios, MacLean-Thorp-Ziemba,
DeMiguel) says deployment should be a risk-budget decision on estimable
quantities (realized vol), with the weak-IC signal deciding SELECTION and
IC-scaled tilts only. Proposes amending RFC #443 L1 from signal-driven
(Σ shrunk-Kelly) to vol-targeted E* = min(σ_target/σ̂_pf, E_ceil(regime)).
The signal-driven governor stays as a falsifiable experimental arm.

## Changes

- `doc/research/2026-07-09-deployment-theory-beta-alpha-separation.md` — the
  memo: thesis, four theory pillars, proposed L1 revision, 6-arm experiment
  design (tuning subset, nested selection), decision asks for codex

## Discipline notes

- Empirical results land in this PR before merge (tuning subset only; eval
  subset reserved for the post-approval confirmatory run)
- The earlier config-only "bridge" proposal is audited by the `kelly_raw` arm
  rather than asserted
