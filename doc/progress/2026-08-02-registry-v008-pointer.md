# GOAL-3: registry V-008 row gains its remediation pointer (pipeline#249)

STATUS: complete (docs-only).
WHAT: the V-008 entry (WF gate promotes on gross statistics, P0) now records
that remediation is FILED as renquant-pipeline#249, with the same-day
re-verification that preceded the filing; revision history appended.
WHY/DIR: the registry is the single G3 record; a filed remediation that only
lives in an issue thread is invisible to the next auditor reading the row.
EVIDENCE:
  artifact:      doc/research/2026-07-12-architecture-violation-registry.md
                 (V-008 row + revision history)
  prod or exp:   exp — audit documentation, no runtime surface
  existing data: re-verification greps on pipeline main@c823184, 2026-08-02:
                 0 cost-term hits in the two gate files, 0 cost_model consumers
                 in pipeline src/ (no-pipe form, both exit 1) `[VERIFIED —
                 recorded verbatim in pipeline#249]`
  best-known?:   yes — first remediation pointer on this row since the 07-12
                 re-audit
  scope:         docs-only; no code; no severity regrade
NEXT: pipeline owns the implementation per #249's staged spec. AC6 gate-design
rule: N/A — docs-only.
