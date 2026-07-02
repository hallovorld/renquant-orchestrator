# #210 governance convergence — two-path Final, Fix-3 fail-closed, expected terminal state (#223 amendment A3)

STATUS: delivered (docs-only RFC amendment integration)

WHAT: Folded amendment A3 from `doc/design/2026-07-01-104-105-design-review-amendments.md`
(umbrella PR #223, already Codex-converged) into the canonical
`doc/design/2026-06-30-model-freshness-governance.md` (RFC #210), so a future implementer
reads the corrected governance directly in the RFC rather than needing to cross-reference a
separate review doc:

- **A3.1 — §6 Final row rewritten as two-path authorization.** The 60→28 `model_staleness_days`
  ceiling flip previously read "only after Phases 1–4 and the §5 experiment authorise the
  tighter ceiling" — hostage to §5 machinery that, per §5.0's own audit, will likely fail closed
  on the historical registry and need years of prospective logging (§5.6) to accrue enough
  independent 60d outcomes, indefinitely deferring the operator's recorded 2026-06-30 freshness
  directive. Mirrors #208 §9.3a's already-adopted structure: the ceiling may now be adopted via
  EITHER (a) the §5 experiment's authorization, OR (b) a separate, explicitly recorded operator
  decision (risk-policy constant, monitor-guarded, with a pre-registered rollback trigger). Added
  a full explanatory paragraph after the rollout table distinguishing the ceiling (safe for
  operator judgment, since the observe-only Phase-1 monitor is what actually enforces it day to
  day) from Pillar 3's best-of-recent fallback (a genuine causal claim, left **untouched** —
  still fully §5-gated and DEFERRED, deliberately not extended the same two-path option).
- **A3.2 — Fix-3 (structural placebo floor) reclassified fail-closed.** §4.3.1's failure taxonomy
  previously listed Fix-3 under MECHANICAL/INFRASTRUCTURE (bypassable by the fallback) "only
  while it remains an embargo artifact, not a real leakage signal" — but distinguishing the two
  is exactly what the not-yet-implemented Fix-3 difference test (`real_ic − placebo_ic > margin`)
  is supposed to do; until it exists and is validated, an unattended fallback has no predicate to
  apply that qualifier with, and a genuinely leaky candidate fails the same placebo ceiling the
  identical way. Moved to QUALITY/SUBSTANCE (fail-closed, always); it re-enters the
  infra/bypassable list only once the difference test is implemented and validated, with the test
  itself as the classification predicate. Cross-referenced consistently at all three other Fix-3
  mentions in the file (the §1B diagnostic table's Class column, and the WF-gate REPAIR section's
  own Fix-3 bullet) so none of them still imply placebo-floor failures are safely bypassable
  pre-difference-test.
- **A3.3 — expected terminal state stated up front.** Given the chronic-June evidence already in
  §1B (structural placebo floor + sub-SPY substance across every candidate examined), the likely
  outcome of repairing Fixes 1–3 is the gate finally speaking and saying the live primary has no
  demonstrated edge (Fix-4) — and Pillar 3 cannot rescue that outcome by construction (§4.3.3's
  independent OOS floor still applies to any fallback candidate). Added a new paragraph at the end
  of §1 subsection B stating plainly that every path through this governance framework converges
  on a recorded operator decision (trade by directive, or stop) — the document's *expected* end
  state, not an unresolved edge case. §8 Q5 ("Active-primary escalation") reworded to reference
  that §1 statement rather than posing it as an open question; what remains genuinely open is only
  the *specific* action within that decision (retrain-and-wait / revert-to-PatchTST /
  accept-with-note).
- Added a "Response to the #223 amendment review (A3, 2026-07-02)" table immediately after the
  document header, following this RFC's own existing "Response to Codex round-N review" convention
  (most-recent-first), mapping each A3 sub-point to its resolution and section. Updated the
  REVISION header line to summarize the amendment.

WHY/DIR: PR #223 is an independent, already Codex-converged review of the four merged 105/freshness
RFCs; its own "Proposed amendment order" ranks A3 (governance convergence) as unblocking the
operator's own freshness directive without reviving the deferred statistics loop. This PR does the
mechanical-but-precise work of folding that already-agreed text into the canonical RFC #210, so #210
is self-consistent and doesn't require a reader to hold two documents in their head simultaneously.

EVIDENCE:
- artifact: `doc/design/2026-06-30-model-freshness-governance.md` diff — 1 file changed, 107
  insertions(+), 22 deletions(-). Verified: (a) every "Fix-3" mention in the file (4 total, up
  from 3 — one new cross-reference paragraph added) is now consistent with the fail-closed
  reclassification; (b) the edited `Fix-3` and `Final` markdown table rows retain the same column
  count as their unedited neighboring rows (checked via `awk -F'|' '{print NF}'` against the
  header/sibling rows — the apparent mismatch on the Fix-3 row is a false positive from
  pre-existing escaped pipes `\|aligned_real_ic\|` inside that cell's content, present before this
  edit too, not a malformed table).
- prod or exp: docs-only. No code, config, broker, risk-cap, or sizing change — matches this RFC's
  own STATUS line ("design for review... does not change any code, config, broker, risk-cap, or
  sizing behaviour"). Does not touch `model_freshness_monitor.py` (a separate concurrent PR,
  amendment A1, handles that file's code-level per-recipe-horizon fix).
- existing data: n/a.
- best-known?: yes — every amendment folded here is the FINAL, r2-converged, Codex-accepted text
  from PR #223 (confirmed via that doc's own "Appendix — response map" sections), not a fresh
  interpretation.
- scope: `renquant-orchestrator` RFC #210 text only. Pillar 3 (best-of-recent fallback) is
  explicitly unchanged — still fully §5-gated and DEFERRED, per A3.1's own instruction not to
  weaken it.

NEXT: this PR only integrates the amendment text; it does not itself flip `model_staleness_days`
60→28 (that still requires either the §5 experiment or a separately recorded operator decision per
the new two-path Final row) and does not implement the Fix-3 difference test (a WF-gate REPAIR
code follow-up, tracked separately). A5 (Stage-1 pilot-data measurement pins, #223's next-ranked
amendment) is queued as a follow-up PR.
