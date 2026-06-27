# Design: two autonomous ops loops (error-responder + post-daily reviewer)

2026-06-27. Status: **PROPOSAL for review** (not implemented). Operator request:
two self-driving loops, executed by subagents, every change via PR + Codex review,
**never self-merge, never `git` in the live tree, never auto-touch live
state/model/data**.

1. **Loop 1 — error-responder**: when an ERROR fires to ntfy, auto-investigate →
   (if a code bug) fix in a clone → open a PR → ntfy; (if operational/live) ntfy
   a human diagnosis, do NOT auto-change.
2. **Loop 2 — post-daily reviewer**: after each daily-full, verify the decision
   tree is sound; if sound, run a fundamentals/technical/analyst trade-reliability
   review; ntfy the operator only when a change is warranted.

This doc grounds both in the **existing** infra (file:line below) so the build is
assembly, not invention. It is for Codex to discuss/review before any code lands.

## 0. Shared foundation (reuse the proven `agent-pr-loop`)
The system already runs a scheduled agent loop we copy wholesale:
- `~/Library/LaunchAgents/com.renquant.agent-pr-loop.plist` (StartInterval 300s) →
  `RenQuant/scripts/agent_pr_loop.sh` (loads per-agent GH tokens from Keychain,
  `flock` lock, PATH fixup) → `agent_pr_loop.py` → pipes a prompt to
  **`claude -p --dangerously-skip-permissions --add-dir /Users/renhao/git/github -`**
  (stdin), env `GH_TOKEN`=agent token.
- `renquant-orchestrator/src/renquant_orchestrator/agent_workflows.py` is the
  control-plane: queue resolution, `reviewed/fixed/merged by <agent>` markers,
  no self-review, **production-path protection**, pre-merge audit, STOP labels
  (`agent:manual-hold`, `agent:cost-cap`).

**Key consequence:** Loops 1/2 only ever **open PRs** and **send ntfy**. The
existing agent-pr-loop already does codex review + the deterministic merge, so we
inherit "never self-merge" for free — neither new loop merges anything.

New-loop shape (per loop): one launchd plist → one wrapper `.sh` (Keychain+lock) →
one orchestrator subcommand that polls/triages and spawns the subagent.

## 1. Loop 1 — error-responder
**Trigger (verified signal):** poll `RenQuant/logs/alerts/alert_log.jsonl`
(`live/alerts.py` `_append_alert_log`; JSONL, one event/line). Filter
`status=="sent"` AND `taxonomy=="ACTION_REQUIRED"` (priority urgent/high). Dedup on
`(key, ts)` against a runner state file; the dedup key is
`stable_alert_key()` = `sha256[:24]`, event id `"{TAXONOMY}:{key}"`. Skip
`suppressed_duplicate` rows (operator already saw the first). Schedule: 300s,
`flock`-guarded.

**Classification (the load-bearing safety step).** Each new error → exactly one of:
- **CODE bug** (NameError/import/contract/test-catchable defect, e.g. the
  2026-06-26 `save_live_state_atomic(..., config)` NameError) → auto-fix path.
- **OPERATIONAL / live-state / model / data** (PREFLIGHT-FAIL on freshness or
  dormancy, broker errors, stale model, FAILED-EXIT) → **ntfy a human diagnosis,
  do NOT auto-change.** This is the hard lesson of this session: agents must not
  auto-touch live state/model/data.
- **UNKNOWN** → ntfy a human.
Classifier = cheap rules on title/taxonomy first, then a triage subagent for the
ambiguous remainder. Default on uncertainty = ntfy human, never auto-fix.

**Auto-fix path (CODE only).** Spawn a headless `claude` subagent with the error
context + strict guardrails:
- Work ONLY in a fresh `/tmp` clone; **NEVER** `/Users/renhao/git/github/RenQuant`.
- Root-cause from logs (read-only on the live tree), reproduce, fix, **add a
  regression test**, run tests, push a branch, open a PR (`fixed by <agent>` marker
  + a `doc/progress/` note), then STOP. No merge.
