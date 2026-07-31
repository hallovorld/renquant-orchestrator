# Schedule the model-freshness monitor — Pillar 1 shipped in June, never fired

**Date:** 2026-07-30 · GOAL-5 (daily-run reliability P0) · orchestrator

**Bottom line:** `model_freshness_monitor.py` is the Phase-1 deliverable the
2026-06-30 governance design (RFC #210) says "ships now". It is complete. It has
**never run** — one CLI call site, zero of the 40 manifest jobs, zero output files
ever written `[VERIFIED — grep over src/ ops/ scripts/ + launchd_manifest.json +
find over logs/ state/, 2026-07-30]`. Run observe-only today it exits **3** with
**two populations in genuine breach**. This PR lands the reviewed surface; the
plist install is a separate authorised step and is NOT done here.

## 1. What the monitor says today

`PYTHONPATH=src python -m renquant_orchestrator.model_freshness_monitor --json
--quiet`, real process exit **3** `[VERIFIED — run this session, 2026-07-30]`:

| population | tier | measured | rail |
|---|---|---|---|
| tournament | **breach** | 141/142 present, age min/med/max = **37/37/37d**, missing `SPY` | 28d |
| shadow-panel | **breach** | `effective_selection_cutoff_date=2026-02-10`, age **170d**; receipt has no `promoted_pin` (fail-closed) | 35d |
| prod-panel | **unknown** | binding data cutoff **unstamped** → fail-closed | 28d |

Thresholds are the monitor's own, not asserted here: fast axis warn 14 / escalate
21 / breach 28; shadow warn 28 / escalate 33 / breach 35 `[VERIFIED — `thresholds`
block of the same JSON]`.

## 2. A correction I owe the record

I reported to the operator earlier today that "the model is **39 days old**
against a 28-day policy". That number used **`trained_date`**, and the monitor
**explicitly refuses that axis**: *"trained_date=2026-06-21 is informational only,
not a freshness axis"* — because a fresh build over stale data is not fresh
(design §2). The correct axis is the binding **data cutoff**, and for the prod
panel it is **unstamped**, so prod-panel freshness today is **not 39 days, it is
unmeasurable**. The real breaches are the tournament (37d) and the shadow panel
(170d). `[VERIFIED — monitor JSON, `prod_panel.detail`]`

This is the same unstamped-cutoff gap that orch#620 and backtesting#86/#87
address on the WF-gate side. Same missing stamp, two different consumers.

## 3. What this PR does — and deliberately does not

**Does:** a wrapper (`ops/renquant104/run_model_freshness_monitor.sh`), the plist
template, the `launchd_manifest.json` entry, 10 tests.

**Does NOT:** install the plist (machine landing — needs operator authorisation),
and does **not** lower `model_staleness_days` 60 → 28. Design §5 defers that
ceiling until a validated remediation path exists, on the explicit ground that
*tightening a gate before a validated remediation path exists makes gating
strictly worse*. Scheduling the monitor is not the ceiling, and
`test_the_wrapper_stays_observe_only` +
`test_exactly_one_python_command_runs_and_it_is_the_monitor` pin that the wrapper
runs the monitor and nothing else.

**Expected transient:** until the plist is installed, the liveness scan will
report this label `UNJUDGEABLE_NO_PLIST`. That reading is **correct** — a reviewed
job exists that is not running — and the manifest entry carries a
`_pending_install_comment` saying not to silence it by deleting the entry.

## 4. Schedule choice

Weekdays **05:45**, 20 minutes ahead of the dawn funnel preflight (06:05) and
~8h ahead of the 13:55 daily. A freshness verdict arriving after the funnel probe
cannot inform it; `test_the_schedule_lands_before_the_dawn_preflight` pins the
ordering rather than leaving it to a comment.

## 5. Three wrong-object defects, in my own tests, caught before push

Logged because this is the recurring shape on this programme and the fix pattern
is reusable:

1. `test_the_wrapper_stays_observe_only` scanned **the whole file** and failed on
   the wrapper's own header, which *names* the mutations it promises not to do.
2. Stripping comments still failed on an `echo` whose printed text says
   "promotes/fits/retrains nothing". **Prose mentioning a mutation is not a
   mutation.**
3. Filtering invocations on the substring `python` counted `PYTHON=...` and
   `export PYTHONPATH=...` as commands — 3 "runs" where the shell executes 1.

Each was fixed by narrowing the test's **subject** to the executed command set,
not by softening the banned list. `test_the_observe_only_check_is_not_vacuous` is
the anti-vacuity control: a filter bug returning `[]` would otherwise make both
guards pass forever.

The manifest digest is likewise **re-derived** with the drift scan's own
`program_args_digest`, never transcribed — a hand-typed hash that drifts from its
own `program_args` makes the drift scan compare a stale constant and pass forever.

## 6. Suite

`tests/test_model_freshness_job_surface.py` — **10 passed**
`[VERIFIED — pytest, this session]`.

## 7. Next

- Operator authorisation to `launchctl bootstrap` the plist (machine landing).
- The two breaches are real and need their own owners: the tournament at 37d, and
  the shadow panel at 170d with an unbound promotion receipt.
- Stamping a binding data cutoff on the prod panel artifact is the shared unblock
  for this monitor and the WF gate.
