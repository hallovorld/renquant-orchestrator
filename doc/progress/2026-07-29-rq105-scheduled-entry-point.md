# Progress: the 105 blend switch shipped and stayed dark for a day

STATUS:   delivered (manifest + repo plist aligned to the installed reality, plus an
          invariant test). The scheduled job now goes through the wrapper.

WHAT:     `ops/launchd_manifest.json` for `com.renquant.rq105-batch-scores-export` now
          invokes `run_batch_scores_export.sh` (via `/bin/zsh`, matching the wrapper's
          own shebang) instead of `export_batch_scores.py` directly. The repo's
          installed plist (`ops/renquant105/com.renquant.rq105-batch-scores-export.plist`)
          was already on the wrapper in `origin/main` — only the manifest was stale.
          Adds a test asserting the scheduled entry point is the wrapper.

WHY/DIR:  `RQ105_SCORE_SOURCE` defaults to **blend** in the wrapper and to **prod** in
          the module. The scheduled job called the module DIRECTLY, so the blend switch
          — merged, correct, and verified by hand — never reached the only path that
          matters.

EVIDENCE:
    artifact:      data/rq105/batch_scores_2026-07-29.meta.json (pre-fix serving
                   vector) + ops/launchd_manifest.json (the fix) +
                   tests/test_rq105_batch_scores_export.py (the new invariant)
    prod or exp:   prod — this is the live launchd-scheduled export job
    existing data: `[VERIFIED — data/rq105/batch_scores_2026-07-29.meta.json, read
                   2026-07-29]` the first serving vector produced after the blend
                   switch merged: `score_source: prod`, `source_db: runs.alpaca.db`,
                   `blend_component_sha256s: {}` — a full day after "105 is on blend".
                   `[VERIFIED — git grep, read 2026-07-29]` the manifest entry for
                   `com.renquant.rq105-batch-scores-export` invoked
                   `export_batch_scores.py` directly, bypassing the wrapper's
                   `RQ105_SCORE_SOURCE=blend` default; the repo's installed plist was
                   already correct (wrapper), so only the manifest was the stale
                   entry point.
    best-known?:   the pre-fix manifest was the worse (stale) variant — it diverged
                   from the already-fixed plist. The post-fix manifest matches the
                   verified-correct plist (`/bin/zsh` + `run_batch_scores_export.sh`),
                   making it the current best-known scheduled config for this job.
    scope:         this is ops/launchd_manifest.json, prod, vs the existing correct
                   entry point already present in the repo's plist — drift scan now
                   reports **0** drift lines for this job, and the suite is 52/52
                   (51 pre-existing + the new invariant). This EVIDENCE block covers
                   the manifest/plist alignment claim only; it does NOT yet cover
                   whether the scheduled export actually emits `score_source: blend`
                   — that is the open item in NEXT below.

          Two things I got wrong on the way, recorded because they cost time:
          * My first fix moved the default INTO the module. Baseline was 51/51; that
            change broke 19 tests, because the suite legitimately exercises the prod
            path without setting the env. The module is a library — an explicit caller
            should get an explicit source — so the default belongs in the wrapper and
            what must not drift is which entry point the scheduler uses. That is now
            the thing under test.
          * I wrote `/bin/bash` into the manifest while the wrapper's shebang and the
            already-installed plist both said `/bin/zsh`, and my own drift scan caught
            the mismatch I had just created. Aligned to the shebang.

NEXT:     Tomorrow's 06:15 export is the check: `score_source` must read `blend` with a
          populated `blend_component_sha256s`. Until an export proves it, this fix is
          unverified in the only environment that counts.
