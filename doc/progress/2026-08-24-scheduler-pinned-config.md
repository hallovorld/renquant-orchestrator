# orch#1041: the intraday scheduler runs the PINNED strategy config

STATUS:   delivered, v2 after review ("existence is not pin verification").
          The wrapper now calls the GENERALIZED #1037 resolver, which proves
          three things or refuses: the lock names renquant-strategy-104, the
          runtime checkout HEAD equals that pin, and the config BYTES equal
          the pinned blob (a dirty file in a pinned checkout is exactly as
          unreviewed as a sibling tree). The scheduler has NO fallback. The
          library candidate list leads with the pinned runtime; migration
          fallbacks remain for non-scheduled callers only.
WHY/DIR:  measured, not assumed: every activated session's manifest
          fingerprints the SIBLING checkout's config (c6d1abe2…) and the
          pinned copy was not even a candidate. Same class as orch#1016; same
          shape as the #1037 fix. This is also the §9.4 LIVE draft's encoded
          hard prerequisite — after deploy, the first session's fingerprint
          changes, and THAT session manifest supplies live_config_fingerprint.
EVIDENCE:
  artifact:      wrapper + generalized rq105_pinned_common.py
                 (pinned_commit_for / verify_pinned_file + --subrepo
                 --verify-file CLI; the renquant-common API is unchanged) +
                 runtime_paths + 9 refusal tests over REAL scratch git repos:
                 missing lock entry, wrong HEAD, DIRTY config at the right
                 HEAD, unreadable git state, missing file, sibling-never-wins,
                 CLI round-trip and CLI dirty-refusal. Also fixes the CI
                 breakage the tuple growth caused: two fixed-pair unpacks and
                 one [1] index now bind first/[-1] with the reason inline.
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
