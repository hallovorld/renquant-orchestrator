# served-model architecture (solo-xgb vs served z-blend) — EXPLORATORY SCOPING, not a preregistration

STATUS:    **NOT a preregistration; authorizes and decides nothing.** Earlier
           revisions were titled FROZEN and presented as the orch#799 decider.
           Neither was tenable: the 125-fold window was contingent on an
           execution-time feasibility probe, so the sample, episode partition and
           power were unknown at approval; and the regime arm rests on **eight**
           historical BEAR episodes, which is exploratory evidence, not grounds
           for a production-architecture reversal. **Must not be executed as a
           production decider.** No computation was run; no code, production, or
           live-config path is touched.

WHAT:      Reduces this branch to what it can honestly carry: a record of why an
           experiment preregistration in this line could not be frozen, plus the
           constraints a future one must respect. The normative body — hypothesis,
           arms, window, metric, decision rule, actionable-outcome mapping — is
           **deleted, not fenced**; the sibling PR orch#975 showed that fencing
           lets normative text survive inside the fence, four review rounds
           running. Full text remains in git history.

WHY/DIR:   Two blockers, both properties of the data and the process rather than
           of the drafting. (1) A feasibility verification scheduled to run at
           execution time cannot be a precondition of approval — if the window
           depends on it, it belongs completed in the PR that freezes the window.
           (2) **Eight BEAR episodes** is the binding constraint on any
           BEAR-conditional claim here, and a percentile bootstrap over
           dependence-structured episodes does not make it confirmatory. This is
           the same shape as orch#975's blocker, where a 60-day label on a 21-day
           cadence reduced 43 manifest rows to n_eff = 15: in both cases the
           effective sample had to be established BEFORE a decision rule was
           chosen, and in both cases it was chosen first.

EVIDENCE:
  artifact:      `doc/design/2026-08-12-served-model-architecture-experiment-prereg.md`
                 (exploratory scoping + recorded blockers) and this record.
                 **No code, no specification, no experiment definition.**
  prod or exp:   neither — a scoping record for a possible future experiment. It
                 changes nothing, runs nothing, and authorizes nothing.
  existing data: no run was performed and no data generated. The two blockers are
                 process/structural facts about this branch's own contents: the
                 window was declared contingent on an execution-time probe, and
                 the regime arm's episode count is eight. An earlier revision
                 tagged a 125-fold count and a BEAR-power recompute as
                 `[VERIFIED]` citing
                 `doc/research/data/2026-08-02-jobb-gbdt-depth-extension-run001/window_artifacts/`
                 — **a path that resolves in neither the branch nor any local
                 worktree**, for the reviewer or for me. Those numbers are
                 withdrawn rather than re-tagged; an unresolvable citation ends
                 the reader's inquiry with something that does not exist.
  best-known?:   not applicable — this document selects nothing and specifies
                 nothing.
  scope:         "this is a scoping record for the served-model architecture
                 question (solo-xgb vs served z-blend) — NOT a prereg, nothing
                 frozen, executed, or authorized. What it establishes is why an
                 experiment here could not be preregistered: a window contingent
                 on an execution-time probe, and eight BEAR episodes as the
                 binding sample constraint. It makes no alpha claim and proposes
                 no architecture change."

TESTS:     none — doc-only PR; no code touched.

NEXT:      Nothing here authorizes anything and no execution is gated on this
           PR's approval. A future experiment in this line needs a NEW, complete,
           independently reviewable preregistration that (a) commits the FULL
           non-outcome feasibility verification first — all cutoffs, exact PIT
           inputs and version, generator, immutable backtesting pin — and only
           then freezes the resulting window, and (b) establishes dependence-aware
           power for its intended regime partition. It inherits nothing from this
           document.
