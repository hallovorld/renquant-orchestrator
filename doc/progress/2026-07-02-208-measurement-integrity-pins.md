# RFC #208 — Stage-1 measurement-integrity pins (amendment A5.1-A5.3)

STATUS: delivered (docs-only RFC amendment integration)

WHAT: Folded amendment A5, sub-points 1-3, from
`doc/design/2026-07-01-104-105-design-review-amendments.md` (PR #223, already
Codex-reviewed and converged) into the canonical RFC it amends,
`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`
(#208):

1. **§6 gate-input census.** The RFC's four-class (A/B/C/D) no-leak replay
   test can only check inputs someone actually classified. Added a required
   deliverable: the §8 pipeline-repo slice must produce a gate-input census
   artifact mapping every gate's every input to a class, and the §6 replay
   test must assert against it — an input absent from the census is a test
   failure. Named explicitly the three non-obvious inputs the RFC did not
   previously classify: the regime detector's daily-bar state (ambiguous
   A-vs-B as written), the earnings-blackout calendar, and wash-sale
   `last_sell_dates` — the last one flagged specifically because an intraday
   sell mutates it mid-session, the same bug shape as this repo's own
   STATE-EXT-SELL incident (a stamped-vs-actual mismatch silently mis-gating
   a decision).
2. **§10 pre-declared entry order type.** Added a new envelope row: entry
   order type (market vs. marketable-limit at a pre-declared NBBO±x bps)
   must be pre-declared for all of Stage 1, not left free per-order — it
   dominates implementation-shortfall measurement more than any other
   envelope parameter, and a mixed-order-type pilot corpus would silently
   contaminate the future §9.4 experiment's data.
3. **§11 quote-feed-quality blocker.** Rewrote the "Live-quote data plane"
   Stage-1 BLOCKER: bare Alpaca entitlement + rate-limit headroom is no
   longer sufficient on its own. Now explicitly requires EITHER a
   SIP/consolidated feed subscription OR a recorded, quantified acceptance
   of IEX bias covering both the §6 class-D arrival quote and the §9.2c
   synthetic batch reference — because Alpaca's free-tier feed is IEX-local
   (~2-3% of consolidated volume) and does not carry the primary-listing
   opening-auction print §9.2c's synthetic reference requires at all.

Added a new §22 "Amendment integration map" section (mirrors the RFC's own
existing §16-§21 review-response-map convention) documenting the
disposition of all three points, and a new r13 top-of-file REVISION marker.

WHY/DIR: per the amendments doc's own priority ordering, A5.1-A5.3 "must
precede pilot data collection or the corpus is retroactively dirty" — Stage
1's entire deliverable is a clean corpus of paired execution data (§9 r11
convergence), so these engineering-integrity gaps needed to be closed in the
RFC text before any implementer builds against it, not discovered after
pilot sessions have already run uncleanly.

EVIDENCE:
- Verified before starting (so as not to duplicate scope or build
  speculative code): `RENQUANT_INTRADAY_DECISIONING` (the RFC's own kill
  switch) is unreferenced anywhere in the codebase, and no §6 four-class
  no-leak replay test exists yet. So A5.1's census requirement is correctly
  scoped as a REQUIRED FUTURE DELIVERABLE named in the RFC text — not an
  artifact or test harness built now with nothing real to attach it to.
- This is a docs-only change: `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`
  (§6, §10, §11, §22, top revision marker) + this progress doc. No code,
  config, or test files touched.
- `git diff --check` clean (no whitespace errors).

NEXT: A5.4-A5.7 (loss-budget noise sensitivity scenario, identifiability/
power-prereg requirements list, batch-rotation churn diagnostic, active-path
verification acceptance test) are explicitly NOT addressed by this PR — left
for a separate round. The gate-input census artifact itself, the order-type
enforcement, and the SIP-subscription-or-recorded-acceptance decision are
all still future work belonging to the §8 pipeline/orchestrator build, not
this docs-only integration.

NOTE: a separate, parallel amendment-integration PR (A2, broker-regulatory/
settlement envelope) may also land a "r13" revision marker on this same RFC
file, on a different branch, from the same base commit. The two touch
disjoint parts of §7/§10/§11 (A2: settlement/margin envelope rows +
exits-always-allowed rule + a new §11 verify-then-bind blocker; A5: census
requirement + order-type row + quote-feed-quality blocker) and should not
conflict in substance, but whichever merges second will need a human to
renumber one revision marker and reconcile the two §22-equivalent sections
(A2's may also claim "§22" — check before merging both).
