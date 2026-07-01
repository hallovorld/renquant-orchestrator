# best-of-10d fallback — SHADOW-LOGGING + rolling staging registry (#210)

STATUS:  merged-ready implementation PR. Observe-only. **Promotes nothing** — no pin / model /
         config / broker / risk / sizing change.
SCOPE:   Phase-4 *shadow-first* (log-only) slice of the freshness-governance design
         (`doc/design/2026-06-30-model-freshness-governance.md` §5.6 + rollout Phase 4). The
         28d ceiling flip, WF-gate repair, and the historical replay (Phases 1–3) are OUT of
         scope here.

## What shipped

- `src/renquant_orchestrator/model_staging_registry.py` — a **read-only** rolling registry.
  Scans a staging dir for `*.staging.json` sidecars → structured `StagingCandidate`s carrying
  data cutoff, gate verdict + **normalized failure class** (§4.3.1), an immutable
  point-in-time availability timestamp (§5.0-i-a), the basic-integrity floor (§4.3.2), and the
  pre-registered selection score (§4.3.4). Query: `within_last_days(N, as_of=…)` — candidates
  trained within the last N days, availability-filtered, newest-first. Malformed sidecars
  degrade to `parse_error` instead of throwing.
- `src/renquant_orchestrator/fallback_shadow_logger.py` — given the registry + prod freshness,
  DECIDES what the best-of-recent fallback **WOULD** select and appends the decision to JSONL.
  It would promote only if ALL hold: (1) prod breached the fast-axis ceiling (or a slow axis is
  off-SLA); (2) the **newest** retrain failed for an **enumerated infra** reason
  (timeout / config-path / artifact-not-found / recipe-mismatch); (3) a recent candidate is
  point-in-time available, infra-only, clears the integrity floor AND the recomputed OOS
  economic floor (§4.3.3), and has a computable selection score. Winner = top selection score,
  tie-broken by freshest cutoff then id. Everything else logs `would_promote=false` with an
  explicit `would_NOT_because`. **Conservative classification:** substantive / leakage /
  placebo / unknown → fail-closed; `>window` → no candidate.
- Log record schema: `{as_of, would_promote, candidate, reason, failure_class, selection_score,
  would_NOT_because}` (+ audit `prod` / `meta`). Append is **idempotent** on
  `(as_of, would_promote, candidate)`.

## Tests (green — RenQuant venv)

`tests/test_model_staging_registry.py` + `tests/test_fallback_shadow_logger.py`, fixture staging
dir + injected clock: registry scan / last-N-days query / `>window → none`, infra-vs-substance
classification (substantive/leakage/placebo/unknown → NOT promote), point-in-time availability
fail-closed, basic-integrity + OOS floor, best-of-recent selection + tie-break, idempotent
append, and the **no-mutation invariant** (run touches only the JSONL log; staging bytes
unchanged). `pytest -q`: **617 passed, 2 pre-existing skips**.

## Not done here (needs sign-off before flipping to real auto-promote)

Shadow logging builds the prospective point-in-time record going forward (§5.6). Turning
`would_promote` into an actual promotion requires: accrued shadow evidence, the §5.0 Phase-0
feasibility audit + §5.2 held-out point-in-time replay clearing the non-inferiority gate, and
**Codex + operator sign-off**. Until then this is a monitor that writes one log line.
