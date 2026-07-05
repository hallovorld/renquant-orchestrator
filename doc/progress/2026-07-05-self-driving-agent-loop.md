# Self-driving agent loop behavior specification

STATUS: Round 2 (Codex review) — reframed as non-binding, MUST-level rules softened.
WHAT: `doc/design/2026-07-05-self-driving-agent-loop.md` — discusses candidate
      self-driving loop heuristics: goal-driven (not task-driven), avoid idling
      by default, self-unblocking, parallel by default, ROI-weighted
      prioritization.
WHY: operator directive 2026-07-05 — agent was passively waiting for reviews
     instead of launching parallel work. The note discusses candidate behavior
     for discussion; it is not itself a source of binding rules.
WHY-DIR (round 2): Codex correctly flagged that this doc, living in a single
     subrepo's `doc/design/`, was proposing global agent-operating-policy
     changes (including a self-executing "Proposed CLAUDE.md amendment") as if
     merging the PR alone would ratify them. Checked this repo's own
     `doc/memory/README.md` tier model: LONG-tier (binding) changes require
     **operator** authorship — the agent may transcribe, not originate, binding
     policy. This doc was effectively asking to originate LONG-tier rules via a
     design-doc merge, which the tier model doesn't permit. Also softened two
     MUST-level rules Codex named ("every tick MUST produce a substantive
     action", "never wait for a single PR review") plus others found with the
     same fragility (the blocker-response table, the anti-patterns list) — all
     are useful heuristics for the common case but not universally correct
     under quota limits, safety gates, or genuine hard dependencies.
EVIDENCE: `doc/memory/README.md` §1's tier table (`LONG | indefinite, binding |
     operator only (agent transcribes)`) directly contradicts the original
     §7's self-executing "Proposed CLAUDE.md amendment" framing.
NEXT: operator reviews the (now explicitly non-binding) heuristics; if any are
      worth keeping, operator authors or directs verbatim transcription of the
      resulting language into `CLAUDE.md`/`doc/memory/long-term-agreements.md`
      directly, per §7's adoption path.

WHY-DIR (round 3): Codex's round-2 review pointed out the non-binding reframing
     fixed the authority-overreach problem but not the underlying scope
     problem: the doc was still a general agent-operating-policy retrospective
     (loop behavior, delegation, wakeups, cross-repo authorization, whole-
     roadmap terminal-state definitions) — none of which `renquant-orchestrator`
     as a repo owns or enforces. Rewrote the doc from scratch, narrowed to ONE
     concrete orchestrator-repo-owned workflow: how this repo's recurring
     PR-review-sweep loop (check open PRs across repos → fix Codex findings →
     merge when ready → repeat) should sequence and parallelize that specific
     task. Cut entirely (not re-hedged): goal-driven/task-driven framing,
     ROI-weighted whole-roadmap prioritization, the standing cross-repo
     "unblock authorization protocol", and the whole-system terminal-state
     definition — all genuinely out of scope for this repo. Kept and sharpened:
     the PR-review sweep's own tick workflow (list → check reviews+comments →
     fan out parallel fixes → verify-before-reporting → merge protocol) and its
     two concrete anti-patterns (serial review blocking, superseding-PR
     fragmentation), both of which this session's own recurring loop actually
     exercises. New §2 "verify before reporting" section is grounded in a real
     incident this session: a dispatched fix reported success as prose without
     a commit ever landing on the branch (caught only because the parent
     re-checked the raw git ref rather than trusting the summary).
EVIDENCE (round 3): doc word count dropped from ~1450 to ~750 words; every
     remaining section names a concrete, orchestrator-repo-owned action (list
     PRs, check comments, fan out fixes, verify commits, merge protocol) rather
     than a general behavioral claim. `[VERIFIED — self-review against Codex's
     round-2 comment text, this session]`
NEXT (round 3): none — this is the final narrowing round unless Codex finds
      further scope drift.
