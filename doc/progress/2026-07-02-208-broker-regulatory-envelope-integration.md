# Fold the broker-regulatory / settlement envelope into RFC #208 (amendment A2)

STATUS: delivered (docs-only integration; no code, config, or broker behavior change)

WHAT: `doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md` (RFC #208) designed
an intraday order loop with no broker-regulatory / settlement envelope at all — §7/§10/§11 never
bound entries to the account's actual margin/regulatory state. The independent design review
(`doc/design/2026-07-01-104-105-design-review-amendments.md`, PR #223) found this gap as amendment
A2, went through its own Codex r1→r2 round (r1's legacy-PDT premise was superseded and its proposed
"day-trade budget = 0 blocks same-session exits" control was itself unsafe; both withdrawn in r2 on
a **verified**, not remembered, account regime), and was accepted. This PR folds the r2-converged A2
text into RFC #208 as genuine RFC content — not a pointer to the amendments doc — so a future
implementer building the execution/pipeline pieces (per §8's decomposition) needs to read only this
RFC:

- **REVISION header**: new r13 entry recording the verified account facts (margin account, FINRA
  Intraday Margin Standards effective 2026-06-04 replacing legacy PDT, `daytrading_buying_power`
  materially exceeding what the legacy sub-$25k PDT regime would permit relative to equity) and
  pointing to the new §22 integration map. Specific dollar balances are NOT reproduced in the RFC or
  here (Codex finding: they go stale immediately and belong in the protected run bundle for the
  verification date, not a durable, widely-read design doc).
- **§7 (order lifecycle)**: new settlement-accounting bullet — `available` derives from
  `non_marginable_buying_power` today (margin account); the cash-account variant (T+1 settled-funds
  gating) is stated conditionally for a future account-regime change, decided by the new §11
  verify-then-bind check, never hardcoded.
- **§10 (safety envelope)**: two new table rows (intraday margin/buying-power headroom binding
  entries; a broker-reported intraday margin deficit as a Tier-1 halt) plus two new interaction-rule
  bullets — margin/buying-power headroom consumption mirrors `reserved_cash`, and **exits-always-
  allowed**: no envelope/regulatory/budget constraint may ever block a protective exit; constraints
  bind entries only; same-session round trips become a ledger diagnostic, never a hard counter. This
  explicitly inverts the withdrawn r1 proposal.
- **§11 (dependencies & blockers)**: new Stage-1 BLOCKER — verify-then-bind the account's
  broker-effective rule regime, recorded in the run bundle per session; a session aborts (no
  entries, exits still allowed) if the recorded regime differs from what the envelope was designed
  for. This exists precisely because §10's defaults were sized against a regime verified at
  amendment time (2026-07-02), which is not guaranteed to still hold whenever the canary actually
  first runs — rule regimes change, which is exactly what happened once already (2026-06-04).
- **New §22** "Amendment integration — #223 amendment A2": a disposition table (mirroring this RFC's
  own existing §16–§21 review-response-map convention) recording what was folded in and where, plus
  an explicit note that no runtime enforcement of this envelope exists yet — per §8's repo
  decomposition, the order-lifecycle state machine belongs to the (not yet built) execution repo and
  the envelope interaction rules belong to the (not yet built) pipeline repo. This RFC is now the
  spec those future PRs build against.

WHY/DIR: A2 is a **blocking gap** for any live canary session (per the amendments doc's own priority
ordering, amendment #2 of 7) — without this, the RFC's §9.3a canary path has nothing stopping an
entry from being sized against a margin/regulatory state the system never checked. Verified
(independently confirmed in this session, not re-derived from memory): `RENQUANT_INTRADAY_DECISIONING`
does not appear anywhere in the RenQuant codebase, and `execution_reconciler.py` (orchestrator PR
#219) is observe-only accounting/state-machine plumbing with no real order submission — so there is
currently no live order-placement code to attach a runtime check to. That makes this integration
correctly scoped as a docs-only fold-in now (the spec exists and is unambiguous before any
implementer starts on the execution/pipeline pieces), not new safety-critical runtime code, which
would be premature against a Stage that hasn't started building its order-emission path yet.

EVIDENCE:
```
artifact:      doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md (RFC #208)
prod or exp:   n/a — design/RFC doc integration, no model or data claim; docs-only, no code/config/
               broker behavior change
existing data: grepped this RFC's own §16-§21 review-response-map convention before adding §22, to
               match structure; grepped the repo for stale legacy-PDT references (see below) before
               concluding the withdrawn r1 framing does not recur elsewhere
best-known?:   this is the r2-converged, Codex-accepted text from PR #223's independent design
               review — the best-available reconciliation of #208's original (gap-having) envelope
               design against the account's actual verified regulatory regime, not a first draft
scope:         this is doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md,
               docs-only integration of already-reviewed amendment text; no comparison to an
               existing "best" numeric result applies (not a model/data PR)
```
Diff reviewed manually for internal consistency (new §10 rows match the existing table's
column/style conventions; new §22 disposition table mirrors §16–§21's existing format; REVISION
header chains correctly with "Prior: r12 ..." preserved verbatim; confirmed no raw account dollar
figures remain anywhere in the file after the balance-figure fix below). No code changed — nothing
to test/run. `git diff --stat`: 1 file changed
(`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`), insertions/deletions per
the balance-figure correction below.

**Fix (this revision, addressing Codex round-2 review on #224):** the REVISION header and §22 row 1
previously stated specific live-account dollar figures (`daytrading_buying_power ≈ $37.5k` on
`~$10.8k` equity, `≈3.5×`). Codex flagged this: durable, widely-read RFC text should not carry
transient account balances — they go stale immediately and are unnecessary operational detail in a
docs file. Replaced with field-semantics + a dated verification statement (qualitative: margin
account, buying power consistent with the new regime rather than legacy sub-$25k PDT) with a note
that exact figures live in the protected run bundle for that verification date, not this RFC. The
durable, load-bearing finding (margin account, new regulatory regime, sized against
`non_marginable_buying_power`) is unchanged.

Checked for stale references to the withdrawn PDT framing elsewhere in the repo: found
`doc/renquant-system-feature-map.md` mentions a "T+2 settlement, PDT guard" feature-status row and
"sub-PDT multi-day only" language in the shorting-mandate description — both read as references to
the EXISTING 104 (batch, multi-day-hold) system's own settlement/PDT posture, a distinct concept
from the withdrawn 105-intraday-specific "day-trade budget = 0" control, not evidence of the same bug
recurring. Left untouched — out of scope for this docs-only RFC integration, flagging for a human
to confirm rather than editing an unrelated file without full context.

NEXT: the actual runtime implementation is future work, split across three repos per §8's merge
order (execution → pipeline → orchestrator) — none of which exist yet for the intraday order path.
When that work starts, it now has an unambiguous spec (this RFC) instead of needing to separately
consult the amendments doc. A5.1–A5.3 (measurement pins) is the next amendment in the design
review's own priority order, ahead of any pilot data collection.
