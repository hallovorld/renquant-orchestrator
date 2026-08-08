# MoE Stage −1 results — three verdicts from the frozen gate, one prereg defect

STATUS:    delivered as a research record. Nothing deployed, no config or pin
           touched. All thresholds were frozen in the design (orch#910 rev 3)
           BEFORE these runs; none were adjusted after.

WHAT:      `doc/research/2026-08-08-moe-stage-minus1-results.md` — the Stage −1
           replay verdicts, the ΔIC→bps transfer, and the §4.3 amendment
           freezing the SE convention the original spec left open.
           `doc/research/data/2026-08-08-stage-minus1-ic-series.csv` — per-date
           IC series for all three arms (383 rows), the reproduction anchor.
           Design doc §4.3 gains the dated amendment paragraph.

WHY/DIR:   Operator made MoE the P0 goal under a self-driving loop. The frozen
           gate was run; the results reorder the whole line and must live in a
           reviewable record, not in a task description and a session
           scratchpad that dies with the session. Codex review of this PR is
           also the first leg of the double-audit these roadmap-level
           conclusions require.

EVIDENCE:  artifact:      383-date offline replay built from production
                          components (LiveReaders, resolve_universe,
                          train_momentum_artifact, frozen v0/v1_fast params);
                          panel arm from runs.alpaca.db candidate_scores
                          (role='candidate', best run per date) ⋈
                          ticker_forward_returns.fwd_20d
           prod or exp:   experiment — read-only replay over prod data; no
                          production surface written
           existing data: none of these quantities existed before 2026-08-08:
                          no challenger IC history (live shadow lanes have
                          0/4/4 scored dates), no paired sd(Δ), no transfer β̂
           best-known?:   yes — first measurement of every number in the doc;
                          supersedes the design's projections where they
                          overlap (assumed sd 0.15 → measured 0.1233)
           scope:         research record + design amendment only. The CSV
                          carries per-date ICs, not per-name scores.

           The three verdicts (full tables in the research doc):
             1. whole-book switching DEAD  — sd(Δ) 0.1725 slow / 0.1484 fast
                vs frozen 0.0929
             2. per-sector switching DEAD BY 3–5× — sd(Δ) 0.32–0.52 after
                fixing the taxonomy mismatch (readers.sector_of() is coarse
                vendor labels; config sector_map threaded through BOTH arms)
             3. 75/25 panel/slow-momentum rank blend = FIRST PASS —
                sd(Δ) 0.0521, mean Δ +0.0204, t +0.50 at 33 paired dates
           Transfer: β̂ +3308 bps/IC, t(iid) +3.17 vs t(adj) +0.71 →
           prereg left the SE convention unfrozen → gate ruled NOT CLEARED,
           amendment freezes n_eff-adjusted SE for all future runs.

TESTS:     none — docs and a CSV. The CSV was generated from the two session
           JSON series by a script whose logic is quoted in the research doc;
           the replay itself is reproducible from production components.

NEXT:      Recon the orch#905 served-matrix path (pipeline#268 emitter into the
           WF replay, pipeline+backtesting, NOT the orchestrator) — it now
           blocks the only surviving hypothesis (C1 significance) AND the
           economics gate (transfer β̂ at usable power) simultaneously, making
           it the single highest-leverage item in the MoE line.
