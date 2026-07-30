# Progress: the GBDT trainer now stamps the cutoff the WF gate requires

STATUS:   delivered. Metadata only — the booster is byte-identical, proved on
          the real production panel (below). No production surface touched: no
          pin advanced, no config, no calibrator, no live artifact rewritten.

WHAT:     `src/renquant_orchestrator/train_gbdt.py` — new
          `StampTrainingContractTask` (+ the pure helper
          `last_label_complete_date`) closes the data-prep sequence in BOTH
          pipeline variants and stamps:

            * `effective_train_cutoff_date` (payload ROOT) — the last date
              whose label was actually observable in the training slice:
              `max(date)` over rows with a non-null label column.
            * `metadata.training_contract` — `{dataset, label_col,
              lookahead_days, n_rows, last_label_complete_date,
              effective_train_cutoff_date, effective_train_cutoff_source,
              derivation}` (+ `train_cutoff_date` on the fold path).

WHY:      `[VERIFIED-prior — this session's WF-gate run]` The gate refuses to
          statically evaluate the candidate because
          `_effective_artifact_cutoff` returns `None`
          (`renquant-backtesting/src/renquant_backtesting/wf_gate/runner.py:1915`,
          consumed at `:1939` `_validate_static_sanity_oos_contract` and
          `:1975` `_validate_static_wf_oos_contract`): *"static sanity missing
          effective training cutoff; trained_date is wall-clock metadata and
          cannot prove OOS label separation"*. The refusal is CORRECT. The gap
          was upstream: `[VERIFIED-now]` `train_gbdt.py:190-192` gives
          `cutoff_date` a value ONLY when `--train-cutoff` is passed (and that
          flag requires `--side-label`), so a walk-forward FOLD run got a
          cutoff stamped by `renquant_model_gbdt/panel_data.py:250-258` while
          the full-panel production retrain stamped none — leaving the only
          scope that could evaluate a universe or data change unreachable.
          There is no existing cutoff to thread on that path; the panel itself
          is the only honest source.

