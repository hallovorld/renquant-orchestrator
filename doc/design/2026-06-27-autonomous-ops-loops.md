# Design: two autonomous ops loops (error-responder + post-daily reviewer)

2026-06-27. Status: **PROPOSAL for review** (not implemented). Operator request:
two self-driving loops, executed mostly by **deterministic scripts** with subagents
only where judgment is irreducible, every change via PR + Codex review, **never
self-merge, never `git` in the live tree, never auto-touch live state/model/data**.

1. **Loop 1 — error-responder**: when an ERROR fires to ntfy, auto-investigate →
   (if a code bug) fix in a clone → open a PR → ntfy; (if operational/live) ntfy
   a human diagnosis, do NOT auto-change.
2. **Loop 2 — post-daily reviewer**: after each daily-full, verify the decision
   tree is sound; if sound, run a fundamentals/technical/analyst trade-reliability
   review; ntfy the operator only when a change is warranted.

This doc grounds both in the **existing** infra (file:line below) so the build is
assembly, not invention. It is for Codex to discuss/review before any code lands.

## 0. Efficiency principle: SCRIPT-FIRST, agent-as-last-resort
Scripts are deterministic and ~free; an LLM subagent costs tokens and latency. So
**the loop body is scripts**; a subagent is spawned **only for irreducible
judgment**, and most cycles spawn **zero** agents:

| Work | Mechanism | Agent? |
|---|---|---|
| poll `alert_log.jsonl`, dedup on `(key,ts)` | script | no |
| classify error (title/taxonomy rules + known-error catalog) | script | no |
| known recurring error → templated playbook fix | script | no |
| **novel code-bug root-cause + fix** | subagent | **yes (only here)** |
| decision-trace integrity + gate-verdict checks | script | no |
| compute portfolio/technical/analyst/fundamental signals + rule-based flags | script | no |
| **narrative trade synthesis when flags trip** | subagent | **yes, optional** |
| build + POST ntfy | script | no |

Budget target: an idle day = 0 agent spawns (pure-script health pass + a digest);
an agent fires only on a *novel* code bug or (optionally) when a rule-flag wants a
human-readable synthesis. Hard cap on agent spawns/cycle + /day.

## 1. Shared foundation (reuse the proven `agent-pr-loop`)
- `~/Library/LaunchAgents/com.renquant.agent-pr-loop.plist` (StartInterval 300s) →
  `RenQuant/scripts/agent_pr_loop.sh` (per-agent GH tokens from Keychain, `flock`
  lock, PATH fixup) → `agent_pr_loop.py` → pipes a prompt to
  **`claude -p --dangerously-skip-permissions --add-dir /Users/renhao/git/github -`**.
- `agent_workflows.py` control-plane: queue resolution, `reviewed/fixed/merged by
  <agent>` markers, no self-review, production-path protection, pre-merge audit.

**Key consequence:** Loops 1/2 only ever **open PRs** and **send ntfy**. The
existing agent-pr-loop already does codex review + the deterministic merge, so
never-self-merge is inherited.

New-loop shape: one launchd plist → one wrapper `.sh` (Keychain+lock) → one
orchestrator subcommand (a **script** that polls/triages/checks) that spawns a
subagent only on the irreducible-judgment branch.

## 2. Loop 1 — error-responder
**Trigger (script):** poll `RenQuant/logs/alerts/alert_log.jsonl`
(`live/alerts.py`). Filter `status=="sent"` AND `taxonomy=="ACTION_REQUIRED"`. Dedup
on `(key, ts)` vs a runner state file (key = `stable_alert_key()` sha256[:24]). Skip
`suppressed_duplicate`. Schedule 300s, `flock`-guarded.

**Classification (script, the load-bearing safety step).** A deterministic table
maps title/taxonomy → one of:
- **OPERATIONAL / live-state / model / data** (PREFLIGHT-FAIL freshness/dormancy,
  broker errors, FAILED-EXIT, stale model) → **ntfy a human diagnosis, NEVER
  auto-change.** Most live alerts land here → script-only, 0 agents.
- **KNOWN code bug** (matches the error catalog, e.g. a recurring import/contract
  signature) → apply the catalog's templated fix in a `/tmp` clone via **script**,
  open PR, ntfy. No agent.
- **NOVEL code bug** (Traceback/NameError not in the catalog) → the *only* branch
  that spawns a subagent.
