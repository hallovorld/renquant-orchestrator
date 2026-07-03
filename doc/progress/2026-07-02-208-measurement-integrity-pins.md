# RFC #208 — Stage-1 measurement-integrity pins (amendment A5.1-A5.3)

STATUS: revised after Codex review — stacked on #224 (amendment A2), now r14/§23

**Stacked on #224 — merge #224 first.** This PR's branch is now based on
`design/208-broker-regulatory-envelope` (#224), not `main` directly, so
GitHub will show it as mergeable once #224 merges. See "Revision-numbering
resolution" below.

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

Added a new §23 "Amendment integration map" section (mirrors the RFC's own
existing §16-§21 review-response-map convention) documenting the
disposition of all three points, and a new r14 top-of-file REVISION marker
chained after r13 (#224/amendment A2).

**Revision-numbering resolution (addressing Codex's structural-conflict
finding):** this branch originally claimed r13/§22, the same numbers #224
independently claimed for amendment A2. Resolved by rebasing this branch
onto #224's tip (`design/208-broker-regulatory-envelope`), keeping A2's
r13/§22 content as-is, and renumbering this PR's own revision entry and
section to r14/§23 — a single coherent chain (r12 → r13/A2 → r14/A5),
not two competing claims. PR #227's base branch was changed from `main` to
`design/208-broker-regulatory-envelope` so GitHub reflects the stack.

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

EVIDENCE:
```
artifact:      doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md (RFC #208)
prod or exp:   n/a — design/RFC doc integration, no model or data claim; docs-only, no code/config/
               broker behavior change
existing data: grepped the RFC's own §6 four-class framework and §16-§21 review-response-map
               convention before adding §23, to match structure and vocabulary; verified
               (before starting) that RENQUANT_INTRADAY_DECISIONING is unreferenced anywhere and no
               §6 replay test exists yet, so A5.1's census is correctly scoped as required future
               work, not built speculatively now
best-known?:   this is the Codex-converged A5.1-A5.3 text from PR #223's independent design review,
               further tightened per this round's census-schema finding (see below) — not a first
               draft
scope:         this is doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md,
               docs-only integration; no comparison to an existing "best" numeric result applies
               (not a model/data PR)
```

**Census-schema tightening (this revision, addressing Codex's review):** the §6 gate-input-census
requirement now specifies, per input, the exact fields the future census artifact must record —
owner (which repo/component is responsible for the input), temporal class (A/B/C/D), source
timestamp (when the value was produced), availability timestamp (when it became knowable to the
decision), mutation semantics (can it change mid-session — e.g. wash-sale `last_sell_dates`,
explicitly named as the STATE-EXT-SELL-bug-family case), and fail-closed behavior (what happens if
this specific input is stale/missing/inconsistent) — rather than a looser "map every input to a
class" statement. Also tightened: "an input NOT in the census is itself a test failure" is now
stated as a MECHANICAL CI requirement on the future §6 replay test's own acceptance criteria, not
merely descriptive documentation.

NOTE: the r13/§22 collision with #224 (amendment A2) flagged in the prior revision of this doc is
now RESOLVED — see "Revision-numbering resolution" above. This PR is stacked on #224.