- ntfy: "auto-fix PR #N opened for «title»" or "could not auto-fix «title» — needs
  you (diagnosis: …)".

**Guardrails:** rate-limit (≤2 open auto-fix PRs, ≤N/hour); dedup; `--dry-run`
(detect+log+ntfy "would do X", no PR); kill-switch (STOP file / env); never
self-merge; never live-tree git; bounded subagent spend (cost cap).

## 2. Loop 2 — post-daily reviewer
**Trigger:** scheduled ~14:15 PT (daily-full runs 13:55, finishes ~14:07 + shadow),
or detect today's `=== daily_104 finished ===` marker in
`logs/daily_104/<date>.log`; idempotent (once/day, dedup on `run_id` from
`pipeline_runs`). Read-only; advisory only; never trades.

**Phase A — decision-tree health (deterministic, no LLM):**
- `kernel.persistence.validate_decision_trace_integrity(run_id)` — the 13 checks
  (watchlist coverage, selected-but-blocked paradox, reason gaps, horizon
  alignment, trade reconciliation, attribution).
- Cross-check `gate_verdicts` / `decision_ledger.db` vs `live_state` (gate
  allow/halve/block vs `skip_buys`; admits=0 vs intent).
- Buy-side health: conviction admits, freshness, model_contract.
- Any failure → ntfy "decision-tree problem: «detail»".

**Phase B — trade-reliability (only if A is clean):** subagent runs the
`trade-review` skill on today's book + orders:
- `portfolio_weights.py` (cash %, HHI, effective-N), `technical_battery.py`
  (trend/RSI/vol/rel-strength vs SPY), **FMP analyst data** (`data/fmp_harvest/`
  price-target & grades — now ~283/291 covered), fundamentals.
- Synthesize per-name keep/trim/cut + sizing-vs-upside + concentration + cash drag
  (+ surface findings like the conviction-floor-too-strict / admits=0 study).

**Notification policy:** ntfy ONLY when a change is warranted; otherwise write a
dated digest, no spam. Advisory — never places/cancels orders.

## 3. Cross-cutting guardrails (apply to both)
- Every change via PR + Codex review; **never self-merge** (agent-pr-loop merges).
- Subagents NEVER `git` in the live tree; work in `/tmp` clones; NEVER touch live
  `state/model/data` files.
- **Verify-before-asserting:** every finding a loop emits must cite the data/log it
  came from; no unverified conclusions (the 2026-06-26 rule).
- Idempotent, deduped, rate-limited, `flock`-guarded, `--dry-run` + kill-switch,
  bounded subagent spend.

## 4. Where code lands (proposal)
- Orchestrator: `renquant-orchestrator ntfy-responder` + `post-daily-review`
  subcommands (poll/triage + prompt construction + classification), in a new module
  mirroring `agent_workflows.py`.
- `RenQuant/scripts/`: `ntfy_error_loop.sh`, `post_daily_review.sh` (+ launchd
  plists), mirroring `agent_pr_loop.sh`.
- Reuse: `live/alerts.py` (send the loop's own ntfys), the `trade-review` skill,
  `validate_decision_trace_integrity`, the conviction validators.

## 5. Open questions for Codex
1. CODE-vs-OPERATIONAL classifier: how conservative? (Hard line: never auto-fix
   anything that touches live state/model/data.)
2. Should Loop 1 auto-fix, or only ever open a **draft** PR + ntfy, given the risk
   of a bad auto-fix? (Proposed: auto-fix CODE bugs **with a regression test**;
   everything else → ntfy.)
3. Rate-limits / cost caps (auto-fix PRs/day; subagent spend/cycle).
4. Phase-A failure: auto-open a fix PR too, or ntfy only?
5. Dedup window + escalation when a `suppressed_duplicate` becomes a new incident.

## 6. Rollout
- **Phase 0:** both loops **dry-run** (detect + log + ntfy "would do X", no PRs).
- **Phase 1:** Loop 2 live (read-only analysis — inherently safe).
- **Phase 2:** Loop 1 auto-fix for CODE bugs only, after Codex signs off on the
  classifier + guardrails.
