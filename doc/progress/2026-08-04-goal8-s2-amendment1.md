# 2026-08-04 — S2 AMENDMENT 1: the momentum arm's real, time-safe record surface

STATUS:    pre-clock amendment to the frozen S2 prereg (legal window:
           the S1 clock has not started)
WHAT:      building the readout's fixtures against REAL record shapes
           found the momentum arm unmeasurable as frozen: the in-process
           lane's identity-stamped records are HEALTH records
           (shadow_scorer_health.jsonl — no per-ticker scores), no rail
           consumes the momentum profile config, no momentum runs db
           exists [all measured 2026-08-04]. Replacement with ZERO new
           serving surface: momentum scores are weekly-frozen by
           construction, so the chain-verified dated artifact IS the
           durable score record. Round-1 review hardened the selection
           to TIME-SAFE: the serving row for session D = last ledger row
           with cutoff_date <= D AND appended_at_utc <= D's session
           cutoff (append-only chain makes this reproducible); the
           readout records (row_index, row_sha, artifact_content_sha256)
           per session so look-ahead or later-ledger substitution is
           mechanically visible; no qualifying/verifiable row = no
           basket, counted against the >=19/20 coverage rule unchanged.
WHY/DIR:   the written-during-run-after discipline working as designed —
           the gap died before the window instead of at session 20.
EVIDENCE:  three measured negatives in the session log (health-record
           keys, zero profile consumers, db listing); doc-only change.
NEXT:      merge → S1 batch (s104#85 + umbrella pins) → shared window.
