# orch#1041: the intraday scheduler runs the PINNED strategy config

STATUS:   delivered. Two layers: the wrapper passes the pinned path explicitly
          and FAILS CLOSED if it is absent; the library candidate list now
          leads with the pinned runtime (sibling + umbrella stay as migration
          fallbacks for hosts without one).
WHY/DIR:  measured, not assumed: every activated session's manifest
          fingerprints the SIBLING checkout's config (c6d1abe2…) and the
          pinned copy was not even a candidate. Same class as orch#1016; same
          shape as the #1037 fix. This is also the §9.4 LIVE draft's encoded
          hard prerequisite — after deploy, the first session's fingerprint
          changes, and THAT session manifest supplies live_config_fingerprint.
EVIDENCE:
  artifact:      wrapper + runtime_paths + 2 tests (one reproduces the
                 measured both-exist-sibling-wins defect and pins the flip).
  prod or exp:   exp — behaviour changes only after merge + orch-run sync;
                 the discontinuity is self-documenting in the manifest.
  existing data: sibling hash c6d1abe2 == all manifests incl. today's; pinned
                 hashes af2344af [VERIFIED, orch#1041].
  best-known?:   yes — explicit-arg + fail-closed at the caller AND a safer
                 default beneath it, so other default-path callers (8 modules)
                 inherit the pinned preference without each needing a patch.
  scope:        one wrapper, one candidate list, tests. No config content
                changed anywhere.
REVIEW:    codex (haorensjtu-dev).
