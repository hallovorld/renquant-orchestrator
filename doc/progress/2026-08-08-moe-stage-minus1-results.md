# MoE Stage −1 preliminary diagnostics — one prereg defect, one blend hypothesis   (PR #911)

STATUS:    delivered as a research record. Nothing deployed, no config or pin
           touched. All thresholds were frozen in the design (orch#910 rev 3)
           BEFORE these runs; none were adjusted after. Relabelled after codex
           r1 of this PR: these are 33-date preliminary diagnostics, NOT the
           preregistered 541-date gate measurement — the kill/pass rule cannot
           execute for any arm until orch#905 lands the served matrix.

WHAT:      `doc/research/2026-08-08-moe-stage-minus1-results.md` — the Stage −1
           preliminary diagnostics on the 33-date panel overlap, the ΔIC→bps
           transfer read, and two design amendments freezing conventions the
           original spec left open (§4.3 SE convention, §4.4 sd estimator).
           `doc/research/data/2026-08-08-stage-minus1-ic-series.csv` — per-date
           whole-book IC series for all three arms, the reproduction anchor
           (383 data rows `[VERIFIED — wc -l = 384 incl. header]`; 33 non-null
           panel rows, 364 slow, 324 fast `[VERIFIED — recount this session]`).

WHY/DIR:   Operator made MoE the P0 goal under a self-driving loop. The frozen
           inequality was applied to the only overlap that exists; the reads
           reorder the whole line and must live in a reviewable record, not in
           a session scratchpad that dies with the session. Codex review of
           this PR is the first leg of the double-audit these roadmap-level
           reads require.

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
                          0/4/4 scored dates `[VERIFIED — prior work, design
                          §2 lane table, orch#910]`), no paired sd(Δ), no
                          transfer β̂
           best-known?:   yes — first measurement of every number in the doc;
                          supersedes the design's projections where they
                          overlap (assumed sd 0.15 → measured 0.1233
                          `[VERIFIED — panel_ic sd ddof=0 from committed CSV,
                          recomputed this session]`)
           scope:         research record + design amendments only; 33-date
                          overlap diagnostics, NOT the frozen 541-date gate.
                          The CSV carries per-date whole-book ICs, not
                          per-name scores.

           The three diagnostics (full tables + grading in the research doc):
             1. whole-book switching over the gate bound ~2× — sd(Δ) ddof=0
                0.1725 slow / 0.1484 fast (ddof=1: 0.1752 / 0.1507) vs frozen
                0.0929 `[VERIFIED — recomputed from committed CSV this
                session; convention-insensitive]`
             2. per-sector switching over the bound 3–5× — sd(Δ) 0.32–0.52
                after fixing the taxonomy mismatch (readers.sector_of() is
                coarse vendor labels; config sector_map threaded through BOTH
                arms) `[VERIFIED — prior work, 2026-08-08 session replay;
                per-name inputs not committed → data points, not conclusions]`
             3. 75/25 panel/slow rank blend = HYPOTHESIS GENERATED, not a
                pass — sd(Δ) ddof=0 0.0521, mean Δ +0.0204, t +0.50 at 33
                paired dates `[VERIFIED — prior work, session replay; blended
                series not committed → not reproducible from PR artifacts]`.
                Not a frozen candidate (design C1 = equal-weight blend; the
                25% weight and winner rule were never preregistered); needs a
                prereg amendment + OOS evaluation on the 541-date matrix
                before any Stage 1 claim.
           Transfer: β̂ +3308 bps/IC, t(iid) +3.17 vs t(adj) +0.71,
           break-even ΔIC 0.0030 `[VERIFIED — prior work, session replay;
           top-3 return series not committed → data point]` → prereg left the
           SE convention unfrozen → gate ruled NOT CLEARED; §4.3 amendment
           freezes n_eff-adjusted SE, §4.4 amendment freezes sample SD
           (ddof=1), both for all future runs.

TESTS:     none — docs and a CSV. The whole-book stats were re-derived from
           the committed CSV this session (pandas recompute; both ddof
           conventions). The per-sector / blend / transfer numbers derive
           from session-scratch series that were NOT committed; the research
           doc grades them hypothesis / data-point and the 541-date rerun
           must commit its derivation artifacts.

NEXT:      (a) design amendment preregistering the allowed blend weight set
           and winner rule BEFORE the 541-date data exists to pick a winner;
           (b) recon the orch#905 served-matrix path (pipeline#268 emitter
           into the WF replay, pipeline+backtesting, NOT the orchestrator) —
           it blocks the first valid gate result for every arm AND the
           economics gate simultaneously, the single highest-leverage item in
           the MoE line.