- **UNKNOWN** → ntfy a human. No agent.

**Novel-code-bug auto-fix (subagent — the one expensive branch).** Headless
`claude` with the error context + strict guardrails: work ONLY in a `/tmp` clone
(NEVER the live tree); root-cause from logs (read-only), reproduce, fix, **add a
regression test**, run tests, push a branch, open a PR (`fixed by <agent>` + a
`doc/progress/` note), STOP. ntfy "auto-fix PR #N opened…" or "could not auto-fix…".

**Guardrails:** rate-limit (≤2 open auto-fix PRs, ≤N/hr); dedup; `--dry-run`;
kill-switch (STOP file/env); never self-merge; never live-tree git; agent-spawn cap.

## 3. Loop 2 — post-daily reviewer
**Trigger (script):** scheduled ~14:15 PT, or detect today's `=== daily_104
finished ===` marker; idempotent (dedup on `run_id`). Read-only; advisory; never
trades.

**Phase A — decision-tree health (100% script, no LLM):**
`validate_decision_trace_integrity(run_id)` (13 checks) + `gate_verdicts` /
`decision_ledger.db` vs `live_state` (selected-but-blocked, gate↔skip_buys) +
conviction-admits / freshness / model_contract. Any failure → script POSTs ntfy
"decision-tree problem: «detail»".

**Phase B — trade-reliability (script computes; agent optional):**
A **script** gathers every signal and applies **rule-based flags** — no agent
needed to FLAG:
- `portfolio_weights.py` → cash%, HHI, effective-N (flag cash-drag > X%, HHI > Y).
- `technical_battery.py` → trend/RSI/vol/rel-strength (flag technically-broken
  holds).
- join `data/fmp_harvest/` analyst (price targets, grades) → implied upside per
  name (flag overweight-but-low-upside, or sell-rated holds).
- fundamentals from `data/` (flag deteriorating).
If **no flag trips** → write a dated digest, **no ntfy, no agent**. If a flag trips
→ either ntfy the scripted flags directly, OR (config) spawn ONE subagent to write
the human-readable keep/trim/cut synthesis. Default: ntfy the scripted flags;
agent-synthesis is opt-in.

## 4. Cross-cutting guardrails
- Every change via PR + Codex review; **never self-merge** (agent-pr-loop merges).
- Subagents (when spawned) NEVER `git` in the live tree; `/tmp` clones only; NEVER
  touch live `state/model/data`.
- **Verify-before-asserting:** every emitted finding cites the data/log it came
  from (the 2026-06-26 rule).
- Idempotent, deduped, rate-limited, `flock`, `--dry-run`, kill-switch; **agent
  spawns are capped and logged** (so token cost is bounded + auditable).

## 5. Where code lands (proposal)
- Orchestrator: `renquant-orchestrator ntfy-responder` + `post-daily-review`
  subcommands — the **script core** (poll/triage/checks/flags + prompt builders for
  the rare agent branch), a new module mirroring `agent_workflows.py`.
- `RenQuant/scripts/`: wrapper shells + launchd plists, mirroring `agent_pr_loop.sh`.
- A versioned **error catalog** (yaml/json) mapping known errors → class →
  templated fix, so recurring bugs never need an agent. Grows over time.
- Reuse: `live/alerts.py`, the `trade-review` scripts, `validate_decision_trace_integrity`.

## 6. Open questions for Codex
1. CODE-vs-OPERATIONAL classifier conservatism (hard line: never auto-fix anything
   touching live state/model/data).
2. Loop 1: auto-fix novel bugs, or only open a **draft** PR + ntfy?
3. Agent-spawn caps + token budget per cycle/day.
4. Phase-B: ntfy scripted flags only, or allow the opt-in agent synthesis?
5. Error-catalog format + how a fixed novel bug graduates into a scripted entry.
6. Dedup window + escalation when a `suppressed_duplicate` becomes a new incident.

## 7. Rollout
- **Phase 0:** both loops **dry-run** (detect + log + ntfy "would do X", no PRs, no
  fix-agents).
- **Phase 1:** Loop 2 live (read-only, script-only flags — inherently safe).
- **Phase 2:** Loop 1 with the **scripted** classifier + catalog only (still 0
  fix-agents). 
- **Phase 3:** enable the novel-bug fix-agent, after Codex signs off on the
  classifier + caps.
