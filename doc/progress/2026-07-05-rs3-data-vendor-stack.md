# RS-3 data vendor stack memo

DATE: 2026-07-05
PR: #398

## What

119-line research memo comparing 6 data vendors (FMP, Polygon, Sharadar,
Norgate, Finnhub, IEX/Alpaca) across PIT fundamentals, analyst consensus,
historical depth, small/mid coverage, API limits, and cost. Includes
3-tier pricing recommendations and roadmap task mapping (N2, N3, M-SIG,
M7, M8).

## Why

Master plan §1 Term IC, RS-3 AC: "subscription list + monthly total +
per-item roadmap mapping." This memo enables the operator to make informed
data subscription decisions.

## Round 2 (codex review)

STATUS: fixed
WHAT: codex blocked on planning quality — the memo recommended vendors by
broad category without pinning each roadmap task to an exact data contract
(fields, PIT semantics, constituent-history need, delivery cadence, first
acceptance test), and it conflated the current FMP snapshot-accrual-with-
`available_at` approach with "a PIT solution" for N2, muddying the very
distinction that matters for M-SIG.
WHY-DIR: codex's framing was correct — "best vendor" by category is theater
without a concrete contract per task, and proxy PIT (what N2 does today) is
not the same claim as true as-reported PIT (what Sharadar sells); blurring
them risks pre-authorizing spend the actual task doesn't need (N2 does not
need upgrading — its own spec only requires proxy PIT) or under-scoping a
need that does require it (M-SIG C1's HISTORICAL backtest, not its live
signal, is the piece that would ever need true PIT, and only conditionally).
EVIDENCE: added an explicit proxy-vs-true-PIT terminology section up front;
reworked §3 into six per-task contracts (N2, N3, M-SIG, M7, M8, S10), each
with named fields, PIT requirement, constituent-history requirement,
delivery cadence, a concrete first acceptance test (e.g. M7: cross-check
Norgate's historical constituent list against a public secondary source for
≥95% match before running the full backtest), and a spend-justification
trigger tied to a specific future condition, not a general "would be nice."
Fixed the two remaining conflation spots in §4/§5 (FMP's "snapshot PIT"
label → "proxy PIT"; Sharadar's "upgrade N2 to genuine PIT" → correctly
scoped as an M-SIG-C1-historical-backtest-only capability). Grep-verified no
remaining "PIT solution"/upgrade-N2 language survives anywhere in the file.
NEXT: none — memo is implementation-grade per codex's checklist.
