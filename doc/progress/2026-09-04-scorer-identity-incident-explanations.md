# Scorer-identity monitor: a recorded incident explains exactly one boundary   (PR #1116)

STATUS:    delivered — G-A (stop a standing page by recording its cause, not
           by loosening the guard).
WHAT:      `scorer_identity_monitor.py` gains a committed registry
           `ops/renquant104/scorer_identity_incident_explanations.json`
           (schema v1) of RECORDED incidents, each bound to exactly one
           run-over-run boundary: lane key + both run ids (exact) + both
           stamped digests (prefix-bound, ≥ 16 hex, the receipt rule) +
           reason / evidence / recorded_by / recorded_at. `explain_boundary`
           gets a third pass (after receipts and the ledger-append rule): an
           unexplained same-lane swap that a record names becomes explained
           with the record as its note; lineup changes are not eligible.
           The loader accepts no wildcard or blank field and loads NOTHING
           from a missing/malformed registry (fail closed: the CRITICAL
           stands). CLI `--incident-explanations PATH` (default: this
           package's committed file; `/dev/null` disables); threaded through
           `build_report`, `evaluate`, `build_backfill_lines`, `format_timeline`.
           One entry shipped: the 2026-08-31 momentum-ledger truncation
           (`shadow:…/artifacts/momentum/momentum_artifact_ledger.jsonl`,
           `2026-08-31-live-ba1899f8` → `2026-08-31-live-5a0c9139`,
           `sha256:a1149c56…` → `sha256:9aa2d8c9…`). 9 tests.
WHY/DIR:   2026-08-31 07:17:50 PDT the live-tree pull reset the git-tracked
           momentum ledger from 5 rows to its committed 1-row revision
           (RenQuant#638 untracks it). The monitor's explanations are
           promotion receipts, rollback markers, and link-intact ledger
           APPENDS — a same-path truncation can never satisfy any of them,
           so the boundary is unexplainable by construction and the monitor
           re-pages it CRITICAL on every full run: 2026-09-04 14:30 was the
           first full run after the incident (09-01..03 aborted at
           preflight) and it paged the 08-31 boundary again. A monitor that
           pages the same diagnosed incident daily is the "247 rows since
           birth were CRITICAL" saturation its own docstring warns about —
           the page stops being read, and a genuine swap would ride inside
           it. The fix records the diagnosis where the monitor can read it,
           bound so tightly that it can explain nothing else; the file is a
           reviewed surface, so every future entry is a PR.
EVIDENCE:  artifact:      `RenQuant/logs/rq104/scorer_identity_2026-09-04.log` lines 2–6 (`CRITICAL: shadow:…momentum_artifact_ledger.jsonl: a1149c566670 -> 9aa2d8c9571b between 2026-08-31-live-ba1899f8 and 2026-08-31-live-5a0c9139 with NO recorded …`); the ledger file: mtime 2026-08-31 07:17:50, 1 row, sha256 prefix 9aa2d8c9571b, unchanged since [VERIFIED — read 2026-09-04 14:5x PDT]; the two runs' stamped digests read from `data/runs.alpaca.db` `run_bundle_json` (`ranking.panel_scoring.components[1]` / `shadow_models[1]`): `sha256:a1149c5666703b4525f352806acd5abf48d92d54d5f4c012d7448ebfe098f086` (14:12:25 UTC) → `sha256:9aa2d8c9571bad950ed9dc50e4437504503be233a5be581b5df39bea65a047e6` (14:24:37 UTC) [VERIFIED — read-only sqlite, 2026-09-04 ~15:05 PDT]
           prod or exp:   prod ops monitor (classification + page text of one historical boundary); no artifact, config, or ledger touched
           existing data: `tests/test_scorer_identity_incident_explanations.py` 9 passed + `tests/test_scorer_identity_monitor.py` 56 passed = 65 passed [VERIFIED — 2026-09-04 between 15:00 and 14:55 PDT]; read-only proof on the LIVE runs DB (no --notify, monitor run from this worktree's src): with `--incident-explanations /dev/null` → `scorer_identity_check: critical - CRITICAL: shadow:…momentum_artifact_ledger.jsonl: a1149c566670 -> 9aa2d8c9571b between 2026-08-31-live-ba1899f8 and …`; with the shipped registry → `scorer_identity_check: ok - 3 explained identity boundary(ies) across 176 runs; scorer identity stable across 176 runs (2026-08-28-live-83d6e1a8 .. 2026-09-04-live-130d3459); prod panel f1b1c1322e3b (trained 2026-08-31 …)` and the 08-31 boundary line reads `INFO: … explained by [incident recorded 2026-09-04 …]` [VERIFIED — same window]
           best-known?:   n/a — ops truth; no model claim
           scope:         "this changes how ONE recorded boundary is classified; the record cannot match any other transition; the monitor's receipt/ledger/rollback rules are unchanged"
NEXT:      after merge + `-run` sync: the next full run's 14:30 monitor reports
           the 08-31 boundary as INFO (explained by the record) and pages only
           if a NEW boundary appears. Follow-up: the truncated ledger's four
           rows stay lost (they carry input digests; not reconstructed); the
           Saturday 2026-09-05 refit appends from the surviving tail row and
           that append is explained by the existing ledger rule.
