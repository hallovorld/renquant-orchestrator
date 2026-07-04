# S12 shadow freshness root-cause diagnosis

**Date**: 2026-07-04
**Master plan ref**: S12 (shadow freshness impl + panel-refresh root-cause memo)
**AC**: served pin advances via validated promote
**Status**: diagnosis — investigation steps, not a fix

---

## 1. The problem

The shadow PatchTST serve pin does not advance. The champion–challenger
framework requires a fresh shadow model to produce a trustworthy comparison,
but the shadow model is stale. Without a refreshing shadow, the weekly promote
chain either (a) never has a challenger to evaluate, or (b) evaluates an
artifact trained on data so old that its WF-gate verdict is meaningless.

The weekly promote monitor (`weekly_promote_monitor.py`) tracks whether the
weekly promote **chain ran** (staging-artifact freshness), but does not answer
whether the **shadow retrain** produced a usable artifact or whether the served
shadow is current. The scorer identity monitor (`scorer_identity_monitor.py`)
catches silent rollbacks and unexplained scorer swaps but does not diagnose
*why* a shadow model stopped advancing.

Two candidate root causes have been identified. They are independent and may
both be active simultaneously.

---

## 2. Candidate A: "builder-not-run"

The shadow retrain launchd job simply is not running, or is running and
failing silently.

**Mechanism:** The PatchTST shadow retrain (`com.renquant.retrain-patchtst`,
dispatched via `renquant-orchestrator run-job weekly_patchtst_retrain --staged`)
requires the full subrepo PYTHONPATH + GPU availability + sufficient training
data. If the launchd plist is not installed, or the job exits non-zero without
an alerting surface, no new shadow artifact is produced. The weekly promote
chain then finds no staged candidate and records a clean "no candidate" pass —
which the promote monitor correctly classifies as "ran, nothing to promote"
rather than "stale."

**Evidence that would confirm:**
- `launchctl list | grep retrain-patchtst` returns nothing (plist not loaded)
- `logs/retrain_patchtst/` directory is empty or has no entries newer than the
  last known shadow artifact date
- The weekly promote log shows repeated "no staged candidate" with no prior
  retrain log entry on the same week

**Evidence that would refute:**
- Recent retrain log entries with exit 0 and a fresh staging artifact written

---

## 3. Candidate B: training/serving axis coupling or config-fingerprint drift

**Investigated, not confirmed as the #26 mechanism specifically.** An earlier
draft of this memo named a concrete causal chain — "the shadow retrain calls
`build_alpha158_qlib.py` without the #26 fix's `resolve_serving_daily_index()`
decoupling" — but tracing the actual shadow PatchTST code path does not
support that specific claim:

- The shadow retrain (`renquant_orchestrator.retrain_patchtst`, dispatched via
  `weekly_patchtst_retrain`) subprocesses into the pinned `renquant-model`
  PatchTST trainer using **`data/transformer_v4_wl200_clean.parquet`** as its
  primary feature-matrix input (`build_patchtst_wf_manifest.py`
  `DEFAULT_DATASET_REL`) — a dataset built by an entirely different pipeline,
  not `RenQuant/scripts/build_alpha158_qlib.py`.
- Only the **calibrator** subprocess (a post-hoc probability-calibration fit,
  not the scorer's own feature build) reads an alpha158-derived file
  (`data/alpha158_291_fundamental_dataset_rawlabel.parquet`,
  `DEFAULT_RAW_LABEL_PANEL_REL`). Using a forward-label-clipped panel to *fit
  a calibrator* is a training-time input choice, not necessarily the same
  defect class as #26 (which was specifically about the **live serving** feed
  being wrongly coupled to that clip).
- `build_alpha158_qlib.py` itself does not import or call
  `resolve_serving_daily_index()` at all (grepped; no reference). The #26 fix
  lives in `renquant_base_data.sec_fundamentals.resolve_serving_daily_index`,
  consumed by the live daily runner's fundamentals feed — a different call
  path than anything in the shadow retrain/calibrator chain traced above.

