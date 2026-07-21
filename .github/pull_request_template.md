<!-- Keep this body SHORT. The durable detail lives in doc/progress/<date>-<slug>.md. -->

## What
<one paragraph — what changed and why, in brief>

## Checklist (repo contract)
- [ ] **Added `doc/progress/<date>-<slug>.md`** — STATUS / WHAT / WHY-DIR / EVIDENCE / NEXT (~12 lines; end EVIDENCE with a `` `[VERIFIED — ...]` `` tag). **Required — CI (`require-progress-doc`) enforces it.**
- [ ] The progress doc is the **single durable record** — this PR body and any `doc/research/` artifact are **not** duplicated into it.
- [ ] Tests pass (`make test`), or this is docs-only (say so).
- [ ] English throughout; no live production inputs touched; not self-merged (Codex reviews).
- [ ] **Gate design rule (GOAL-5 AC6):** if this PR adds/tightens a HARD capital-admission gate (can take a name or the book from tradeable→not-tradeable via `raise` / zero-candidates / sell-only / buy-block, not a market decision), the progress/design doc states its **governed override path** — *identity* (who lifts it, via what reviewed surface), *expiry* (explicit restore condition + auto-alarm, not "temporary"), *binding* (scoped by fingerprint + provenance in the run bundle). True kill-switches say so explicitly. N/A if no such gate. See `doc/design/2026-07-20-ac6-gate-design-rule.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
