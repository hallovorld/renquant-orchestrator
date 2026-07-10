# Workstream: architecture compliance remediation (#454 registry)

STATUS:   R0 in-progress — twin-parity tripwires PR (this PR); registry +
          roadmap merged 2026-07-10 (#454, guidance-only).
GOAL:     make the multi-repo architecture self-defending per the #454
          roadmap: R0 tripwires → (R1 launchd ∥ R6 single-source) → R2
          kernel cutover (the P0: gate evidence ≠ live code) → R3/R4;
          R5 fail-closed fingerprints independent after R0.
NEXT:     Codex review of the R0 tripwires PR; then the remaining R0 items
          land in their owning repos (boundary AST tests → base-data/
          artifacts; unknown-key counter → pipeline). No R1+ code moves
          before their tripwires exist.
EVIDENCE: [VERIFIED 2026-07-10] twin states pinned by
          `data/twin_parity_manifest.json`: alerts.py + ibkr_broker.py
          byte-identical; broker/alpaca_broker/paper_broker/readonly_broker
          diverged (sha-pinned per side). Full audit evidence:
          `doc/research/evidence/arch_audit_2026_07/`.
