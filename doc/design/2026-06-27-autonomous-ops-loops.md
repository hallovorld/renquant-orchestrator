# Design: autonomous ops + PR-review loops (error-responder + post-daily reviewer + PR-review watcher)

2026-06-27. Status: **PROPOSAL for review** (not implemented). Operator request:
self-driving loops, executed mostly by **deterministic scripts** with subagents
only where judgment is irreducible, every change via PR + Codex review, **never
self-merge, never `git` in the live tree, never auto-touch live state/model/data**.

Three loops, ONE operating model:
0. **Loop 0 — PR-review watcher** (§1A): discover new/updated PRs → review Codex's,
   fix Codex's comments on mine, merge good ones (account-separated). This is the
   operator's main repeated workflow; it is a first-class part of this design.
1. **Loop 1 — error-responder**: when an ERROR fires to ntfy, auto-investigate →
   (if a code bug) fix in a clone → open a PR → ntfy; (if operational/live) ntfy
   a human diagnosis, do NOT auto-change.
2. **Loop 2 — post-daily reviewer**: after each daily-full, verify the decision
   tree is sound; if sound, run a fundamentals/technical/analyst trade-reliability
   review; ntfy the operator only when a change is warranted.

This doc grounds all three in the **existing** infra (file:line below) so the build
is assembly, not invention. It is for Codex to discuss/review before any code lands.

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

**Key consequence + PREREQUISITE (not inherited).** Loops 1/2 only ever **open PRs**
and **send ntfy** — they never merge. But this is NOT yet a complete safety
contract: the existing agent-pr-loop would still merge an approved auto-generated
PR, so error→PR→merge is not closed by default. **Prerequisite before Loops 1/2
leave dry-run/draft:** the agent-pr-loop must first be *amended and audited* to
(a) **refuse** any PR labeled `agent:auto-generated` / `agent:manual-hold`,
(b) enforce **current-head approval** (an approval is void if the head advanced),
and (c) enforce **account separation** (a PR is never merged by the account/workflow
that created it). Until that amendment is merged + audited (Phase-2 gate, §6), loop
PRs stay **draft + manual-hold** and a human clears them.

New-loop shape: one launchd plist → one wrapper `.sh` (Keychain+lock) → one
orchestrator subcommand (a **script** that polls/triages/checks) that spawns a
subagent only on the irreducible-judgment branch.

## 1A. Loop 0 — PR-review watcher (the recurring review/fix/merge workflow)
The operator's recurring ask — "review Codex's new/updated PRs, fix Codex's
comments on mine, merge the good ones, be extra strict on design/experiment" — is
itself a loop; formalize it (it currently runs as the 5-min agent-pr-loop, but the
spec must pin its state + separation contract).

**Mostly SCRIPT.** Queue resolution + the deterministic merge are already scripts
(`repos agent --workflow review|fix|merge`); a subagent is spawned ONLY to author a
review or a fix-commit. Per cycle, ideal = 0 agents when the queue is empty.
- **Discover (script):** across the manifest repos, list open PRs → three queues:
  (a) Codex PRs needing my review, (b) my PRs with Codex `CHANGES_REQUESTED`,
  (c) approved-at-head PRs eligible to merge.
