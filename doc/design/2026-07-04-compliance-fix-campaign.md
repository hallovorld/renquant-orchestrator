# The compliance fix campaign — consolidated plan from the 4-way architecture audit

STATUS: DECISION/design (leader synthesis). Sources: the four audit memos — pipeline+s104
(pipeline#168: 1 P0/24 P1/33 P2), execution+common+model (#295: 2/13/15), orchestrator+
base-data+backtesting (#296: 0/16/25), umbrella (RQ#444: 6/19/5). Total 9 P0 / 72 P1 / 78 P2.
GOVERNING CONSTRAINT (operator 2026-07-03, memory-pinned): the mature, order-placing
production system must not break — every fix per the six-rule protection contract
(behavior-invariance proof + A/B suite; behavior changes = separate operator-visible PRs;
prod artifacts read-only; enablement via pre-registered gates only).

## Group A — LIVE-BEHAVIOR bugs (operator-visible fixes, one PR each, never bundled)

| ID | Finding | Proposed fix | Behavior change? |
|---|---|---|---|
| A1 | RQ#444 F-1: the 06-15 PatchTST mis-score fix lives only in the umbrella mirror; live shadow scoring runs the UNFIXED pipeline copy | port the fix to renquant-pipeline (the live authority) with the umbrella version as the reference; regression = the 06-15 incident fixture | YES — shadow scoring becomes CORRECT; primary untouched (GBDT). Operator notified pre-merge |
| A2 | RQ#444 F-17: the Sunday tournament writes per-ticker models straight to prod with the acceptance gate auto-disabled — next firing ~2 days | SHORT-TERM: re-enable the acceptance gate for tournament writes (fail-closed to previous model); LONG-TERM: route through the factory/artifacts lane | YES on the failure path only (bad models get rejected instead of deployed). Operator notified |
| A3 | pipeline#168 P0: kelly sigma_horizon default 252 + preflight passes on absent key | make the missing key FAIL preflight (protective; current behavior with key present unchanged) | failure-path only |
| A4 | #296 OR-3: Stage-2 canary allowlist stamped-not-enforced; §9.3a loss budget + session counter unimplemented | implement enforcement + budget + counter; extend the 16-combination arming tests | dark code today; MUST land before any Stage-2 authorization (pre-arming blocker, added to the authorization checklist) |

## Group B — the multiplicity收编 (structural, behavior-invariant, equivalence-pinned)

| ID | The N copies | Canonical home | Order |
|---|---|---|---|
| B1 | WalkForwardModelLoader ×3 (pipeline M6 / backtesting fork / umbrella fork = the LIVE gate leg) — the stamp-mismatch incident generator | pipeline's M6-dispatched loader; backtesting+umbrella re-point; M6 inventory amended | FIRST (feeds the promote gate; rides the M6 stage-2 window) |
| B2 | model_content_sha256 call-sites ×4 (calibrator fit + WF stamping on stale local copies) | renquant-common (import-only; the M6 rule) | with B1 |
| B3 | parent-intent identity ×2 (execution vs orchestrator reconciler, divergent-by-construction) | renquant-execution's compute_parent_intent_id | before Stage-2 arming |
| B4 | score_content_sha256 ×2 incompatible | renquant-artifacts hash_jsonable | any |
| B5 | NYSE session calendar ×6 | NEW renquant_common.market_calendar (equivalence-pinned against all six on a 10-year date fixture) | any |
| B6 | ntfy ×18 (+ RENQUANT_NO_NOTIFY honored nowhere in orchestrator) | renquant_common.notify + ops/notify.sh | any |
| B7 | manifest writers ×3 divergent (base-data) + validator under-enforcement | one shared writer passing the repo's own validator | any |
| B8 | train/serve alpha158 operators hand-mirrored (pipeline#168 top-P1, live XGB path) | single shared operator module + anti-skew test | careful: byte-equivalence proof on real panel rows first |

## Group C — mirror-drift GOVERNANCE (the disease, not the symptoms)

1. Reality: 78/169 kernel files materially drifted, bidirectional dual maintenance,
   the §3.5-cited parity test does not exist, no CI drift detection, alias fallback silent.
2. Decide the regime (this doc DECIDES): **pipeline = single authority for kernel/**;
   umbrella kernel becomes a frozen compatibility mirror — no new features land there
   (already the sprint convention), CI gains a drift-inventory check (report-only first),
   and the sim leg migrates to pinned-pipeline execution (fixes RQ#444 F-3: the promote
   gate validating on frozen-May code) in stages: inventory → sim-parity harness on pinned
   code → cutover PR with the gate re-baselined. F-3's fix is the LARGEST behavior-adjacent
   item — its own design PR with before/after gate readings; NOT bundled.
3. The 24 pipeline-only + 47 umbrella-only files get explicit dispositions in the drift
   inventory (lift / retire / mirror-freeze).

## Group D — P1/P2 hygiene waves (batched per repo, invariance-tested)

Import-direction fixes (9 pipeline→umbrella sites + boundary-test blind spots), divergent-
defaults cluster (6 keys → defaults matched to config + missing-key fail-loud), shadow-task
fail-isolation, factory artifact stamping (rides M6 re-stamp), caps/floors (execution+
orchestrator pyproject), IGV strategy relocation (PENDING operator's answer: yours?),
rq104 liveness checker, doc-convention tail.

## Sequencing & safety

Wave 1 (immediate): A2 (before Sunday), A3, A4, B1+B2 (the M6 window is open now).
Wave 2: A1 (with operator ack), B3-B7, D batches.
Wave 3: Group C staged program (F-3 cutover last, its own gate re-baseline).
Every PR: the protection-contract header + A/B suite proof + file-list placement scan at
harvest. Enablement changes: none in this campaign — pre-registered gates only.

## Phase 3 (after the waves): the four-system doc normalization

104 as-built (current production architecture, post-restore), 105 as-built (Stage-1/2 +
gates), 106 serving path (PIT lake → features → readiness), 107 governance (attribution/
risk-budget/S-REL/VERDICTS) — cross-linked, stale docs marked superseded, one index.
