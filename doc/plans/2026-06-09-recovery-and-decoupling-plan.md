# Plan: daily full-run recovery + retrain repair + umbrella decoupling

**Date**: 2026-06-09 · **Owner**: renquant-orchestrator (control panel)
**Status**: ACTIVE — each milestone below is one PR. Update status here as PRs land.

## Diagnosis (evidence, 2026-06-09)

The three priorities share one causal chain:

1. **Daily run is sell-only** because the full run HARD-fails preflight
   `P-WF-GATE` + `P-REGIME-IC`: the live primary model
   (`hf_patchtst` seed_44, promoted 2026-06-05 commit `b5f9045`) has **no
   stamped `wf_gate_metadata`** on its sidecar. The previous XGB prod artifact
   (`panel-ltr.alpha158_fund.json`) has none either (`promotion_status:
   gated_buys`). Log: `RenQuant/logs/daily_104/2026-06-09.log` — "Full live
   trader hit preflight system failure — rerunning sell-only".
2. **The stamping path is `weekly_wf_promote.sh`** (launchd
   `com.renquant.weekly-wf-promote`, last exit 1; `retrain-panel104` exits 1
   because it delegates to it). It fails twice over:
   - **Mechanical**: all 3 sim cuts crash —
     `ModuleNotFoundError: qp_contracts` at
     `renquant_backtesting/wf_gate/sim_driver.py:84`. `qp_contracts.py` exists
     only in `RenQuant/scripts/`, invisible from the `.subrepo_runtime`
     sys.path. No sim cuts → no WF Sharpe evidence → nothing to stamp.
   - **Substantive**: §5.2 sanity battery FAIL — time-shift
     `placebo_ic=+0.0359 > threshold +0.0295` on the staged weekly GBDT.
     Connects to the 2026-06-02 experiment-validity audit (leak-contaminated
     B_tuned) and the in-flight leakage-triad work. An uncommitted
     `wf_gate/runner.py` diff in renquant-backtesting (supplement-only-missing
     sanity panel columns) targets the sanity-input merge path.
3. **Decoupling**: two production jobs remain `umbrella_bridge`
   (`daily_live_runner_bridge`, `live_runner_bridge`); launchd points at
   umbrella shell scripts; ~9 native jobs still carry
   `umbrella_state_dependency`. PR #59 (readonly native live run candidate)
   merged 2026-06-09; offboard blockers/exit criteria are encoded in
   `scheduled_jobs.py` and `live-offboard-status`.

## Phase 0 — restore full daily run (ETA 2–4 days)

| # | PR (repo) | Content | Depends | Est |
|---|---|---|---|---|
| M1 | renquant-backtesting | Lift `qp_contracts.py` into `renquant_backtesting/wf_gate/`; package-relative import in `sim_driver.py`; umbrella `scripts/qp_contracts.py` becomes a shim. Test: sim-cut import smoke. | — | 0.5d |
| M2 | renquant-backtesting | Land the in-flight sanity-panel supplement fix (uncommitted `runner.py` diff): supplement ONLY missing addendum columns from the training panel; tests pin merge provenance. | — | 0.5–1d |
| M3 | RenQuant | Green `weekly_wf_promote` e2e: rerun gate vs the ACTIVE artifact. PASS → stamp `wf_gate_metadata` + regime IC on the PatchTST sidecar. Legit placebo FAIL → **decision point**: revert primary to XGB (`b5f9045` rollback), gate + stamp XGB, PatchTST back to shadow until leak-clean. Also: alerting must distinguish "gate crashed" from "gate rejected". | M1, M2 | 1d + sim compute |
| M4 | RenQuant | A5 verification: `daily_104.sh` e2e — readonly rehearsal first, then live FULL run with buys allowed; persist run bundle; close tracker A5. | M3 | 0.5d |

**Risk**: if the sanity placebo failure survives M2, M3's PASS path is blocked
and the M3 decision point (revert to XGB) is the only same-week unblock. That
is a user decision — gate evidence will be presented, not bypassed (§5.13.15).

## Phase 1 — scheduled retrain pipelines trustworthy (ETA ~1 week, overlaps Phase 0)

| # | PR (repo) | Content | Depends | Est |
|---|---|---|---|---|
| M5 | renquant-orchestrator | Scheduled-job health surface: per-launchd-job last exit, last log path, crash-vs-reject verdict; folded into `live-offboard-status`-style JSON so the control panel sees every red job. | — | 1d |
| M6 | renquant-model + renquant-common | Close the placebo/leakage question on the weekly staged GBDT: leakage-triad checks at staging time (triad sidecar preflight already in renquant-artifacts), verdict doc; closes the 2026-06-02 audit follow-up. | M2 | 2–4d (research) |
| M7 | renquant-orchestrator | Migrate training launchd entries (`retrain-alpha158-linear`, `retrain-panel104`, `weekly-wf-promote`) to `renquant-orchestrator run-job …`; inventory states updated in `scheduled_jobs.py`. | M3 | 1d |

## Phase 2 — fully decouple umbrella (ETA 2–3 weeks)

Sequence follows the offboard blockers in `scheduled_jobs.py`:

| # | PR (repo) | Content | Depends | Est |
|---|---|---|---|---|
| M8 | renquant-orchestrator | ✅ DONE 2026-06-09 — PR #59 (readonly `native_live_run_candidate`) reviewed + merged. | — | 0.5d |
| M9 | renquant-pipeline | Port live context/state adapters (`live_state.alpaca.json`, `runs.alpaca.db`) behind pipeline contracts. | M8 | 2–3d |
| M10 | renquant-execution | Port broker commit semantics (order submission + audit) out of umbrella `live.runner`. | M8 | 2–3d |
| M11 | renquant-orchestrator | Writeable native live job; buy/sell/sell-only parity vs bridge on readonly fixtures (`native_live_parity_fixture` green on prod + shadow configs). | M9, M10 | 2d |
| M12 | RenQuant + orchestrator | launchd cutover: `daily104` plist → `run-job` native; bridge kept as documented rollback ≥ 1 week. | M11, M4 | 1d |
| M13 | renquant-backtesting | wf_gate Phase-5 caller flip (tracker C5): `weekly_wf_promote` runs `python -m renquant_backtesting.wf_gate` natively from the pinned subrepo, no umbrella kernel aliasing. | M3 | 1–2d |
| M14 | renquant-base-data + orchestrator | Umbrella `data/` + artifacts staging paths behind manifests; `state_backup` fully native. | — | 2–3d |
| M15 | RenQuant | Retire the two `umbrella_bridge` jobs; umbrella reduced to pins + docs + rollback source. | M12–M14 | 0.5d |

## Totals

- **Phase 0**: 2–4 days (full daily run restored — the only correct path is a
  green, stamped WF gate; no gate bypass).
- **Phase 1**: ~1 week, parallelizable with Phase 0 except M6.
- **Phase 2**: 2–3 weeks sequential; M9/M10/M13/M14 parallelizable across
  agents → compressible to ~1.5–2 weeks.
- **End-to-end**: ~4–5 weeks single-lane; ~2.5–3 weeks with codex+claude
  swimlanes at current review cadence.

## Standing rules

- Every milestone: feature branch → `make test` green → PR → verbal approval →
  merge → advance pin in `RenQuant/subrepos.lock.json`.
- Update this doc's milestone statuses before ending a session (same contract
  as `RenQuant/doc/arch/multirepo-tasks.md`, which should gain a pointer here).

Agent-Origin: Claude
