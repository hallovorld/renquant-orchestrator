# 2026-08-05 — DESIGN posted: why the book is "full" with 47 % cash

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
