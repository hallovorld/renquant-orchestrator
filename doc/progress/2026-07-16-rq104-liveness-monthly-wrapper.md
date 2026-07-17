# Fix: rq104 liveness treats risk_budget as the monthly job it is

STATUS: delivered
WHAT: `ops/renquant104/rq104_liveness_check.py` checked the risk_budget
wrapper log DAILY, but the launchd job (com.renquant.rq104-risk-budget)
runs monthly (Day=1, 15:30). Every non-first session day alarmed
"risk_budget: wrapper log missing" (operator saw it 2026-07-16). Split
into _DAILY_WRAPPER_LOGS (scorer_identity) and _MONTHLY_WRAPPER_LOGS
({risk_budget: 1}, checked only on its run day). This upstreams a local
hotfix that lived uncommitted in the renquant-orchestrator-run checkout
and was reverted when that checkout was aligned to origin/main during the
07-16 #522 deploy (preserved in backup/pre-522-local-hotfixes-20260716).
WHY/DIR: 07-16 incident cleanup — silent local hotfixes must live
upstream or die (recovery-checkout-clobbers class).
EVIDENCE: tests updated to the monthly semantics + new
test_monthly_wrapper_checked_only_on_run_day (missing log on day 1 DOES
alarm); 11/11 pass.
NEXT: none.
