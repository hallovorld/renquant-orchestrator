# RS-5 down-cap panel spec + frozen M7 thresholds — design PR (prereg)

STATUS:   design / pre-registration deliverable (RS-5 of the unified 107 master plan #231
          M7 row; h2-execution-roadmap §6 RS-5 row: "M7's panel spec + frozen thresholds;
          AC: M7 runs on it"). Docs only — no panel built, no scan run, no data crunched,
          no purchase made, no production/config/capital change.
REVISION: r1.
WHAT:     `doc/design/2026-07-02-rs5-downcap-panel-spec.md` — the complete M7 down-cap MVP
          screen specification with every threshold FROZEN before any down-cap evidence
          exists: §1 universe (PIT Russell 2000 via Norgate constituency-by-date; ADV ≥ $5M
          63d-median; price ≥ $5; ≥252d history; exclude ADRs/REITs/non-common; financials
          price-family-only; biotech retained with mandatory ex-biotech sensitivity; target
          800–1,400 names, hard bounds [500, 1,600] with stop-and-amend), §2 survivorship
          protocol (primary constituency-by-date; documented fallback = current-membership
          panel from the existing ~2,926-ticker local bar store, on which any positive is an
          UPPER BOUND and only NO-GO is decision-grade), §3 frozen cost model (round-trip
          25/40/60 bps at ADV ≥$25M / $10–25M / $5–10M; bucket C deliberately above the
          plan's 25–40bps headline), §4 scan suite (committed scanners reused —
          sighunt/robustness/regimemom/fundamentals_scan patterns; k=4 factor families with
          ONE pre-declared headline each: mom_12_1, st_rev_21, earnings yield, C2-style
          quality composite; C3-convention shifted-label placebo-clean differences gate;
          block=60/n_boot=2000/seeds {42,43,44}; Bonferroni k=4 ⇒ one-sided 98.75% CIs),
          §5 frozen GO/NO-GO ((a) placebo-clean IC ≥ 0.02 + corrected CI LB > 0; (b) net L/S
          Sharpe > 0.5 on the frozen costs; (c) 3-leg regime robustness; (d) sample floors
          n≥600 dates / ≥200 names-per-date / avg ≥500 / ≥60% PIT-timestamp coverage; KILL =
          all family UBs < 0.02; MISS recorded-and-dropped; D3 consumes the verdict as-is),
          §6 procurement/build checklist (Norgate trial-first per RS-3 r2/r3; script homes;
          evidence paths), §7 explicit non-authorizations.
WHY/DIR:  #231's M7 row requires "frozen thresholds BEFORE running" and RS-5 is due before
          M7 (early Aug). Today's C3 MISS (PR #249) leaves the M-SIG stack riding on C4+C2
          with one of three votes already spent — raising D3's dependence on the down-cap
          leg, so M7's verdict must be decision-grade, not retrospectively argued. The C3
          lesson (raw +0.0253 IC entirely explained by a +0.0275 placebo) is baked in: gates
          are placebo-clean differences only, and the IC bar is 0.02 (> large-cap 0.015)
          for stated cost/placebo-structure/McLean-Pontiff-decay reasons. Bar-raising and
          the fallback GO-asymmetry both err toward false NO-GO — the safe direction, since
          GO feeds a structural decision (D3) and NO-GO's fallback (new-data-only) stays
          live.
EVIDENCE: design/prereg PR — the deliverable IS the frozen spec; no measurement is claimed.

          Canonical evidence-block subfields (`doc/AGENT-RETROSPECTIVE.md` §4(b)):
          ```
          artifact:      doc/design/2026-07-02-rs5-downcap-panel-spec.md (the frozen spec)
          prod or exp:   docs only — nothing run, nothing written outside doc/
          existing data: context verified on origin/main this session — #231 M7 row +
                         h2-roadmap §6 RS-5 row (frozen-thresholds requirement + due date),
                         RS-3 r2/r3 (Norgate = constituency-by-date source, trial-first,
                         $346.50/6mo fixed-term), M-SIG spec (binding design rules + shared
                         CI/multiplicity conventions), C3 doc (PR #249, MISS + placebo-
                         inflation numbers), the four committed scanners' actual factor
                         definitions (read from scripts/), and the local fallback substrate
                         (umbrella data/ohlcv: ~2,926 tickers, small caps ANDE/THRM
                         2014-01→2026-05-08, read-only ls/parquet-metadata check only)
          best-known?:   yes — no prior down-cap panel spec exists in this repo; no down-cap
                         number has been computed or inspected (prospectivity holds as of
                         this freeze)
          scope:         M7's measurement contract only; authorizes no build to run outside
                         experiment paths, no purchase, no universe/production change
          ```
          [VERIFIED — every internal citation above was read from origin/main (or the open
          PR branches for C3/RS-6) in this session, not from memory; the fallback-store
          facts (ticker count, ANDE/THRM date ranges, 2026-05-08 staleness) were checked
          read-only against the umbrella data directory this session.]
NEXT:     Codex review; merge freezes the thresholds. Then, in order: (1) Norgate
          Windows/VM + plugin POC and 3-week trial acceptance test (RS-3's gate — schedules
          the purchase decision, not a purchase), (2) `scripts/build_downcap_panel.py`
          (panel to `data/exp/downcap/` with manifest; stop-and-amend if size bounds
          violated), (3) `scripts/m7_downcap_scan.py` citing this doc's merged SHA with the
          prospectivity affirmation, (4) the M7 go/no-go memo in the frozen §5 vocabulary —
          whose verdict D3 consumes. Any threshold change before the scan = explicit
          amendment PR; after the scan = prohibited.
