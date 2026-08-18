# G-I MoE step 2 — the authorized one-shot screen run: 0/3 not flagged

STATUS:    delivered. The ONE authorized execution of the frozen, reviewed
           runner (spec orch#987, corrected runner orch#990) has happened;
           the one-shot budget is SPENT. All three candidates FLAGGED.
           Results + memo only — no code, no config, no live surface.

WHAT:      Executed `doc/research/data/2026-08-17-gi-moe-screen-derivation.py`
           VERBATIM from orchestrator main `252fa4f6` (byte-identical
           asserted before run; file sha256 `f4f19683…2adc4f`), once, in an
           isolated worktree, against read-only local stores. Commits the
           runner's own outputs (results JSON + IC-series CSV, overwriting
           the pilot's retained copies — pilot versions recoverable at
           `da9b05bb`), the results memo
           `doc/research/2026-08-17-gi-moe-step2-authorized-results.md`, and
           a pointer note in the superseded pilot memo.

           Verdicts (h=20, frozen §5 triage rule): high52w FLAGGED
           (Δ=+0.00799, t=0.483, pos=48.3%); lowbeta FLAGGED (Δ=+0.00432,
           t=0.819, pos=49.4%); quality_gp FLAGGED (Δ=+0.00270, t=1.045,
           pos=49.4% — fails ONLY the block-majority criterion). The pilot's
           "1/3 not flagged" did not survive the pairing correction: every Δ
           moved down, and quality_gp's pass is gone. FLAGGED = deprioritised
           + point-in-time rerun required before any kill; nothing is killed.

WHY/DIR:   Spec §7's sequencing (spec merged → runner committed AND reviewed
           → ONE run) is satisfied for the first time — the pilot ran before
           review and was withdrawn for the unpaired-cross-section defect
           (codex HIGH, orch#990). This run closes G-I step 2: the #984 §5b
           queue now has an evidence-backed triage ordering, and the next
           gate for all three candidates is the point-in-time-universe rerun.

EVIDENCE:
  artifact:      doc/research/data/2026-08-17-gi-moe-screen-results.json +
                 …-ic-series.csv (written by the run);
                 doc/research/2026-08-17-gi-moe-step2-authorized-results.md
  prod or exp:   exp — the authorized one-shot screen; isolated worktree of
                 main `252fa4f6`; read-only inputs (OHLCV, sec_fundamentals,
                 watchlist config); wrote only doc/research/data/ in the
                 worktree; no production path touched.
  existing data: the withdrawn pilot (pilot-era runner `52d198c0`, outputs at
                 `da9b05bb`): 1/3 not flagged (quality_gp Δ=+0.00417,
                 t=1.443, pos=51.7%). Same input digests, same emitter pin
                 `74c22647` — the authorized deltas vs pilot isolate the
                 pairing correction: quality_gp Δ +0.00417→+0.00270 (~35% of
                 measured Δ was the coverage artifact), verdict NOT
                 FLAGGED→FLAGGED.
  best-known?:   yes — this is the only valid (paired) measurement on this
                 corpus, and per the frozen one-shot rule it is FINAL for
                 this corpus; the pilot numbers are withdrawn, not competing.
  scope:         "this is the authorized G-I step-2 triage screen, exp, on
                 the survivorship-tilted current-watchlist corpus; verdicts
                 are FLAGGED/NOT-FLAGGED triage only — vs the withdrawn
                 pilot's 1/3, the corrected answer is 0/3 not flagged. No
                 kill, no admit, no roster change."

NEXT:      the #984 §5b batch proceeds with all three candidates
           deprioritised; any kill decision first requires the
           point-in-time-universe rerun the spec defers to. Separately, the
           orch#990 NEXT item "add runner_sha256 to the results JSON" is
           still open (the frozen runner could not be edited during this
           run); the memo records the digest externally instead.
