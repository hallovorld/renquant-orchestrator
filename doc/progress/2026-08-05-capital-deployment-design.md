# 2026-08-05 — DESIGN posted: why the book is "full" with 47 % cash

STATUS:   planned (design doc only, per operator's "先设计，发 PR，再 impl" — nothing implemented,
          no threshold tuned).
WHAT:     posts `doc/design/2026-08-05-why-the-book-is-full-at-47pct-cash.md`, identifying three
          independent defects behind a book holding 47% idle cash while reporting "no trade": (A)
          `max_concurrent_positions` unset in pinned config so the live cap silently falls back to
          the code's hardcoded 8, and the book already holds 10; (B) the rotation veto names a
          non-binding pair (SOFI→CRWD, ρ=0.30) off a correlation artifact 75 days stale; (C) TSLA
          at 23.5% of equity vs. a 12% BULL_CALM cap.
WHY/DIR:  answers the operator's direct question ("仓位是什么鬼？还有很多现金啊！为什么就仓位满了？
          rotate 为什么没起作用？") — every behavioural fix needs a pin advance, and that batch
          (orch#808) is already blocked on operator authorisation, so this round is design-only.
EVIDENCE: `max_concurrent_positions` absent from the pinned config; book holds 10 positions,
          `open_slots = 8 - 10 = -2`, $5,141 (47%) idle; correlation artifact's `as_of` is
          2026-05-22 (75 days stale) and shows ρ(SOFI,CRWD)=0.30 while the only holding over the
          0.70 veto threshold is PANW at 0.845; TSLA is 23.5% of equity against
          `BULL_CALM.max_position_pct=0.12`. `[VERIFIED — this session, pinned config + correlation
          artifact + trades table read this session]`
          artifact:      pinned config + correlation artifact + `trades` table, all read this session
          prod or exp:   prod — the live pinned config and the live book's own holdings
          existing data: the correlation artifact's own `as_of` timestamp, showing it 75 days stale
          best-known?:   n/a — this is a config/data-freshness audit, not a model-variant comparison
          scope:         "this is the live pinned config and book state, prod, vs. the declared regime caps — no model skill claim is made"
NEXT:     two items cost nothing and unblock the rest — make the rotation veto name the binding
          holding, and measure whether a trim path exists (orch#850 does the latter); everything
          else needs orch#808's pin advance and operator authorisation.

Design: `doc/design/2026-08-05-why-the-book-is-full-at-47pct-cash.md`.

Operator asked, on seeing `no trade … held=10 eq=$10,934`:
*"仓位是什么鬼？还有很多现金啊！为什么就仓位满了？rotate 为什么没起作用？"*

Both questions are correct. Three independent defects, all measured today:

- **A.** `max_concurrent_positions` is **not set anywhere** in the pinned config,
  so the live cap is the code's hardcoded **8**. The book holds **10** →
  `open_slots = −2` → no buy can be admitted, with **$5,141 (47 %)** idle. And
  reaching 10 under a cap of 8 means one buy path does not enforce it.
- **B.** The rotation veto cites `SOFI→CRWD`, but **ρ(SOFI,CRWD) = 0.30**; the
  only holding over the 0.70 threshold is **PANW at 0.845**. The correlation
  artifact is **75 days stale** (`as_of 2026-05-22`).
- **C.** TSLA is **23.5 %** of equity against `BULL_CALM.max_position_pct = 0.12`.

Design-only, per the operator's "先设计，发 PR，再 impl". Nothing implemented,
no threshold tuned — every behavioural item needs a pin advance, and that batch
(orch#808) is already blocked on operator authorisation.

The two items that cost nothing and unblock the rest are named: make the
rotation veto name the binding holding, and measure whether a trim path exists.
