# RS-5 down-cap panel spec + frozen M7 thresholds — design PR (prereg)

STATUS:   design / pre-registration deliverable (RS-5 of the unified 107 master plan #231
          M7 row; h2-execution-roadmap §6 RS-5 row: "M7's panel spec + frozen thresholds;
          AC: M7 runs on it"). Docs only — no panel built, no scan run, no data crunched,
          no purchase made, no production/config/capital change.
REVISION: r2 (see Round 2 below for the correction; header updated to reflect current state).
WHAT:     `doc/design/2026-07-02-rs5-downcap-panel-spec.md` — the complete M7 down-cap MVP
          screen specification with every threshold FROZEN before any down-cap evidence
          exists: §1 universe (PIT Russell 2000 via Norgate constituency-by-date; ADV ≥ $5M
          63d-median; price ≥ $5; ≥252d history; exclude ADRs/REITs/non-common; financials
          price-family-only; biotech retained with mandatory ex-biotech sensitivity; target
          800–1,400 names, hard bounds [500, 1,600] with stop-and-amend), §2 survivorship
          protocol (primary constituency-by-date; corrected delisting-return convention —
          vendor proceeds preferred, else -100% for bankruptcy/distress, else inadmissible;
          fallback panel restricted to pipeline-feasibility/exploratory-sensitivity only,
          neither a fallback GO nor NO-GO feeds D3), §3 frozen cost model (round-trip
          25/40/60 bps at ADV ≥$25M / $10–25M / $5–10M; bucket C deliberately above the
          plan's 25–40bps headline; evidentiary justification, not an asymmetric-safety
          claim), §4 scan suite (committed scanners reused —
          sighunt/robustness/regimemom/fundamentals_scan patterns; k=4 factor families with
          ONE pre-declared headline each: mom_12_1, st_rev_21, earnings yield, C2-style
          quality composite; C3-convention shifted-label placebo-clean differences gate;
          block=60/n_boot=2000/seeds {42,43,44}; Bonferroni k=4 ⇒ one-sided 98.75% CIs;
          regime conditioning is diagnostic-only, not gating), §5 frozen GO/NO-GO ((a)
          placebo-clean IC ≥ 0.02 + corrected CI LB > 0, minimum-economic-effect derivation
          not a cost-wedge; (b) net long-only-vs-benchmark Sharpe > 0.5 with realized costs
          — the GATING quantity, L/S demoted to diagnostic; (c) regime robustness split into
          exploratory-only (c1) vs gating (c2)/(c3); (d) sample floors n≥600 dates / ≥200
          names-per-date / avg ≥500 / ≥60% PIT-timestamp coverage; KILL = all family UBs <
          0.02; MISS recorded-and-dropped; D3 consumes the verdict as-is, fallback results
          never feed D3), §6 procurement/build checklist (Norgate trial-first per RS-3
          r2/r3, now with a 4th delisting-proceeds acceptance criterion; script homes;
          evidence paths), §7 machine-readable preregistration artifact (new —
          `prereg_contract.json`, the actual freeze mechanism the runner must validate
          against), §8 explicit non-authorizations.
WHY/DIR:  #231's M7 row requires "frozen thresholds BEFORE running" and RS-5 is due before
          M7 (early Aug). **Round-2 correction**: the original r1 WHY/DIR here claimed C3
          had resolved as a MISS with one M-SIG vote spent — that claim no longer holds. PR
          #249's own round-2 correction found C3's substrate future-contaminated and
          reclassified its verdict to UNADJUDICATED, casting no formal vote at all. This
          spec no longer depends on C3's outcome as a settled prior; M7's verdict must still
          be decision-grade regardless of how C3 eventually resolves. The C3 PLACEBO lesson
          (raw +0.0253 IC entirely explained by a +0.0275 placebo — an empirical fact
          independent of C3's verdict-classification) is still baked in: gates are
          placebo-clean differences only, and the IC bar is 0.02 (> large-cap 0.015) for
          stated minimum-economic-effect/placebo-structure/McLean-Pontiff-decay reasons —
          NOT a cost-conversion (that framing double-penalized costs and has been removed).
          The prior round's "high thresholds are always the safe direction" framing was
          false decision theory (a false NO-GO has real costs too) and has been withdrawn;
          bucket C's conservative cost value is now justified purely on the published spread
          evidence.
EVIDENCE: design/prereg PR — the deliverable IS the frozen spec; no measurement is claimed.

          Canonical evidence-block subfields (`doc/AGENT-RETROSPECTIVE.md` §4(b)):
          ```
          artifact:      doc/design/2026-07-02-rs5-downcap-panel-spec.md (the frozen spec)
          prod or exp:   docs only — nothing run, nothing written outside doc/
          existing data: context verified on origin/main this session — #231 M7 row +
                         h2-roadmap §6 RS-5 row (frozen-thresholds requirement + due date),
                         RS-3 r2/r3 (Norgate = constituency-by-date source, trial-first,
                         $346.50/6mo fixed-term), M-SIG spec (binding design rules + shared
                         CI/multiplicity conventions), C3 doc (PR #249's current corrected
                         content, re-read directly in round 2: verdict UNADJUDICATED, not
                         MISS; raw/placebo IC numbers +0.0253/+0.0275 unaffected by the
                         verdict correction; survivorship direction NOT identified; regime
                         reconstruction confirmed non-PIT with no alternative in this
                         codebase), the four committed scanners' actual factor
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

## Round 2 (Codex review: 7-point decision-invalidity findings)

**Finding.** The spec froze several "safe/conservative" choices that were neither
statistically monotone nor aligned with the deployable strategy: (1) it treated PR #249's C3
result as an established MISS that had already spent one M-SIG vote, when #249's actual
verdict is UNADJUDICATED (substrate future-contamination, corrected in a parallel session
effort) and casts no formal vote at all; (2) the fallback-panel asymmetry (trusting a
fallback NO-GO as decision-grade) rested on an unsupported claim that survivorship bias
always inflates factor ICs — the true bias direction is not identified, so neither a fallback
GO nor NO-GO can be trusted; (3) the delisting-return convention ("carry last price forward")
was asserted conservative but actually INFLATES long-factor returns for bankruptcy/distress
delistings by replacing a large negative terminal return with zero; (4) the primary economic
gate depended on a zero-borrow-fee L/S Sharpe, undeployable given the shorting mandate's
near-prohibition on real small-cap shorts; (5) the regime-robustness leg inherited C3's
invalid, non-point-in-time regime reconstruction; (6) the "high cost thresholds are always
safe" framing was false decision theory, and a separate +0.005 IC cost-wedge double-penalized
costs already charged by the net-return gate; (7) the whole contract was frozen in prose only,
with no machine-readable artifact for an eventual runner to validate against.

**Fix.**
- (1) Removed every claim that C3's MISS is settled, that one M-SIG vote is spent, or that a
  specific P(G106) reading is conditioned on C3's outcome; §0 now states C3's status is
  UNRESOLVED. Kept ONE genuinely verdict-independent citation: C3's raw-IC/placebo empirical
  measurement (+0.0253 vs +0.0275 placebo), reframed explicitly as a methodological lesson,
  not evidence C3's own candidate-level verdict is decided.
- (2) §2 rewritten: fallback panel role restricted to pipeline-feasibility/exploratory-
  sensitivity only; NEITHER a fallback GO NOR NO-GO is decision-grade or may feed D3. A
  procurement slip now makes M7's status INCONCLUSIVE (not NO-GO) pending the primary panel.
- (3) §2's delisting handling reframed: vendor proceeds data preferred (added as a 4th Norgate
  trial acceptance criterion in §6), else a frozen bankruptcy/distress convention of -100%
  terminal return (not carry-forward), else affected labels are INADMISSIBLE with coverage
  loss stated. Mandatory missingness + sensitivity reporting added.
- (4) §5(b) rewritten: the GATING net-return measurement is now an implementable long-only
  top-decile-vs-SPY construction with realized §3 costs; the zero-borrow-fee L/S Sharpe is
  demoted to a factor-diagnostic metric, never gating.
- (5) §4 and §5(c) corrected: regime-derived checks inherit C3's non-PIT regime reconstruction
  (confirmed no PIT alternative exists in this codebase, per #249 §6's search — reused that
  investigation rather than re-doing it). Split (c) into (c1) largest-regime-cell-removed,
  now exploratory-only, vs (c2)/(c3) two-half and yearly-breakdown checks, which remain
  gating since they're pure calendar-time splits with no regime-label dependency.
- (6) §3 and §5's "why 0.02" rationale rewritten: removed the false "high thresholds are
  always safe" claim (a false NO-GO has real costs too) and the double-counted cost-wedge;
  the IC threshold is now justified by a minimum-economic-effect argument (raw signal must be
  strong enough to plausibly survive gate (b)'s SEPARATE, real cost accounting), with costs
  charged exactly once, in gate (b) only.
- (7) Added `doc/research/evidence/2026-07-02-rs5-m7-prereg/prereg_contract.json` — a new §7
  in the spec doc encoding every frozen parameter (universe, survivorship/delisting,
  cost model, factors/estimand/bootstrap/multiplicity, full corrected verdict logic) in
  structured, machine-loadable form. The eventual runner must load and validate against it,
  refusing to run on any deviating parameter. §4's prospectivity claim corrected to state the
  novelty affirmation is necessary but not sufficient (per #249 §8's identical correction) —
  this artifact's own merge commit SHA/timestamp is the actual demonstrable freeze point.

**Evidence:** validated the new artifact parses as JSON (`python3 -c "import json;
json.load(...)"` — passes); read C3's (PR #249) current corrected doc directly for every
citation above rather than relying on memory of its prior, since-withdrawn claims; confirmed
no other `§7`/`§6.1`-style cross-reference in the spec doc broke from the section-renumbering
(old §7 "What this spec does NOT authorize" is now §8).

[VERIFIED — every C3 citation in this round was re-read from PR #249's current branch content
directly (not from the earlier round's since-corrected claims); the JSON artifact was
parse-validated; the full doc was greped for stale cross-references after every edit.]

## Round 3 (Codex review: stale Section 5 contradiction + parity gap)

**Finding.** Section 5's primary-panel gate paragraph still carried the OLD, pre-round-2
asymmetric fallback rule ("a fallback GO is never decision-grade... only a fallback NO-GO is
decision-grade") — a leftover the prior round's fix to §2/D3 never reached, since it lives in
a different section of the same prose doc. This directly contradicted §2's already-corrected
rule (neither GO nor NO-GO from the fallback panel has D3 authority). The PR body was also
still describing the pre-round-2 contract entirely (settled C3 MISS, fallback asymmetry, L/S
gating, regime gating, cost-conversion rationale), and `prereg_contract.json` had no test
proving it actually agrees with the prose it's supposed to freeze.

**Fix.**
- §5's stale asymmetric sentence rewritten to match §2 exactly: "NEITHER a GO NOR a NO-GO
  computed on the fallback panel is decision-grade, and NEITHER may feed D3 under any
  circumstance."
- Full end-to-end re-read of the doc for any other section carrying pre-round-2 language
  (C3-as-settled, L/S-as-primary-gate, regime-as-gating, cost-double-penalization) — found
  none outstanding; every other reference already correctly reflects the round-2 corrections.
- New `tests/test_rs5_downcap_panel_spec.py` (12 tests): a direct regression guard against
  the exact bug found this round (asserts the stale asymmetric phrase is absent and the
  corrected symmetric rule is present in the prose), plus prose-vs-`prereg_contract.json`
  parity assertions for every binding choice Codex named explicitly — fallback authority,
  long-only economic gate, non-gating regime diagnostics, delisting policy enum +
  sensitivity-reporting requirement, multiplicity/factor family (k=4, Bonferroni), bootstrap
  methodology (moving-block, 60-session, 3 seeds), frozen thresholds (IC≥0.02, Sharpe>0.5),
  admissibility/sample floors, and D3 authority mapping. Confirmed the stale text was present
  in the pre-fix commit — this test suite would have caught the exact contradiction this
  review found.
- Confirmed `prereg_contract.json` is genuinely tracked in the PR diff (not untracked-on-disk)
  and revalidated as parseable JSON with every field the review named present with a
  non-placeholder value.
- Rewrote the PR body to describe the current, fully round-2-corrected contract.

**Evidence:** `python3 -m pytest tests/test_rs5_downcap_panel_spec.py -v` → 12/12 passed.
`git diff --stat origin/main..HEAD` confirms `prereg_contract.json` is a tracked addition.

[VERIFIED — ran the new test suite locally (12/12 pass); confirmed the stale phrase was
present in the immediately-prior commit before this fix, proving the test is a genuine
regression guard and not a tautology; re-read the entire spec doc end to end after editing to
confirm no other stale cross-reference survived.]
