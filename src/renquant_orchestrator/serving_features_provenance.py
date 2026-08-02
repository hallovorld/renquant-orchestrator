"""The daily run bundle's ``serving_features`` block. (pipeline#250 design, rollout step 3)

WHY IT EXISTS. pipeline#250 (merged) measured the gap: the daily run computes
the full serving feature matrix, scores with it, and discards it — the run
bundle carried **0** feature keys against ~290 decision-trace rows (orch#678),
and the served matrix is not reconstructible after the panel refreshes
(orch#703). Step 2 (pipeline#252, merged) made the pipeline STAGE the
as-served matrix plus a digest sidecar on the inference context; this module
is step 3 — the orchestrator consumes that staged record into the daily
``run_bundle.json``, completing any deferred parquet write into the run
output dir (the same dir the rest of the bundle lands in).

ABSENT IS NOT CLEAN. Tri-state and additive, the
``serving_bundle_provenance`` / ``g4_session_bundle_block`` /
``wf_gate_provenance`` idiom: the block always carries a ``status``, and
"the producer staged nothing" and "the pinned pipeline predates the
recorder" are DIFFERENT statuses. A block that simply omitted itself would
be indistinguishable from a run that persisted its features.

STATUS VALUES (one discriminator across producer + consumer):

* ``written`` / ``write_failed`` — forwarded VERBATIM from the pipeline's
  record (pipeline#252 owns these; ``write_failed`` carries ``error``).
* ``not_staged`` — the pipeline recorder exists but never fired this run
  (sequence/history scorers consume no snapshot matrix — today's live
  hf_patchtst primary — and pre-step-2 contexts).
* ``pipeline_support_unavailable`` — the importable renquant-pipeline
  predates the #252 exports (version skew, the ``_record_bundle_contract``
  ImportError tri-state precedent: skew is not evidence either way).
* ``recorder_error`` — this recorder itself failed; the error is recorded.

NEVER RAISES. A provenance recorder that can abort the daily run is a worse
defect than the gap it closes (the ``wf_gate_provenance`` rule). The
finalized write is itself record-don't-raise on the pipeline side; every
failure path here returns a status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

STATUS_NOT_STAGED = "not_staged"
STATUS_PIPELINE_SUPPORT_UNAVAILABLE = "pipeline_support_unavailable"
STATUS_RECORDER_ERROR = "recorder_error"

#: Producer-owned statuses forwarded verbatim (pipeline#252).
STATUS_WRITTEN = "written"
STATUS_WRITE_FAILED = "write_failed"


def serving_features_block(
    inference_context: Any,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build the bundle's ``serving_features`` block. Never raises.

    ``inference_context`` is the object the pipeline's runtime stages ran on
    — the same context whose ``decision_trace`` the bundle already collects;
    the #252 recorder stages its matrix copy and its completed record there.
    ``output_dir`` (the run output dir, where ``run_bundle.json`` lands)
    completes a staged-but-unwritten matrix into
    ``<output_dir>/serving_features.parquet`` before the record is read —
    the identical finalization the pipeline's own payload writers perform.
    """
    try:
        try:
            from renquant_pipeline import (
                serving_features_bundle_block,
                write_staged_serving_features,
            )
        except ImportError as exc:
            return {
                "status": STATUS_PIPELINE_SUPPORT_UNAVAILABLE,
                "note": (
                    "the importable renquant-pipeline predates the #252 "
                    "serving-features exports — version skew, not evidence "
                    "that nothing was served"
                ),
                "error": str(exc)[:500],
            }
        if inference_context is not None and output_dir is not None:
            # Record-don't-raise on the pipeline side; a failure surfaces as
            # a forwarded `write_failed` record, never an exception.
            write_staged_serving_features(inference_context, Path(output_dir))
        record = serving_features_bundle_block(inference_context)
        if record is None:
            return {
                "status": STATUS_NOT_STAGED,
                "note": (
                    "the pipeline's serving-features recorder never fired "
                    "this run — sequence/history scorers consume no snapshot "
                    "matrix, and pre-step-2 contexts stage nothing; this is "
                    "not evidence of a write failure"
                ),
            }
        return dict(record)
    except Exception as exc:  # noqa: BLE001 — never abort the daily run
        return {
            "status": STATUS_RECORDER_ERROR,
            "error": str(exc)[:500],
        }


__all__ = [
    "STATUS_NOT_STAGED",
    "STATUS_PIPELINE_SUPPORT_UNAVAILABLE",
    "STATUS_RECORDER_ERROR",
    "STATUS_WRITE_FAILED",
    "STATUS_WRITTEN",
    "serving_features_block",
]