So there is no demonstrated call chain from the shadow retrain path into the
specific #26 mechanism. The broader hypothesis — that *some* data-path or
config coupling between training-time and serving-time state is stalling the
shadow lane — remains plausible and worth investigating, but should not be
presented as a variant of the #26 bug specifically until a concrete call path
is found (e.g., if a future change routes the shadow feature build through
`build_alpha158_qlib.py`, or if the calibrator's rawlabel-panel staleness
turns out to gate the shadow's effective serving date some other way).

A separate, better-evidenced variant: even with a successfully trained shadow,
the config fingerprint stamped at training time may not match the current live
config (`strategy_config.shadow.json`), causing `P-CONFIG-FP` mismatch at
promote evaluation time. This is the known `shadow-config-fp-restamp` issue —
the shadow e2e leg fail-closes whenever the watchlist/sector_map drifts from
the stamp. Of the two variants folded into this candidate, this one has a
concrete, previously-observed mechanism; the axis-coupling variant above is
speculative pending further evidence.

**Evidence that would confirm (axis-coupling variant, still speculative):**
- A recent shadow retrain log shows the training dataset's max date is >60
  trading days behind the price calendar, AND a concrete call path from the
  shadow retrain into a label-clipped serving-relevant index is identified
- The shadow artifact metadata's `config_fingerprint` does not match the
  current pinned `strategy_config.shadow.json`'s fingerprint
- The promote log shows `panel_scorer_config_mismatch` for the shadow lane

**Evidence that would refute:**
- Shadow retrain log shows a training dataset that reaches within ~5 trading
  days of today
- Config fingerprint matches after a re-stamp
- No call path from the shadow retrain/calibrator into a serving-coupled clip
  is ever found (in which case this candidate reduces to the config-fp variant
  alone)

---

## 4. Investigation steps (operator-executable, read-only)

1. **Check launchd:** `launchctl list | grep -i patchtst` — is the retrain job
   loaded?
2. **Check retrain logs:** `ls -lt logs/retrain_patchtst/ | head -5` — when
   did the last retrain attempt run?
3. **Check staging artifacts:** `ls -lt artifacts/patchtst_shadow/ | head -5`
   — is there a staged artifact newer than the current serve pin?
4. **Check config fingerprint:** run `check_model_bundle_consistency.py` against
   the shadow artifact + shadow config — does `P-CONFIG-FP` pass?
5. **Check data freshness in the shadow artifact:** read the metadata JSON for
   `trained_date` and the corpus date range — is the corpus behind price by
   more than the expected training lag, and if so, trace what specifically
   clips it (no call path into `resolve_serving_daily_index()` is
   established yet — see §3)?
6. **Check weekly promote logs:** `grep -l "VERDICT\|no.*candidate\|config_mismatch"
   logs/weekly_wf_promote/*.log | tail -5` — what has the promote chain been
   seeing?

Steps 1–2 distinguish Candidate A from B. Steps 3–5 characterize Candidate B's
variant (data clip vs config fp). Step 6 provides the promote chain's own view.

---

## 5. Expected outcome

If **A (builder-not-run)**: install the launchd plist, verify one successful
retrain cycle, then the promote chain picks up the staged artifact normally.

If **B (axis coupling, speculative)**: step 5's investigation determines
whether a concrete data-path coupling is actually stalling the shadow's
effective data horizon; if so, the fix depends on what that path turns out to
be (not assumed in advance to be `resolve_serving_daily_index()` — no call
chain into that function has been demonstrated from the shadow retrain path).
If **B (config-fp variant, well-evidenced)**: fixed by re-stamping (the
existing `stamp_patchtst_fingerprint.py` script) — this is the same known
`shadow-config-fp-restamp` mechanism seen before, not speculative.

Both causes may be active. The investigation order is A-first because it is
cheaper to diagnose (one `launchctl` command) and likelier given the system's
history of uninstalled/unfired launchd jobs.

---

## 6. Existing monitoring that will catch recurrence

Once the shadow retrain runs and produces a fresh artifact:
- `scorer_identity_monitor.py` (daily): catches silent scorer rollbacks and
  warns on `trained_date` > 28 days (the freshness directive)
- `weekly_promote_monitor.py` (weekly): catches promote chain staleness
- `fallback_shadow_logger.py` (daily): tracks best-of-recent model selection
  for the #210 freshness governance policy
