# M1 Stage-1 integration checklist

STATUS: design spec delivered.
WHAT: `doc/design/2026-07-04-m1-stage1-integration-checklist.md` — the M1
      integration spec: cross-repo dependency map, 7 prerequisites, 5-session
      acceptance criteria (with replay audit), risk register, activation sequence.
WHY: all 3 code slices delivered (orchestrator #268/#303/#335, execution #20,
     pipeline #163) but never wired together. M1 is the integration milestone
     that proves the slices compose into a working shadow loop.
NEXT: operator activates per §5 sequence (landing action — ask-first);
      5 sessions → replay audit → M1 AC → unlocks M2 (frozen canary).