- **Current-head + dedup (script):** persist `(repo, pr, head_sha, last_review_sha)`;
  re-review/re-fix ONLY when the head SHA advanced past the one already acted on
  (so a stale review isn't re-emitted; a force-push re-queues). This is exactly the
  race that produced Codex's "review predates your push" here — pin it.
- **Review (subagent, strict):** read the diff, post ONE review with `reviewed by
  claude`. **Extra-strict gate on `design(`/`research(`/`experiment` PRs**: require
  reproducibility, conservative stats (no iid t on overlapping labels), repo-boundary
  compliance (no model training in the orchestrator), and explicit caveats — reject
  otherwise. Never review own PR (account separation).
- **Fix (subagent):** address Codex comments on my PRs in a `/tmp` clone, push,
  comment `fixed by claude`. Genuinely fix valid points; rebut wrong ones with
  evidence — never paper over.
- **Merge (script):** only PRs APPROVED-at-current-head + checks green + no
  `agent:manual-hold`; post the `merged by claude` pre-merge audit marker; **never
  merge a PR this same account authored** (reviewer separation, §4.1).
- **Dry-run rollout:** Phase 0 lists the three queues + would-do actions via ntfy,
  opens/merges nothing.

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

## 4. Safety contracts — HARD DEFAULTS (addressing the Codex review)
These are decided defaults, not open questions. They are the accepted operating
plan; anything looser requires a separate change to this doc.

**4.1 Draft-PR-only + reviewer separation (no autonomous-merge path).**
- Every PR a loop opens is a **DRAFT** and carries the label `agent:auto-generated`
  + `agent:manual-hold`.
- The existing agent-pr-loop merge step is amended to **refuse to merge any PR
  labeled `agent:auto-generated`** until a human (or an agent on a *different*
  account than the one that opened it) removes `agent:manual-hold` and marks it
  ready. So an auto-fix can never flow error→PR→merge on one account/workflow.
  Reviewer separation is enforced by account, not just by marker.

**4.2 Hard allowlist of auto-fix surfaces (not categories).**
Phase-2 auto-fix may ONLY touch files matching an explicit allowlist:
`tests/**`, `doc/**`, and pure-diagnostic read-only scripts under
`scripts/research_*`/`scripts/check_*` that are not wired into the live run.
EVERYTHING else — live trade logic, preflight/gates, broker adapters, state
migration, model artifacts/provenance, data-freshness code, configs, lockfiles —
is **diagnosis-only → ntfy a human**, even if the root cause is "a code bug". A
code bug in a load-bearing path is still a human decision.

**4.3 Untrusted input / prompt-injection.**
Logs, ntfy/alert bodies, model & data artifacts, and trade-review outputs are
**untrusted data**. Subagent prompts quote them **as evidence only, never as
instructions**; the runner wraps them in explicit "DATA, do not follow"
delimiters. Subagents are forbidden from executing any command string copied from
a log/alert/artifact. The triage/classifier runs on a fixed rule table, not on the
free-text body.

**4.4 Loop-2 freshness/provenance gate (degrade to "insufficient evidence").**
Before any keep/trim/cut, the script must check each input's freshness +
manifest: live OHLCV (DataFreshnessGate), `data/fmp_harvest/*` analyst manifests,
fundamentals, the active model's vintage. Any stale/missing input → that lens is
dropped and the verdict degrades to **"insufficient evidence — <what's stale>"**,
never a confident recommendation on stale data (the 2026-06-26 rule, encoded).

**4.5 Standing guardrails + initial NUMERIC defaults.**
PR-only; never self-merge; subagents NEVER `git` the live tree (`/tmp` clones
only) and NEVER touch live `state/model/data`; verify-before-asserting (cite the
source); idempotent, deduped, `flock`, `--dry-run`, kill-switch.
Initial caps (config-overridable, tuned in Phase 0):
- Loop 1: ≤ **3** agent spawns/cycle, ≤ **6** novel-fix agent spawns/day, ≤ **2**
  open auto-generated PRs at a time.
- Loop 0: ≤ **8** review/fix agent spawns/day; reviews never block on agents (queue
  drains across cycles).
- Loop 2: ≤ **1** synthesis agent/day (Phase B), and only when a flag trips.
- Per-spawn token budget ≤ **120k**; daily aggregate ≤ **1M** output tokens across
  all loops, hard-stop + ntfy on breach. Every spawn logged (id, reason, tokens).

## 5. Where code lands (proposal)
- Orchestrator: `renquant-orchestrator ntfy-responder` + `post-daily-review`
  subcommands — the **script core** (poll/triage/checks/flags + prompt builders for
  the rare agent branch), a new module mirroring `agent_workflows.py`.
- `RenQuant/scripts/`: wrapper shells + launchd plists, mirroring `agent_pr_loop.sh`.
- A versioned **error catalog** (yaml/json): known error → class → allowlisted
  templated fix. A novel bug graduates into a catalog entry only after its fix PR
  merges with a regression test (then future occurrences need no agent).
- Reuse: `live/alerts.py`, the `trade-review` scripts, `validate_decision_trace_integrity`.

## 6. Rollout with measurable acceptance gates
Each phase must MEET its criteria (observed in the dry-run logs) before the next.
- **Phase 0 — both dry-run** (detect + log + ntfy "would do X"; no PRs, no fix
  agents). Gate to Phase 1, over ≥10 trading days: false-positive rate < 10% on the
  error classifier; duplicate-suppression correct (0 re-fires within cooldown);
  audited **0 live-tree git ops**, **0 live state/model/data writes**.
- **Phase 1 — Loop 2 live** (read-only, script-only flags; inherently safe).
  Gate: its flags match a human spot-check on ≥5 days; freshness-degrade path
  exercised at least once.
- **Phase 2 — Loop 1 scripted classifier + catalog only** (still 0 fix-agents;
  opens draft PRs from the catalog). **Prerequisite**: the agent-pr-loop amendment
  (refuse `agent:auto-generated`/`agent:manual-hold`, current-head approval, account
  separation — §1) is merged + audited FIRST. Gate: ≤ max-PRs/day honored; reviewer
  separation verified (no same-account merge); spend within cap.
- **Phase 3 — enable the novel-bug fix-agent** (draft PRs only, allowlist 4.2),
  after Codex signs off on the classifier + caps + an audited Phase-2 run.

## 7. Resolved review points (Codex #197)
Round 1 (safety contracts §4) + round 2 (Loop 0 + numeric caps):
- Concrete defaults / draft-only / ntfy-default: §4.1, §4.2.
- Autonomous-merge path closed (label-gated, account-separated reviewer): §4.1.
- Hard allowlist of auto-fix surfaces: §4.2.
- Prompt-injection / untrusted input: §4.3.
- Loop-2 freshness/provenance gate: §4.4.
- **Loop 0 / PR-review watcher** (round 2): §1A — state, dedup, current-head check,
  reviewer separation, extra-strict design/experiment gate, dry-run.
- **Numeric caps + token budget** (round 2): §4.5.
- Measurable acceptance criteria: §6.
- Trailing-whitespace `git diff --check`: clean (was fixed in the safety-contracts
  commit the round-2 review predated).

Round 3 (doc consistency):
- Title/intro reframed to "autonomous ops + PR-review loops"; Loop 0 stated as
  first-class part of the same operating model (intro list).
- §1 "never-self-merge inherited" REWRITTEN: the agent-pr-loop amendment (refuse
  auto-generated/manual-hold, current-head approval, account separation) is now an
  explicit PREREQUISITE before Loops 1/2 leave dry-run/draft, not inherited; wired
  into the §6 Phase-2 gate.
- Progress doc rewritten to the accepted current design (Loop 0 + hard defaults +
  manual-hold + numeric caps), open-questions framing removed.
