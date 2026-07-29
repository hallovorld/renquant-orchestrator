# Progress: rq105 blend landed on operator grant; and a runtime-checkout drift I must not clear myself

STATUS:   two items. (1) rq105 blend export LANDED and VERIFIED — durable
          record + literal revert steps below. (2) A run-surface drift found
          by the scan needs an OPERATOR decision, because clearing it requires
          a git operation in the live tree that I am forbidden from running.

## 1. rq105 blend export — landed under explicit operator grant

WHAT:     Operator directive 2026-07-29 ("105不等，马上开始上线"). Forced the
          scheduled export to run immediately rather than waiting for its next
          06:15 window, because the wrapper fix had landed 14 minutes AFTER
          that morning's run (plist switched 06:29:53; the run executed
          06:15:04) and the job fires once per weekday.

          `launchctl kickstart -k gui/<uid>/com.renquant.rq105-batch-scores-export`

          This OVERWROTE the day's production export
          (`data/rq105/batch_scores_2026-07-29.{json,meta.json}`), which is why
          it needed a grant and why it is recorded here.

VERIFIED (both acceptance criteria, measured after the run):
          score_source                 = "blend"            (was "prod")
          scorer_identity.blend_component_sha256s = 2 components:
            components[0].artifact_path = sha256:04d7a381cd6df84721d…  (XGB)
            components[1].artifact_path = sha256:1e644354e0981f470d1…  (clf)
          broker_mode = alpaca_shadow_blend, training_cutoff = 2026-06-21,
          n = 85, coverage = 1.0, launchd runs = 1, last exit code = 0.

          NOTE ON MY OWN CHECK: the first verification read a TOP-LEVEL
          `blend_component_sha256s` and reported it absent. It is nested under
          `scorer_identity`. I nearly published a false failure; the criterion
          passes.

REVERT (literal, if the blend export must be undone):
          cp <scratch>/rq105-backup-20260729/batch_scores_2026-07-29.json \
             /Users/renhao/git/github/RenQuant/data/rq105/
          cp <scratch>/rq105-backup-20260729/batch_scores_2026-07-29.meta.json \
             /Users/renhao/git/github/RenQuant/data/rq105/
          The pre-overwrite files were snapshotted BEFORE the kickstart
          (both dated 06:15, score_source="prod").
          To revert the LANE rather than the file, set
          `RQ105_SCORE_SOURCE=prod` in the job environment — the wrapper reads
          `${RQ105_SCORE_SOURCE:-blend}`, so an explicit value wins.

NO DRIFT INTRODUCED: `ops/launchd_manifest.json` already pins this job to the
          wrapper (orch#599), and the loaded-vs-disk check (orch#603) reports
          the job running its on-disk definition. The landing changed an
          OUTPUT, not the reviewed surface.

## 2. Run-surface drift: the pinned renquant-model runtime carries a modified README

FOUND BY: `ops/run_surface_drift_check.py` —
          `runtime/renquant-model: 1 uncommitted tracked change(s): M README.md`

WHAT IT IS: `README.md`'s auto-generated `LATEST_MODELS` table, regenerated in
          the PINNED runtime checkout
          (`.subrepo_runtime/repos/renquant-model`, HEAD 5ef1c2d). Only that
          one file; `git status --porcelain` shows nothing else and no
          untracked paths.

WHEN:     File mtime 2026-07-28 23:57:42 local, matching the table's own
          `last refreshed: 2026-07-29T06:57:42Z` — the same instant in UTC. I
          initially read the UTC stamp as a local morning time and had to
          correct that before concluding anything.

WHO:      Not a launchd job — no plist references `refresh_readme`. The
          timestamp matches training run `20260729065741-hf_patchtst-d3a535`
          exactly, so a manually-triggered trainer refreshed the table as a
          side effect of running inside that checkout.

WHY IT MATTERS beyond a doc table: the content is harmless, the MECHANISM is
          not. A trainer that writes into whatever checkout it is invoked from
          will write more than a README when it is invoked somewhere else.
          This is the 2026-07-16 class — a run checkout silently diverging
          from its reviewed ref — caught this time while still cosmetic.

WHY I DID NOT CLEAR IT: restoring the file means `git checkout -- README.md`
          inside the live runtime tree. Agents must not run git in the live
          tree (HARD rule, after the 2026-06-25 near-miss where a sub-agent's
          `git reset --hard` hit a shared live checkout). The drift scan
          alarming daily on this is the DESIGNED reminder; silencing it by
          editing the manifest would be exactly the wrong move.

OPERATOR DECISION NEEDED: either (a) run
          `git -C /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-model checkout -- README.md`
          yourself, or (b) tell me the runtime checkout is an accepted
          scratch surface for generated docs, in which case the scan needs a
          reviewed exclusion rather than a silent one.

## 3. Incidental measurement — fresh PatchTST vs XGB, from the regenerated table

The table the drift consists of carries the trainer's own self-reported OOS IC.
Reporting it because it bears directly on "is the new PatchTST any good", with
the caveat that this is the TRAINER's number, not an independent walk-forward
evaluation, and not comparable to the corpus work:

    hf_patchtst        2026-07-29  +0.0102   (172 feat, 145 tickers, 5ef1c2d)
    hf_patchtst        2026-07-29  +0.0101
    hf_patchtst        2026-07-25  +0.0257
    hf_patchtst        2026-07-23  -0.0569 / -0.0439 / +0.0143
    panel_ltr_xgboost  2026-07-26  +0.0568
    panel_ltr_xgboost  2026-07-25  +0.0449

Freshly trained PatchTST sits near +0.01 while XGB sits at +0.045-0.057 on the
same feature count — a 4-5x gap on the trainer's own metric.

EVIDENCE: artifact: `data/rq105/batch_scores_2026-07-29.meta.json` (post-run),
                    `launchctl print gui/<uid>/com.renquant.rq105-batch-scores-export`,
                    `ops/run_surface_drift_check.py` output,
                    `.subrepo_runtime/repos/renquant-model` @ 5ef1c2d.
  prod or exp:      PROD. Item 1 deliberately overwrote a production output
                    under an explicit operator grant; item 2 observed a
                    production checkout READ-ONLY and changed nothing.
  existing data:    Yes, all measured this session: the meta fields above, the
                    launchd counters, the porcelain status, the file mtime,
                    and the OOS IC table.
  best-known?:      Yes for items 1 and 2. Item 3 is the trainer's own metric
                    and is explicitly NOT an independent evaluation.
  scope:            Record only. No pin advanced, no umbrella change, no
                    manifest edit, no live-tree git operation.

NEXT:     Operator decides on the §2 drift. The scan will keep alarming until
          it is either cleared or legitimized in review — by design.
