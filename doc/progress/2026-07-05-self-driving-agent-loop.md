# Self-driving agent loop behavior specification

STATUS: RFC opened for discussion.
WHAT: `doc/design/2026-07-05-self-driving-agent-loop.md` — formalizes the
      self-driving loop behavior: goal-driven (not task-driven), never idle,
      self-unblocking, parallel by default, ROI-weighted prioritization.
WHY: operator directive 2026-07-05 — agent was passively waiting for reviews
     instead of launching parallel work. The spec codifies the expected behavior
     so it persists across sessions.
NEXT: operator review → amend CLAUDE.md with the §7 behavioral rules.
