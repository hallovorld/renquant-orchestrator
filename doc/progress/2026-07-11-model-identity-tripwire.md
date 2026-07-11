# model-identity regression tripwire — #484 fix C

STATUS:   done (new module, DARK by default; wire-ready, no scheduled job invokes it).
          Round 2 after Codex CHANGES_REQUESTED on #485 (see REVIEW below).
WHAT:     `model_identity_tripwire` (sibling of the #480 outage monitor, same headline
          vocabulary) compares the latest run bundle's `artifact_hashes.panel` against
          (a) the previous session's bundle and (b) the AUTHORIZED identity binding —
          a new `expected-model-identity.json` record in the neutral R-PIN state root
          (sibling of `expected-generation.json`; FORWARD-ONLY, atomic write, refuses
          generation decreases and same-generation re-binds; identical re-record is
          idempotent). The deploy/promote flow records the panel sha it deploys via
          `--record-expected` (or `record_expected_identity()`); an optional
          promotions ledger is the second binding source. The #477 deployment manifest
          supplies DIAGNOSTIC metadata only (generation, deployed_at, plus a
          generation-vs-durable-record check that adds a DEGRADED note on
          stale/replayed/torn state). CLI:
          `renquant-orchestrator identity-tripwire --bundle-dir … [--offline]
          [--record-expected]`.
CONTRACT: | case | verdict | page |
          |---|---|---|
          | same sha as prev session, binding matches/absent | `identity_unchanged` | none (INFO) |
          | changed + binding names the NEW sha | `explained_pin_advance` | none (INFO) |
          | changed + sha in promotions ledger | `explained_promotion` | none (INFO) |
          | serving sha contradicts the binding (changed or not) | `identity_binding_mismatch` | OUTAGE, prio 5, exit 2 |
          | changed + no binding + no promotion (06-25 shape) | `unexplained_identity_change` | OUTAGE, prio 5, exit 2 |
          | comparison impossible (no latest identity / no prev bundle) | `coverage_lost` | DEGRADED exit 1 by default; quiet note under `--offline` |

          Absent/unreadable binding record or manifest = lost verification coverage:
          DEGRADED contribution by default, quiet under `--offline`; a DEGRADED
          contribution never downgrades an OUTAGE (worst tag wins).
WHY/DIR:  orchestrator#484 (ZM/NFLX forensics) found the prod panel artifact silently
          regressed 06-21 → 05-18 between the 06-25/06-26 sessions and served a
          39-45-day-old model for 5 sessions, unalerted — nothing existing noticed a
          DIFFERENT model was serving. This closes that detection gap the same way #480
          closed the funnel/data-availability alerting gap.
REVIEW:   Codex round 1 (CHANGES_REQUESTED) — all three points taken:
          (1) the original `deployed_at >= prev session` predicate was UNSOUND (a
          timestamp proves capture, not authorization) → replaced by the verifiable
          identity binding; manifest timestamps demoted to diagnostics; a change the
          manifest cannot explain is OUTAGE/DEGRADED, never INFO.
          (2) missing-input posture inverted: lost coverage pages DEGRADED by default;
          `--offline` is the explicit local-forensics quiet mode (`--require-inputs`
          dropped).
          (3) expected state lives under the neutral R-PIN state root with atomic
          forward-only generation semantics; torn (same-generation re-bind), rollback
          (generation decrease) and same-day-re-run (idempotent) transitions tested.
          Note: `data/strategy_snapshot.json` was never tripwire state — it is the
          repo's CLI-subcommand doc-alignment snapshot (test_doc_alignment), untouched
          by the tripwire at runtime.
EVIDENCE: `tests/test_model_identity_tripwire.py` — 34/34 passed `[VERIFIED]`: the
          06-25 regression shape alerts (with AND without a binding record); a
          recorded pin advance passes quiet; a manifest timestamp alone never explains
          a change; unchanged-but-unauthorized pages OUTAGE; missing inputs page
          DEGRADED by default and stay quiet under --offline; forward-only record
          semantics (rollback/torn/idempotent); promotions ledger; bundle discovery;
          CLI exit codes + --record-expected mode. Full repo suite: 3648 passed (2
          pre-existing environment failures — shadow-ab portable-timeout, twin-parity
          manifest-current — fail identically on clean origin/main in this
          environment).
NEXT:     (i) wiring into a scheduled job is a separate, ask-first machine landing
          (same posture as #480); (ii) the deploy/promote flow should call
          `--record-expected` after its verify step so the binding stays current —
          same landing. Fix D (fill-truth in the runs DB, pipeline-owned) ships as
          renquant-pipeline PR #190.
BOUNDARIES: read-only in check mode — consumes run-bundle JSONs + state-root records;
          never touches broker, live state, or production paths; the only write path
          is the explicit `--record-expected` maintenance mode, confined to the
          neutral state root.
