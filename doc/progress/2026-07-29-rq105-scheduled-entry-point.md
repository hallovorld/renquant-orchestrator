# Progress: the 105 blend switch shipped and stayed dark for a day

STATUS:   delivered (manifest + repo plist aligned to the installed reality, plus an
          invariant test). The scheduled job now goes through the wrapper.

WHAT:     `ops/launchd_manifest.json` and the repo's plist for
          `com.renquant.rq105-batch-scores-export` now invoke
          `run_batch_scores_export.sh` (via `/bin/zsh`, matching the wrapper's own
          shebang) instead of `export_batch_scores.py` directly. Adds a test asserting
          the scheduled entry point is the wrapper.

WHY/DIR:  `RQ105_SCORE_SOURCE` defaults to **blend** in the wrapper and to **prod** in
          the module. The scheduled job called the module DIRECTLY, so the blend switch
          — merged, correct, and verified by hand — never reached the only path that
          matters.

EVIDENCE: the first serving vector produced after the switch shipped
          `[VERIFIED — data/rq105/batch_scores_2026-07-29.meta.json, read 2026-07-29]`:
          `score_source: prod`, `source_db: runs.alpaca.db`, and
          `blend_component_sha256s: {}` — a full day after "105 is on blend". One
          contract with two homes and two values reads as merged and behaves as dark.
          After the change: drift scan reports **0** drift lines for this job, and the
          suite is 52/52 (51 pre-existing + the new invariant).

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
