# A-1 λ dose-response sweep — research PR

STATUS:   research evidence (read-only; script + JSON + memo). Round-1 "valuable NULL"
          conclusion RETRACTED; round 2 fixed the harness bug but overstated
          `w_current` precision and left stale "NULL" framing in the PR surface —
          both corrected in round 3.
REVISION: r3.
WHAT:     pre-enable evidence for RS-2's A-1: drive the real pipeline QP solver on the
          latest two full runs' (mu, σ) with cash_drag_lambda ∈ {0…0.10}.
WHY/DIR:  round 1 concluded A-1's deployment contribution ≈ 0 because solutions were
          identical at every λ. Round 2 (codex review) found this was an
          experiment-harness artifact: the solver only adds the cash-drag objective
          term when BOTH min_invested_pct > 0 AND cash_drag_lambda > 0
          (qp_solver.py:468); round 1 never passed min_invested_pct, so the wrapper
          default (0.0) disabled the mechanism entirely — identical solutions were
          guaranteed by construction. Separately, live production
          (strategy_config.json → rotation.joint_actions) has BOTH
          qp_min_invested_pct=0 and qp_cash_drag_lambda=0 set explicitly, so A-1 as
          literally scoped (λ alone) is mechanically a no-op right now — a fact, not
          new evidence.
EVIDENCE: re-ran with min_invested_pct=0.7 (this config's own pre-2026-05 value,
          strategy_config.json.pre-meta-label-deploy) as a 2D sweep against
          turnover_max ∈ {0.15,0.20,0.30,0.50}, plus a positive-control point (loose
          turnover). Result: λ 0→0.05 (A-1's proposed target) adds ~16-19pp deployed
          fraction at the CURRENT production turnover cap (0.15), consistently across
          both runs and every turnover cap tested — λ has a large, real, monotonic
          effect once the mechanism is genuinely enabled. w_current reconstructed from
          each holding's most recent real trades.target_pct (13/13 held positions
          across both runs resolved from real trade history, no equal-weight
          approximation needed). Run selection now joins pipeline_runs
          (run_date + created_at), not lexicographic run_id ordering.
NEXT:     RS-2 (#238, merged) describes A-1 as touching only qp_cash_drag_lambda —
          this needs a follow-up correction: A-1 as scoped is a no-op; a genuine
          "un-disable the shipped mechanism" change requires BOTH parameters moving
          together. Flagging as a NEW finding for whoever picks up A-1's S6
          preregistered shadow sweep, not resolving it here (out of this PR's scope
          — this PR is evidence, not a design decision). The S6 in-pipeline shadow
          sweep remains the actual enable-gating AC.

## Round 2 (2026-07-02) — codex review r4, all 6 findings addressed

1. **Disabled-objective bug fixed** — script now passes `min_invested_pct` explicitly
   on every solver call; confirmed the gate condition by reading `qp_solver.py:468`
   directly rather than trusting the review text alone.
2. **Production config recovery** — `min_invested_pct=0.7` (historical, real value
   from this exact config file's own git history) and per-regime `turnover_max` values
   (0.15 BULL_CALM, 0.20 global) pulled from the live `strategy_config.json`, not
   invented placeholders.
3. **State reconstruction fixed** — `w_current` now built from each held ticker's most
   recent `trades.target_pct` as of the run date (real point-in-time weight signal),
   not an equal-weight-of-cap approximation. All 13 held positions across both runs
   resolved from genuine trade history.
4. **Positive-control test added** — `tests/test_poc_lambda_sweep.py` proves λ changes
   the solver's objective/solution at a deliberately non-binding turnover cap when
   `min_invested_pct > 0`, and proves it does NOT change the solution when
   `min_invested_pct = 0` (the production-reality mechanical-null case) — both
   branches of the gate condition are directly tested.
5. **2D sweep added** — λ × turnover_max at the un-disabled `min_invested_pct`,
   separating "turnover cap limits the deployment ceiling" (real, confirmed) from
   "λ has no effect" (false — λ moves the solution at every turnover cap tested).
6. **Run selection fixed** — joins `pipeline_runs` on `run_date`/`created_at`,
   selecting the latest run per calendar date for the most recent 2 distinct dates,
   not lexicographic `run_id` ordering.

Title and headline retracted ("valuable NULL" → "NOT a NULL — round-1 harness never
enabled the mechanism"); "structural" and "lane-B-only consequences" framing removed
from the research doc.

## Round 3 (2026-07-02) — codex review r5: two overclaims closed

Codex confirmed the mechanistic conclusion (harness bug + "A-1 is a no-op unless
`min_invested_pct` also changes") is SOUND. Two remaining corrections:

1. **PR body updated completely** — it still advertised round 1's fully-retracted
   "valuable NULL / turnover masks lambda / lane B only" framing. Rewritten to state
   the CONFIRMED mechanical no-op finding as the primary result, with the +16-19pp
   figure explicitly demoted to conditional sensitivity evidence.
2. **`w_current` overclaim corrected.** Round 2's "real point-in-time weight signal"
   language overstated what `trades.target_pct`-based reconstruction actually captures
   — it's the INTENDED target at trade time, not a true as-of delivered weight (misses
   price drift, partial/unfilled fills, subsequent sells/exits, corporate actions,
   cash/NAV normalization). Relabeled the +16-19pp finding as "solver sensitivity under
   a target-weight approximation," not a production-effect estimate. The script now
   computes and stamps `sum_w_current_target_pct_approx` per run in the evidence JSON
   (0.3951 for 2026-07-01, 0.4278 for 2026-06-30) alongside the existing reconstruction-
   coverage fields (100% coverage in both runs — 6/6 and 7/7 held positions). The
   research doc's structure now explicitly separates a "CONFIRMED (mechanical)" section
   from a "CONDITIONAL SENSITIVITY (not a production estimate)" section, plus a new
   "what a real effect-size claim requires" section pointing to a full run-bound
   replay/shadow (per #228's one-change-at-a-time experiment structure) as the correct
   vehicle for an actual production estimate.

Verified: `python3 -m pytest tests/test_poc_lambda_sweep.py` (run with
`PYTHONPATH` including the `renquant-common`/`renquant-pipeline` sibling checkouts,
since these tests import the real QP solver) — 4/4 pass. Re-ran the script end-to-end
against real data to produce the fresh `sum_w_current_target_pct_approx` values above.
