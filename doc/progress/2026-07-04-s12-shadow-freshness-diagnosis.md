# S12 shadow freshness root-cause diagnosis

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: S12 (shadow freshness impl + panel-refresh root-cause memo)

## What

Root-cause diagnosis memo for the stale shadow PatchTST serve pin.
Two candidate causes identified:

- **A: builder-not-run** — the shadow retrain launchd job is not loaded or
  is failing silently; no staged artifact produced for the promote chain.
- **B: training/serving axis coupling (speculative) or config-fingerprint
  drift (well-evidenced)** — two variants folded into one candidate: an
  unconfirmed general data-path coupling hypothesis, and the known
  `shadow-config-fp-restamp` promote-time fail-close.

Includes 6 read-only investigation steps the operator can execute to
distinguish the two causes. This is the "diagnosis FIRST" deliverable
that the master plan requires before implementing shadow freshness phases 2–4.

## Not included

No code changes. The diagnosis identifies what to investigate; the fix
depends on which cause is active.

## Round 2 (review)

Codex held the PR because Candidate B named a specific mechanism (the #26
`build_alpha158_qlib.py` / `resolve_serving_daily_index()` dropna bug) without
showing the shadow retrain path actually calls it. Traced the real code path:
the shadow PatchTST trainer's primary feature matrix comes from
`data/transformer_v4_wl200_clean.parquet` (`build_patchtst_wf_manifest.py`'s
`DEFAULT_DATASET_REL`), an entirely different pipeline than
`build_alpha158_qlib.py`. Only the calibrator subprocess reads an
alpha158-derived rawlabel panel, and `build_alpha158_qlib.py` itself never
imports `resolve_serving_daily_index()` — grepped, no reference. No call chain
from the shadow retrain into the #26 mechanism is demonstrated. Rewrote
Candidate B (design doc §3–5) to state this investigation explicitly, broaden
the axis-coupling half to a general, speculative hypothesis pending a concrete
call path, and separate out the config-fingerprint variant as the
well-evidenced half (same known `shadow-config-fp-restamp` mechanism, not
speculative).
