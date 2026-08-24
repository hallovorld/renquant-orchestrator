# rq105 Stage-3 design: intraday live entries

STATUS:   design PR only — no code, no config, no deploy.
WHAT:     doc/design/2026-08-23-rq105-stage3-live-entries.md. Four-piece build
          (feature-panel persist → snapshot producer → wire existing shadow
          lane → guarded intraday entry loop), v1 admission = batch ∩ intraday,
          rollout ladder with the live flip as an explicit operator ask.
WHY/DIR:  operator-directed 2026-08-23: "105 = live trade, 尽快". The decision
          lane has skipped `not-wired` daily since 08-12; orch#1021 measured a
          partial-bar decision flip the design addresses.
EVIDENCE:
  artifact:      the design doc.
  prod or exp:   neither — documentation only.
  existing data: interface contracts read from the running tree, not memory:
                 FeatureSnapshot.from_mapping requirements
                 [shadow_realtime_serving.py:619], causality/staleness rules
                 [realtime_data_plane.py docstring], batch_scores meta shape
                 [data/rq105/*.meta.json], and the ABSENCE of any persisted
                 feature panel [find over data/, 2026-08-23].
  best-known?:   yes — reuses the reviewed Stage-1 modules instead of new ones.
  scope:        design only.
REVIEW:    codex (haorensjtu-dev).
