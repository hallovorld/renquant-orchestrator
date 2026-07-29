# Progress: the 105 blend switch shipped and stayed dark for a day

STATUS:   delivered (manifest + repo plist aligned to the installed reality, plus an
          invariant test). The scheduled job now goes through the wrapper.

WHAT:     `ops/launchd_manifest.json` now pins
          `com.renquant.rq105-batch-scores-export` to
          `/bin/zsh .../run_batch_scores_export.sh` instead of invoking
          `export_batch_scores.py` directly, plus a test asserting the scheduled entry
          point is the wrapper. NOTE (codex, non-blocking): the repo PLIST was already
          on the wrapper in origin/main — this patch changes the MANIFEST only, and my
          earlier wording claiming both was wrong.

WHY/DIR:  `RQ105_SCORE_SOURCE` defaults to **blend** in the wrapper and to **prod** in
          the module. The scheduled job called the module DIRECTLY, so the blend switch
          — merged, correct, and verified by hand — never reached the only path that
          matters.

EVIDENCE:
artifact:      `data/rq105/batch_scores_2026-07-29.meta.json` (the 06:15 scheduled
               export, live path) and a scratch-redirected re-run of the same exporter
               with `RQ105_SCORE_SOURCE=blend`; `ops/launchd_manifest.json`;
               `ops/renquant105/run_batch_scores_export.sh` vs
               `ops/renquant105/export_batch_scores.py`.
prod or exp:   PROD — this is the live 105 serving vector and the live launchd surface.
               The verification re-run was redirected to a scratch directory and did
               NOT write any production path.
existing data: the scheduled export wrote `score_source: prod`,
               `source_db: runs.alpaca.db`, `blend_component_sha256s: {}` — a full day
               after the blend switch merged. The wrapper defaults
               `RQ105_SCORE_SOURCE` to blend; the module defaults it to prod; the job
               called the module. The scratch re-run through the blend path produced
               "85/85 frozen blend scores (coverage 100.0%) from
               2026-07-28-live-735c7e9b" with `score_source: blend`,
               `source_db: runs.alpaca_shadow_blend.db` and both component digests
               populated (`sha256:04d7a381...` plus the clf leg).
best-known?:   n/a — this is a wiring defect, not a competing model or signal variant.
               No IC, Sharpe or return number is claimed anywhere in this PR, so the
               §4(b) sanity triad has no applicable comparison.
scope:         the claim is scoped to WHICH entry point the scheduler invokes and what
               the resulting vector's identity block contains, on this machine, for
               session 2026-07-29. It does NOT claim the scheduled job now reaches the
               blend path — that remains unverified until the next 06:15 run.


PATH VERIFIED, SCHEDULER NOT — the distinction matters and is kept explicit.

          **Verified now** `[VERIFIED — wrapper-equivalent invocation with
          RQ105_SCORE_SOURCE=blend, output redirected to a scratch dir so the live
          vector was NOT touched, 2026-07-29]`: the blend path exports
          "85/85 frozen blend scores (coverage 100.0%) from 2026-07-28-live-735c7e9b",
          and its meta reads `score_source: blend`, `source_db:
          runs.alpaca_shadow_blend.db`, with `blend_component_sha256s` POPULATED for
          both components (prod panel-ltr `sha256:04d7a381…` plus the clf leg). So the
          code was never the problem — only which entry point the scheduler used.

          **Deliberately NOT done**: replacing today's live vector. Today's serving
          replay may already have consumed the prod-sourced one, and swapping it
          mid-session would leave 2026-07-29 half prod and half blend in the record.
          Today stays an honest prod day.

          **Still unverified**: that the launchd job now reaches this path. Only the
          06:15 run can show that, and no amount of manual invocation substitutes for
          it — which is precisely the error this PR exists to correct.

NEXT:     Check tomorrow's 06:15 export meta: `score_source: blend` with a populated
          `blend_component_sha256s`.
