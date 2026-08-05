# 2026-08-04 (21:05 PT) — e2e map refresh: the fleet, the override, and the blocked gate

Second AS-OF refresh of the day (the map's own discipline). What changed since
15:10 PT, all measured:

- **PROD is the z-blend on the full book** (operator override; audit manifest,
  single-commit rollback, review condition on record). The map's PROD row now
  says so instead of describing the retired single-scorer state.
- **The fleet exists**: Step 5c/5d/5e rails + profiles + broker tags deployed,
  callsigns Rf / RCS / RCf (RC and RSs already serving). RCS is
  serving-eligible; the fast-leg lanes are dormant until the 08-08 genesis.
  3-component support landed via the N≥2 generalization.
- **Gap #1 is now the gate itself** (orch#799): the measured phantom-config
  incident (same booster, Sharpe 0.6018 vs 0.0524) and the fail-closed repair
  (RenQuant#580). The map states plainly that the weekly promote will BLOCK
  rather than emit numbers until the blend-prod reference rule is decided, and
  that RFC#210 governance is what keeps prod fresh in the meantime.
- **R4/orch#564 moved from gap to CLOSED** with the before/after bundle
  measurement (9,154 B absent → 10,087 B present with the RFC#210 identity).
- New honest gaps recorded: the blend's zero OOS record, the S1/S2 degeneracy,
  the orphaned rawlabel host (orch#798), and the built-but-unscored clf corpus.

No behavior changes — documentation of measured state only.
