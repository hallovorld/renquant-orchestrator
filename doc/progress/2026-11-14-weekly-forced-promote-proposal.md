# 2026-11-14 — PROPOSAL: a written "weekly retrain is force-promoted" policy (operator-requested; NOT in force until the operator ratifies it)

STATUS:   proposal, awaiting the operator's own approval. Nothing here changes any gate, config, artifact or
          launchd job; this PR is the written policy LONG row 1 requires before any WF-gate exception exists.
WHAT:     Defines exactly what "force the weekly model into prod" means, which gates it relaxes and which it
          does NOT, the risk caps, the automatic kill-switch, the expiry, and the implementation PRs that would
          follow. Parameters marked **[OPERATOR SETS]** carry a proposed default and must be confirmed by the
          operator when ratifying.
WHY/DIR:  Operator, 2026-11-14: "从今天开始，每周重训的模型强行进prod上线". Row 1 ("a model that can't pass does not
          ship … never RQ_ALLOW_NO_WF") forbids the author from creating this exception; it must be the
          operator's written, dated, scoped decision (same shape as rows 2e/2g/2h and the fast-path policy #1133).
EVIDENCE: see §0. This is a policy proposal; the numbers are the risk the operator is accepting, not a claim
          that the forced model is good.
NEXT:     operator edits/approves and merges as `haorensjtu-dev`, adds the LONG row in §6 in the SAME merge or a
          follow-up reviewed PR; only then do the implementation PRs in §5 begin. Agents do NOT implement before
          that row exists.

## 0. What the operator is accepting — measured, not assumed

| quantity | value | provenance |
|---|---|---|
| Weekly candidate verdict, every run since 2026-10 | REJECTED on `quality_floor` | [VERIFIED logs/weekly_wf_promote/2026-11-14.log "WF gate REJECTED … refused on 'quality_floor'"; SILENT-REFUSAL page 2026-11-08: 35 non-acting runs] |
| placebo (label-shuffled) IC of the 2026-11-14 candidate | 0.0347 vs ceiling 0.0188 | [VERIFIED logs/weekly_wf_promote/2026-11-14.log placebo_ceiling detail] — the candidate's "signal" is partly a leakage floor |
| genuine IC (aligned − placebo), recent candidates | ≈ −0.005 vs required +0.02 | [FROM 2026-10 session WF logs; not re-read 2026-11-14 — re-verify before ratifying] |
| mean WF Sharpe vs SPY | ≈ 0.54 vs 1.08 | [FROM 2026-10 session WF logs; not re-read 2026-11-14 — re-verify before ratifying] |
| 104 since 2026-09-29 | sell-only, `no trade (no_candidates)` | [VERIFIED daily_104 logs 2026-11-09..13: all "finished sell-only fallback"] |

Ratifying means: real capital buys driven by a model that has no evidence of beating the benchmark. That is the
operator's call to make; this document makes it explicit and bounded.

## 1. What "force-promote" does — and does not

DOES (only when this policy is ACTIVE and UNEXPIRED, §4):
1. The weekly job promotes the freshly trained staging pair (model + calibrator) to prod after the gate runs
   **regardless of the gate verdict**, stamping `wf_gate_metadata.promotion_basis = "operator_forced_weekly"`,
   `passed = false` (the truth is never overwritten with `true`), and the policy id/expiry.
2. `P-WF-GATE` and `P-REGIME-IC` are downgraded HARD → SOFT **only** when the served artifact carries that exact
   stamp and the policy is unexpired. Any other failed-WF artifact still hard-fails.

DOES NOT (unchanged, still fail-closed):
- Training must SUCCEED on fresh data. A failed training, stale-bar failure (the 2026-11-14 MSFT case), a
  calibrator/scorer BINDING MISMATCH, a smoke-test failure, or a digest-stamp failure promotes NOTHING.
- `P-MODEL-STALENESS`, `P-CORR-FRESHNESS`, data-freshness gates, broker/preflight health, wash-sale and tax rules,
  position cap, rotation rules, and every shadow lane are untouched.
- No artifact is written outside the existing weekly promote path; the existing `weekly_rollback_<date>` backup
  of the prior pair is still taken first.
- The gate still RUNS and its verdict is still recorded and still paged (prefixed `FORCED:`) — the alarm is not
  silenced, only the block is lifted.

## 2. Risk caps (apply to buys admitted while the served artifact is `operator_forced_weekly`)

| cap | proposed default | |
|---|---|---|
| max new-buy notional per name | ≤ 5% of NAV | [OPERATOR SETS] |
| max NEW buys per session | ≤ 2 | [OPERATOR SETS] |
| max cumulative NAV deployed by forced-model buys | ≤ 25% | [OPERATOR SETS] |
| sells / exits | unchanged (no cap, no delay) | fixed |

Caps are enforced in the decision pipeline by reading the stamp (implementation §5), not by operator discipline.

## 3. Automatic kill-switch → back to sell-only

The policy self-suspends (served artifact reverts to the pre-force rollback copy; preflight returns to HARD) when
ANY of: (a) trailing-20-session realized+unrealized P&L of forced-model buys is below **−3% of the NAV they
deployed** **[OPERATOR SETS]**; (b) those buys trail SPY by more than **5 percentage points** over the same
window **[OPERATOR SETS]**; (c) the policy expiry passes; (d) the operator revokes it in the ledger. A suspension
pages immediately and is recorded; re-enabling needs a NEW ledger row (no silent re-arm).

## 4. Expiry and review

Default expiry **2026-12-31** **[OPERATOR SETS]**, renewable only by a new dated ledger row. On 2026-12-15 an agent
posts a one-page read-out (forced-model buys vs SPY, vs the cash it displaced) so renewal is a decision on data.

## 5. Implementation (separate, reviewed PRs — begin only after §6 row exists)

1. `weekly_wf_promote.sh`: read policy (`doc/policy/weekly-forced-promote.json`: id, expiry, active); on REJECT +
   policy active, promote with the stamp instead of exiting 1; page `FORCED:`. Test: forced path stamps
   `passed=false`; expired/absent policy keeps today's behaviour (exit 1).
2. Pipeline preflight: `P-WF-GATE` / `P-REGIME-IC` soft only on exact stamp + unexpired (pipeline repo).
3. Decision pipeline: the §2 caps + §3 kill-switch evaluator, with a read-only status line in the daily page.
4. Manifest/ledger/doc updates; `sentinel_acks` untouched.
Each carries its own progress doc and full codex review (none is fast-path eligible: touches pipeline/ops).

## 6. Proposed LONG-ledger row (operator adds; wording is the operator's)

> **N. TIME-BOXED exception to row 1 — weekly retrain force-promote.** AUTHORIZED BY the operator 2026-11-14
> ("从今天开始，每周重训的模型强行进prod上线"), scoped and bounded by `doc/progress/2026-11-14-weekly-forced-promote-proposal.md`:
> only the weekly-trained pair, only after a SUCCESSFUL fresh-data training, gates still run and page, caps §2,
> kill-switch §3, expires 2026-12-31 unless renewed by a new row. Row 1 otherwise stands.

## 7. Honest limits

- This policy lifts a block; it does not create edge. §0 is the evidence that the forced model currently has none.
- It does not fix the weekly training failures (stale bars from fetch timeouts, RenQuant#647 only surfaces them).
- Until §6 exists and §5 lands, **nothing changes**: 104 stays sell-only and the weekly job keeps exiting 1 on REJECT.
