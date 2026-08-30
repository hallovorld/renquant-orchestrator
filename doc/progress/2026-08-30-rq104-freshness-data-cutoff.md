# orch#906: rq104 freshness reads the producer's data-cutoff stamp; retrain refuses unstamped artifacts

STATUS:   delivered, two surfaces:
          (1) `model_freshness_monitor.read_artifact_freshness` resolves each
          binding axis top-level-then-`metadata` (the SAME read order the
          RFC#210 license and the axis-agreement probe already use; a nested
          bind is recorded as `metadata.<field>`), echoes the trainer's
          `feature_cutoff_date` as provenance-only, and widens the
          CONDITIONALLY lagged axes (`effective_train_cutoff_date`,
          `data_cutoff_date`) by the artifact's OWN validated stamped
          `lookahead_days` — absent/invalid stamps apply NO widening
          (raw-age tiering, conservative) and never a guessed default.
          `DATA_CUTOFF_FIELDS` itself is unchanged (probe + job_universe
          mirrors stay in agreement).
          (2) `retrain_alpha158_fund._validate_scorer_artifact` fails closed:
          it refuses an artifact without parseable
          `metadata.data_cutoff_date` + `metadata.feature_cutoff_date`, a
          data cutoff that postdates `trained_date`, or a top-level
          `effective_train_cutoff_date` disagreeing with the metadata stamp.
WHY/DIR:  the daily `RenQuant 104 model freshness UNKNOWN` alert (#906, the
          precondition #745's 28-day ceiling waits on, #941's prod-panel
          axis): the panel producer stamped no binding cutoff and the monitor
          fails closed by design. Producer fix = renquant-model PR (stamps
          `metadata.data_cutoff_date` MEASURED from the training frame);
          this PR makes the monitor able to READ that stamp and makes the
          retrain lane refuse to ever produce another unstampable artifact.
          Conditional (stamped-only) widening is what keeps a fresh fwd-60d
          retrain from reading born-BREACH on its ~60-BD label lag (the #423
          round-3 semantics) without borrowing an allowance for recipes that
          deliberately stamp no horizon (the momentum ledger's skip is an
          embargo, not a horizon).
EVIDENCE:
  artifact:      monitor: `_artifact_field` resolver, `_STAMPED_HORIZON_AXES`,
                 `feature_cutoff_date` provenance echo; retrain: stamp
                 validation. +8 monitor tests (nested bind, field-major
                 priority, top-level-wins, stamped widening, invalid-stamp
                 no-widening, provenance-never-binds, frozen-still-breaches)
                 and +7 validator tests. Full affected suites green,
                 including the axis-agreement mirror tests
                 [VERIFIED — pytest run 2026-08-30].
  prod or exp:   exp — the alert resolves only after: model PR merged →
                 weekly retrain produces a stamped artifact → it is promoted.
                 The SERVED 08-02 fallback artifact stays UNKNOWN by design
                 (its cutoff is genuinely unknowable from the receipt).
  existing data: served artifact: 0/6 binding axes, `metadata` carries only
                 promotion/fallback keys [VERIFIED — json.load 2026-08-30];
                 monitor UNKNOWN branch confirmed at
                 `read_artifact_freshness` (fail-closed by design).
  best-known?:   yes — fail-closed at the producer gate + readable stamps at
                 the monitor; no axis-order change, no policy-threshold
                 change (28d fast-axis SLA untouched).
  scope:        monitor read path + one validator + tests. No production
                path written; no launchd/manifest change; the daily job runs
                the same module.
MERGE ORDER: renquant-model `fix/panel-data-cutoff-stamp` FIRST — until it
           lands in the sibling checkout, `_validate_scorer_artifact` will
           (correctly, loudly) fail the weekly retrain lane on unstamped
           artifacts. Related pipeline PR (P-MODEL-STALENESS momentum ledger
           reader) is independent.
REVIEW:    codex (haorensjtu-dev).
