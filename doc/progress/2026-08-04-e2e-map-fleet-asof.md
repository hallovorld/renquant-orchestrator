# 2026-08-04 (final AS-OF 21:19 PT / 2026-08-05T04:19Z) — e2e map refresh: the fleet, the override, and the blocked gate

Second AS-OF refresh of the day (the map's own discipline). The document's ONE
as-of boundary is 2026-08-05T04:19Z (21:19 PT) — header and gaps section
carry the same stamp, and every cell was verified against the deployed
surfaces at it. What changed since 15:10 PT, all measured:

- **PROD is the z-blend on the full book** (operator override; audit manifest,
  single-commit rollback, review condition on record). The map's PROD row now
  says so instead of describing the retired single-scorer state.
- **The fleet exists**: Step 5c/5d/5e rails + profiles + broker tags deployed,
  callsigns Rf / RCS / RCf (RC and RSs already serving). RCS is
  RAIL/REGISTRY-ready (profile, tag and rail all deployed) but NOT runtime-
  eligible at this AS-OF: its first execution fail-closed on the clf
  component's kind and the fix (s104#91, merged `c8bba9c9`) is not in the
  deployed runtime s104 (`b99101d5`) yet — RCS serves only after the pin
  advance + deploy. The fast-leg lanes are dormant until the 08-08 genesis.
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

## Round 2 (codex): the AS-OF must not backdate an unmerged repair

Codex caught a real provenance defect: the first version stamped
2026-08-05T04:05Z while describing RenQuant#580's fail-closed behaviour as
current reality — #580 was still OPEN at that timestamp. Backdating a repair
into a measured-state document is the same defect class as an
asserted-not-measured number.

Fixed by doing the verification rather than the wording: #580 is now merged
(`ba2b3eb5`) and DEPLOYED, re-verified at the new AS-OF (2026-08-05T04:19Z)
against the live wrapper — `candidates=("$pinned_path")` is the sole candidate
line and the `WEEKLY-BLOCKED` path is present. The map now also carries an
explicit PROVENANCE RULE, and applies it to the fleet row: s104#91 (the RCS
clf-component-kind fix) is MERGED `c8bba9c9` but the runtime s104 checkout is
still `b99101d5`, so RCS is documented as still fail-closed until the next pin
advance + deploy.