WHERE:    `[VERIFIED-now]` The artifact metadata dict is built in the model
          pin, NOT here: `renquant-model/src/renquant_model_gbdt/panel_trainer.py:246`
          `build_model_artifact` (dict literal at `:272`), called from
          `renquant-model/src/renquant_model_gbdt/pipeline.py:139-151`
          (`BuildArtifactTask`), which applies the driver's injected fields with
          `artifact.update(ctx.extra_artifact_fields)` at `:150`.
          `extra_artifact_fields` is the sanctioned driver-side channel (the
          orchestrator's own `SentimentGateTask` already uses it), so the stamp
          lands here without reaching into model internals.

CONSUMER  `[VERIFIED-now]` Fields matched against the consumer, not invented:
MATCH:      * `_effective_artifact_cutoff` reads six aliases;
              `effective_train_cutoff_date` is first AND is the only one of the
              six classified in `renquant_common.model_fingerprint`
              (`OPERATIONAL_KEYS`) → stamping it leaves the v1 model-content
              hash unchanged. It is also the same field name the fold path
              already stamps, so one field means one thing everywhere.
            * `lookahead_days` (the gate's other input, `runner.py:1946`) was
              already stamped by `build_model_artifact` — untouched.
            * `training_contract` is the PatchTST-sidecar schema
              (`runner.py:645`, `artifact_loader.py:47`, `:2485`
              `training_contract.dataset`). Two verified reasons it is nested
              under `metadata` instead of the root:
                1. `[VERIFIED-now]` a top-level `training_contract` is
                   UNCLASSIFIED in renquant-common's total-classification
                   table, so `model_content_sha256` raises
                   `UnclassifiedKeyError` — reproduced:
                   `model_content_sha256({...,'training_contract':{...}})` →
                   `UnclassifiedKeyError`. That hard-fails this trainer's own
                   content-fingerprint path (`--strategy-config none`, used by
                   research mode + `tests/test_train_gbdt_native.py`), and the
                   legacy 0.8.1 denylist hash would silently change too
                   (`training_contract` is NOT in `MUTABLE_ARTIFACT_KEYS`).
                   Promoting it to the root is a renquant-common
                   classification change owned by the model repo, with a
                   `FINGERPRINT_SCHEMA_VERSION` policy attached — deliberately
                   not smuggled into an orchestrator PR.
                2. A root `training_contract.dataset` would ALSO switch the
                   gate's sanity panel from the rawlabel panel to the training
                   panel (`runner.py:2485` → `_load_sanity_panel`) — an
                   evaluation-behaviour change far beyond stamping a cutoff.
              `metadata` is classified OPERATIONAL in v1 and denylisted in the
              legacy hash → the nested record is hash-neutral in BOTH
              implementations. `attach_inference_smoke` uses
              `artifact.setdefault("metadata", {})`, so pre-seeding it is safe
              and the smoke fields still land.

FOLD PATH `[VERIFIED-now]` When `--train-cutoff` IS supplied, `LoadPanelTask`
CONSISTENCY: has already stamped `cutoff_date - embargo BDays`. That value is
          KEPT (the fold contract the manifest/loader is bound to) and the
          derived date is recorded beside it; if the data's last label-complete
          date is AFTER the declared cutoff the task RAISES
          ("training-contract disagreement") rather than stamping a cutoff the
          training data contradicts. The two cannot disagree silently.

BOOSTER   `[VERIFIED-now]` Full production invocation (real
IDENTITY: `RenQuant/data` panel, pinned strategy config, sentiment gate ON, CV
          on), run twice — once on `origin/main` (24433515), once on this
          branch, same machine, sequential:
            sha256(booster_raw_json) base   = c2c2b80c3b418bf68d8dff21da2d8e711810026e1d3aaa850074bb810af981f6
            sha256(booster_raw_json) branch = c2c2b80c3b418bf68d8dff21da2d8e711810026e1d3aaa850074bb810af981f6
            IDENTICAL
          `feature_means`, `feature_stds`, `panel_shape`, `training_train_ic`,
          `oos_mean_ic`, `oos_per_fold_ic`, `params`, `feature_cols`,
          `sentiment_runtime_gate_zeroed_rows` and `config_fingerprint` all
          equal; the branch artifact adds exactly
          `effective_train_cutoff_date` at the root plus
          `metadata.training_contract`. Log:
          `scratchpad/ab_identity_a7f3.log`. The branch artifact still passes
          `renquant_artifacts.validate_panel_artifact_contract(strict=True)`
          (base ok=True, branch ok=True, no errors).

GATE      `[VERIFIED-now]` Run against the gate's own resolver on the two real
END-TO-   artifacts produced above:
END:        base   `_effective_artifact_cutoff` → None → static sanity
                   `passed=False`, "static sanity missing effective training
                   cutoff; trained_date is wall-clock metadata …"
            branch `_effective_artifact_cutoff` → 2026-05-01 → static sanity
                   `passed=True {cutoff 2026-05-01, lookahead_days 60,
                   safe_last_label_date 2026-07-24}` for eval_start 2026-08-01,
                   and still `passed=False` for eval_start 2026-06-01 with the
                   arithmetic spelled out ("2026-05-01 + 60BDay = 2026-07-24 >=
                   2026-06-01").
          The refusal is LIFTED where the labels are genuinely separated and
          KEPT where they are not. Nothing was loosened.

TESTS:    13 new, all behavioural (no source grepping):
          `tests/test_train_gbdt_native.py`
            * `test_stamped_cutoff_is_the_last_label_complete_date` — synthetic
              panel whose last LABEL-complete date (25th) differs from its last
              FEATURE date (40th); asserts the stamp is the constructed answer
              and that the WF gate's own `_effective_artifact_cutoff` resolves
              it off the payload root.
            * `test_wf_fold_stamp_stays_consistent_with_train_cutoff` — the
              fold stamp is still `cutoff - 60 BDay`, and the derived date sits
              strictly inside it.
            * `test_stamp_is_metadata_only_booster_byte_identical` — the
              load-bearing one: trains the same inputs through renquant-model's
              stamp-free `build_training_pipeline()` (the pre-change path) and
              through the driver, asserts identical `booster_raw_json`,
              normalization, `panel_shape`, `training_train_ic` AND
              `config_fingerprint`.
          `tests/test_train_gbdt.py` — helper + task units: null-label /
          missing-column / no-frame None-safety (unstamped, no crash), the
          derived stamp, fold-path recording, the disagreement raise, and
          "does not mutate the training frame".
          Falsifiability checked by mutation: making the helper ignore
          null-ness fails 3; letting the task touch `ctx.train` fails 4
          (including the booster-identity test).

SUITE:    baseline `origin/main` (24433515, separate worktree): 1 failed,
          4448 passed, 5 skipped. Branch: 1 failed, 4461 passed, 5 skipped (+13 = the 13 new tests). The single failure is
          the same pre-existing one on both sides —
          `tests/test_cli.py::test_parking_sleeve_cli_computes_allocation`
          (`FileNotFoundError`, needs the umbrella data dir that a scratchpad
          worktree does not have). Not touched by this change.

TESTS I   6 tests in `TestMainPipelineAssembly` and 5 elsewhere patched
CHANGED:  `mod.build_training_pipeline` as their seam. `main()` now assembles
          BOTH gate variants explicitly (so the stamp cannot be missing from
          one path) and no longer calls that factory, so those patches would
          have become silent no-ops that let real training run inside a unit
          test. They now patch `mod.Pipeline` — the seam
          `test_sentiment_gate_pipeline_structure` already used. Every
          assertion is preserved; the two structure tests additionally pin
          `StampTrainingContractTask`'s position. This is a test pinning the
          pre-change COMPOSITION, not the absent-metadata behaviour: no
          assertion about the artifact was relaxed.

KNOWN     `[VERIFIED-now]` Two downstream readers see a value where they used
EFFECTS:  to see nothing. Both are disclosed, neither is a trading gate:
            * `renquant-orchestrator/model_freshness_monitor.py:145`
              `DATA_CUTOFF_FIELDS` — the prod panel currently reports
              `TIER_UNKNOWN` ("binding data cutoff unknown", fail-closed at
              breach severity, exit 3) because no cutoff field exists. It will
              now report a MEASURED age instead. For a fwd_60d model that age
              is ~60 business days by construction, i.e. > the 28d
              `DEFAULT_BREACH_DAYS`, so the tier becomes `breach` with a real
              number. Severity/exit code unchanged (`_TIER_EXIT_CODE`:
              unknown=3, breach=3); the headline "worst tier" actually improves
              (`unknown` ranks above `breach`). The monitor already has the
              right home for a label-clipped axis —
              `label_observation_cutoff`, the ONLY axis with expected-lag
              compensation (`_AXIS_EXPECTED_LAG_BDAYS`) — but that key is
              UNCLASSIFIED in renquant-common, so stamping it needs the same
              model-repo classification change. FOLLOW-UP, not silently done
              here.
            * `renquant-pipeline .../preflight_pipeline/tasks/staleness.py:89`
              P-MODEL-STALENESS (SOFT, warn-only) currently reports the
              provenance gap "effective_train_cutoff_date unstamped — decay
              curve rail unmeasurable"; it becomes measurable.
            * `renquant-pipeline .../walk_forward/lean_guard.py:33` —
              `_selection_anchor` will prefer the stamped cutoff over
              `trained_date` for LEAN BACKTESTS only (`is_live_mode` returns
              early). That is the intended direction: an evidence-based data
              anchor replacing a wall-clock one.
          `[VERIFIED-now]` NOT affected: `job_universe.FilterStalenessTask`
          (the fail-closed offensive-buy freshness gate) reads per-ticker
          artifacts from `strategy_dir/models/<ticker>` (`LoadArtifactsTask`),
          never the panel artifact.

NEXT:     The gate can now be asked to evaluate a full-panel candidate at all.
          Whether it PASSES is a separate question and is not claimed here.
