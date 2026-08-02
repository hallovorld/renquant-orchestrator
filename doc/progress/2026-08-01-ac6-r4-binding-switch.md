# AC6 R4 binding switch — the daily bundle's gate-provenance block is now REQUIRED

STATUS: complete (code + tests); R4 closes for the daily-bundle path on merge.
WHAT: `_record_bundle_contract` now calls
`validate_live_run_bundle(bundle, require_gate_provenance=True)` — the per-caller
flip common#40's default-False docstring anticipates. Version skew (a
renquant-common predating the kwarg) is tri-stated `ok=None`, distinguished from
a real violation by the kwarg name in the TypeError; everything still records,
never raises, so a malformed receipt can never become a no-trade day.
WHY/DIR: R2 landed in all four gate-owning repos (pipeline#241, execution,
strategy-104#72+#74, model#112 — recorded on #564); the schema half landed as
common#40. The one gap left was that the daily persist call did not REQUIRE the
block it always writes, so a producer regression would validate clean.
EVIDENCE:
  artifact:      src/renquant_orchestrator/daily.py::_record_bundle_contract
                 (tests: tests/test_daily_bundle_contract.py)
  prod or exp:   prod — the live daily-bundle persist-time contract check
  existing data: grep of tests/test_daily_bundle_contract.py before this PR shows
                 0 tests exercised require_gate_provenance=True; this PR adds 79
                 lines / 6 binding tests (teeth test — bundle without
                 wf_gate_provenance records ok=False naming the block; skew test —
                 pre-common#40 signature records ok=None "too old", not a
                 violation; source-level test that the task emits the block)
  best-known?:   yes — first binding enforcement of R4 on the daily-bundle path;
                 supersedes the default-False flip alone (record-only, never
                 raises, so a malformed receipt cannot become a no-trade day)
  scope:         this is src/renquant_orchestrator/daily.py, prod code path, vs
                 existing behaviour (block written but not required) — 12/12
                 tests pass under RenQuant/.venv python 3.10.20 with
                 renquant-common main on PYTHONPATH; the 3.9 import crash seen
                 while probing was a false alarm (production venv is 3.10.20,
                 common declares requires-python >=3.10, CI runs 3.10)
                 `[VERIFIED — pytest 12 passed under RenQuant/.venv python
                 3.10.20, 2026-08-01]`
NEXT: operator item 6 on orch#747 (sibling sync) turns the local skips into runs;
the deployed daily run picks this up at the next run-checkout sync (#747 item 5).
AC6 gate-design rule: N/A — this PR adds no capital-admission gate; the check is
record-only on the run receipt and never raises.
