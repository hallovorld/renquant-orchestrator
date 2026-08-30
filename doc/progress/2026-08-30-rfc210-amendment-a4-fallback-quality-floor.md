# 2026-08-30 — RFC#210 amendment A4: fallback promotion requires the quality floor; ratchet removed

STATUS:    delivered (design amendment only; code PR in renquant-backtesting
           follows and references this doc).

WHAT:      Adds Amendment A4 to `doc/design/2026-06-30-model-freshness-governance.md`:
           Pillar 3 fallback promotion requires `genuine_ic ≥ 0.02` (the §5.2
           Fix-3 floor) plus infra-only failure classes; the implemented
           "candidate genuine_ic > served fallback's" ratchet is removed; the
           28-day ceiling stands with no production relaxation knob; a lapse =
           buys blocked / exits continue is the designed safe state; the
           2026-08-04 promotion is recorded as a policy breach.

WHY/DIRECTION:
           A3.2 already made placebo-floor failures fail-closed. The code
           promoted one anyway (served genuine_ic +0.0029) and then could never
           promote again (candidates → +0.0000) while the ceiling lapses the
           served model on 2026-08-31. The admission state of the live book was
           being decided by which of two contradictory rules fired first. The
           operator's 2026-08-30 directive was to push forward in the
           maximum-benefit direction without further questions; the
           maximum-benefit direction for a $10.8k book trading a zero-IC signal
           at 5.5× turnover is to stop admitting unvalidated models.

EVIDENCE:  §4(b) block — this PR makes no new model/data claim; it cites:
           - served artifact `artifacts/prod/panel-ltr.alpha158_fund.json`
             `metadata.wf_gate_metadata.passed=false`,
             `promotion_basis=freshness_fallback_rfc210`,
             `fallback_genuine_ic=+0.00289`, `trained_date=2026-08-02`
             `[VERIFIED read-only 2026-08-30]`;
           - `wf_gate/freshness_fallback.py:182-198` ratchet rule; candidate
             `Sanity result` lines 2026-08-18..23: genuine_ic +0.0006 →
             +0.0000 `[VERIFIED logs/weekly_wf_promote, daily_retrain_alpha158_fund]`;
           - `rfc210_license.py:29,94-104` (28-day ceiling, no config override
             present) and `preflight.py:553-586` (sell-only soft pass; full run
             hard fail) `[VERIFIED]`;
           - ledger forensics: 33 round-trips realized +$4.32, 5.55× turnover,
             book +1.5% vs SPY +2.5% (memory `win-rate-is-backtest-not-live`).

NEXT:      (1) codex review of this amendment; (2) renquant-backtesting PR
           `fix/freshness-fallback-quality-floor` implementing rule 1 with
           tests (candidate at 0.019 → refused; 0.02 → eligible; ratchet code
           deleted; verdict text names the floor); (3) umbrella PR
           `fix/buy-blocked-alert-truth` (urgent alert + honest preflight text);
           (4) Monday 2026-08-31: expect BUY-BLOCKED; verify exits ran in the
           sell-only pass and record the first lapse day.

Memory tier: LONG (RFC#210 is a binding governance rule) — the amendment is in
the RFC itself; no `long-term-agreements.md` row is added because the rule text
lives in the RFC and the ledger points at it.
