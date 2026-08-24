# rq105 Stage-3 design: intraday live entries

STATUS:   design PR only — no code, no config, no deploy.
WHAT:     doc/design/2026-08-23-rq105-stage3-live-entries.md. Four-piece build
          (feature-panel persist → snapshot producer → wire existing shadow
          lane → guarded intraday entry loop), v1 admission = batch ∩ intraday,
          rollout ladder with the live flip as an explicit operator ask.

          REVISED 2026-08-24 (codex review), two additions and one CORRECTION:
          * §4a repo-ownership map. Each of the four PRs now names its target
            repo/module against the orchestrator's hard boundaries. S3-P1 goes
            to renquant-pipeline (kernel/panel_pipeline builds the served
            vectors; the orchestrator has NO feature-building code and adding
            one would implement pipeline internals here). P2/P3/P4 are
            orchestrator-owned. S3-P4's two reuse contracts are stated as
            constraints: composed from renquant_common.pipeline Task/Job/
            Pipeline, and orders leave ONLY via
            renquant_execution.alpaca_broker_port.AlpacaBrokerPort through
            live.runner's existing path — no broker-adapter code in this repo.
          * §4b(ii) names the batch artifact: the completed prior-session
            pipeline_runs row in runs.alpaca.db (run_id / run_date /
            run_bundle_json, run_type='live', bound config+artifact+watchlist
            fingerprints, joined to role='candidate' scores), loaded by the
            EXISTING intraday_session_inputs loader, which already enforces the
            previous-session leak guard twice and raises SignalLeakError. Plus
            a fail-closed rejection contract (wrong run_date, any fingerprint
            mismatch, missing/mismatched bundle digest, coverage below the
            loader's floors), each refusal recorded with the run_id refused.
          * CORRECTION §4b(i): §2 said daily_104 buys "at 13:55 ET". It is
            13:55 LOCAL (PT) = 16:55 ET [VERIFIED — the launchd plist has
            StartCalendarInterval Hour=13 Minute=55 and NO TZ in
            EnvironmentVariables, so the system zone applies; log timestamps
            agree]. That is 55 min AFTER the 16:00 ET close, not two hours
            before it — so today's batch decision does not exist during the
            session it would gate, and the v1 rule as written was not
            implementable. The batch side is necessarily T-1's decision; the
            admission rule now says so.
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
  scope:        design only — no code, no config, no deploy. Approving this
                authorizes the four implementation PRs to be WRITTEN against
                the named repos; it does not authorize any live flip, which
                §6's ladder keeps as an explicit operator ask.
NEXT:      S3-P1 first, and it is a renquant-pipeline PR (§4a), not an
           orchestrator one — the feature panel must exist before P2 can
           assemble a snapshot from it. Then P2/P3 (orchestrator), then P4.
           Each is its own PR under the ladder in §6; S3-a..S3-d gates are
           evidence-gated and the live flip stays an explicit operator ask.
           No implementation is authorized to start until this design merges.

REVIEW:    codex (haorensjtu-dev).
