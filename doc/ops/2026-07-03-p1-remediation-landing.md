# Landing record — P1 remediation batch items 1–2 (unblock clause, 2026-07-03 04:03–04:10 PT)

STATUS: ops record (record + notify discipline). Authority: the operator's unblock clause
(2026-07-02) — P1 production remediation (prod silently running the wrong scorer since
06-26, #274) + the armed 0.9.x detonations (#270 §1a). Executed in the #242 safe window
(04:03–04:10 PT, no runs in flight), pre-announced in-session at 03:33 with no objection.

## Item 1 — prod scorer restore + calibrator refit (RQ #437, merged 03:48 PT)

| Step | Result |
|---|---|
| Backup | wrong-model artifact (5ce63326…) + old calibrator copied to scratchpad (retained ≥1 week) |
| Targeted restore | `git checkout origin/main -- backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json` → sha 04d7a381… (byte-identical to the 06-21 promoted model) |
| Verification | `scripts/verify_prod_scorer_restore_20260703.py`: **PASS** — C1..C5 green; config fingerprint f8fb2259… valid with zero field diff (no re-stamp) |
| Calibrator refit | `fit_calibrator_alpha158_fund.py` → side-path candidate inspected FIRST (bound fp = restored scorer 6fc9985e… ✓, neutral_raw ≈ −0.267, monotone ER, acceptance gate PASS, pool_ic +0.1225) → backup → installed at artifacts/prod/panel-rank-calibration.json |
| Final pairing | verify C6: **PAIRED** (calibrator fp == restored scorer fp) — no fail-closed interim; buys re-enabled for today's 13:55 run on the correct 06-21 model (12d old, within the 28d directive) |

## Item 2 — M6 step-0 legacy pre-stamp (orch #273, merged)

| Step | Result |
|---|---|
| Dry-run | 47 targets, 0 refusals, 0 red bindings |
| Apply | **47/47 stamped** (grant string embedded per tool contract); report JSONs archived in scratchpad; .bak files per tool convention |
| Idempotence recheck | n_to_stamp = 0, 0 red — clean; zero follow-up commands emitted |
| Effect | the two armed detonations (#270 §1a: weekly refit v1-stamp → daily fail-close; weekly_wf_promote loader fail-close) are DEFUSED — venv/checkout convergence to common 0.9.x is now safe |

## Deferred (await explicit operator grant)

Item 3 (S12 shadow refresh — 1–2h retrain), item 4 (M1 scheduler install), item 5
(scorer-identity monitor install): P1 urgency does not extend to them; commands stand ready
in their PRs (#435/#266/#277). Note: the refit calibrator (trained 2026-07-03) supersedes
the 07-01 vintage; the −0.29-anchored intercept artifact (#274/V5) is expected to clear in
today's run — BL-2 sign_laundered should drop from ~45 to single digits WITHOUT M4's flag
(the pairing was the artifact). Today's run is the natural A/B read.
