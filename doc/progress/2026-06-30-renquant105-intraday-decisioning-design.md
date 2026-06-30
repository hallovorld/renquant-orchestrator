# renquant105 intraday-decisioning architecture — design

STATUS: RFC opened for review. Engineering design only (the prerequisite); no build yet — design first.

WHAT: An RFC (`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`) that reframes renquant105 as an ENGINEERING evolution from 104's 盘后 (after-close batch) decisioning to 盘中 (real-time, during-session) decisioning, and specifies the target architecture, the staged evolution path (Stage 1 = decouple entry timing from the batch by repointing the existing intraday loop from sell-only to full decisioning), engineering contracts/risks, and the explicit downstream boundary (model rework is NOT the prerequisite).

WHY/DIR: Operator re-clarification 2026-06-30 — I had drifted a whole session into alpha/signal search; 105's core is the engineering of real-time intraday decisioning, the model is downstream, and **the prerequisite is the engineering design.** Build on prior work, do not rewrite: the RFC is reuse-first (intraday loop, InferencePipeline, gate-stack, model serving, decision-ledger, decision-tree-review, safety mechanisms, methodology spine all carried over). Goal = catch the trend entry in real time during the session instead of the next-day batch; holding period stays multi-day (not HFT/day-trading).

EVIDENCE:
- §4(b): artifact = `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md` (this PR, orchestrator); prod-or-exp = DESIGN/RFC (no code, no live change); existing-data = current 104 flow (`daily_104.sh` after-close batch + `com.renquant.intraday` sell-only loop) is the documented baseline; best-known? = first written architecture for the 盘后→盘中 evolution under the corrected (engineering-first) framing; scope = orchestrator control-plane design only, model rework explicitly out of scope (Stage 3 / downstream).
- Today's alpha screens (directional / analyst-orthogonal / minute / breadth) were all honest NULLs — recorded as the WRONG question for 105's prerequisite, not as 105 progress.

NEXT: Operator/Codex review of the four open questions (cadence, entry-timing baseline, safety-envelope numbers, whether Stage 1 is the right minimal first build). On agreement, scope Stage 1 (repoint the intraday loop to full decisioning + dedup-vs-pending + intraday safety envelope) as the first build, measurable A/B vs the next-day-batch baseline via the decision-ledger.
