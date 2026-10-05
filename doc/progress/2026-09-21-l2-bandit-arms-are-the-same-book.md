# 2026-09-21 — MoE L2 paper bandit: the four arms are the same live account; the bandit now refuses

STATUS:    delivered — code + tests in this PR only; the scheduled L2 bandit
           job will exit 1 (REFUSED) daily until per-lane paper books exist.
           No live log, DB or config written.

WHAT:      `l2_paper_bandit` refuses to price arms that are the same book as
           the champion: marks within 0.5% AND broker cash identical to the
           cent on the latest >= 5 consecutive shared dates (r2; mark-only
           is a labelled legacy-schema fallback, not proof of same account).

WHY/DIR:   The shadow lanes snapshot the live Alpaca account, so the reported
           -3.5% "mixture minus champion" was a coverage artefact, not regret.

EVIDENCE:  artifact: scratch `--log-dir` run of the patched module against
           data/runs.alpaca*.db → REFUSED 39/39, 34/34, 34/34 shared dates
           (r1); r2 re-run 2026-10-03 → REFUSED, latest 22 / 23 / 23
           consecutive cent-identical cash dates, nothing written.
           prod or exp: exp (read-only against prod DBs; real log untouched).
           existing data: yes — existing lane DBs + l2_moe_mixture.jsonl (108 rows).
           best-known?: yes — identity check at the current snapshot schema.
           scope: L2 paper bandit only; no scorer / strategy change.

NEXT:      Design PR for per-shadow-lane paper books (allocation machine §2
           premise repair); re-run the bandit from those books.

## Conclusion

The L2 paper bandit (`renquant_orchestrator.l2_paper_bandit`, live since
2026-09-03) has been reporting `mixture_minus_champion ≈ −3.5%` and "every
shadow arm trails the champion". That number measures nothing. Each arm's
daily return is `live_state_snapshots.portfolio_value` of its lane DB, and the
three shadow lanes run READ-ONLY against the SAME Alpaca account: their marks
are within 0.5% of the champion's on 39/39, 34/34 and 34/34 shared dates
(median 1.5–2.7 bps, max 34 bps); since 08-31 `cash` is identical to the cent
on every shared date (`n_holdings` is lane-local and does not always agree —
see Corrections) `[VERIFIED: read-only query on data/runs.alpaca*.db]`. Same-day returns agree within ≤ 9 bps. The lanes
hold no paper book.

The −3.5% is coverage: the shadow DBs start 07-28 / 08-04 while the champion
starts 04-24, so on the 71–76 dates the shadow arms were not marked the
champion compounded +3.6% / +8.5% and the arms sat at 1.0. `arm_value ×
champion_compounded_on_unheld_dates` = 1.0646 / 1.0682 / 1.0672 against the
champion's 1.0683 — residual ≈ 0 `[VERIFIED from l2_moe_mixture.jsonl, 108 rows]`.

The §2 contract (orch#918) presumed "expert PAPER books that the shadow-lane
infrastructure already marks daily". That premise is false, so the regret
series and the daily MoE readout (hand-sent 09-15 / 09-16 as "NOT a prod
candidate, −3.5%") were coverage artefacts — retracted to the operator. The
arithmetic of the bandit is correct; its input is not what the design assumed.

## Change

- `load_book_identity` / `same_book_as_champion` (r2, after codex r1): a
  shadow arm is the same account when marks are within 0.5% AND broker
  `cash` is identical to the cent on the latest ≥ 5 consecutive shared dates
  where both schemas carry cash. Mark proximity alone is not conclusive (two
  books with shared starting capital can stay within 50 bps for a week). Only
  when fewer than 5 such dates exist does the mark-only rule (≥ 90% of shared
  dates) apply, and its evidence is labelled "distinctness NOT established;
  insufficient to assert the same account". `n_holdings` is reported, not
  required (see Corrections).
- `main()` refuses (`REFUSED`, exit 1, nothing appended, no mixture written)
  when any arm is the same book, naming the evidence per arm. Fewer than 5
  shared dates → not judged. The self-verifying log contract is unchanged.
- Tests: same-account arms are refused and nothing is published; arms with
  their own books are priced; too-few-dates / column-less fixtures are not
  judged; r2 adds: close marks + different cash are priced (codex's
  adversarial case), the trailing window decides (distinct history does not
  rescue an arm that is the same book now; one distinct latest date does),
  and the legacy fallback is labelled insufficient.
  `tests/test_l2_paper_bandit.py`: 19 passed; 4 of them fail on the r1 code.

## Evidence (§4(b))

Patched module against the live DBs with a scratch `--log-dir` (the real log
untouched): `REFUSED — profile_blend: marks within 0.5% of the champion's on
39/39 shared dates (100%) …; profile_blend_mom 34/34; profile_blend_rb_mom
34/34`. `[VERIFIED 2026-09-21]`

r2 (2026-10-03), same scratch procedure against the live DBs
(`--data-root` umbrella, `--log-dir /tmp/l2scratch_1129`, empty afterwards):
`REFUSED — profile_blend: … cash identical to the cent on the latest 22
consecutive corroborable shared date(s) (… 46 corroborable in total;
lane-local n_holdings equal on 11 of those); profile_blend_mom: … latest 23
(… 42 …; 12); profile_blend_rb_mom: … latest 23 (… 42 …; 12)`.
`[VERIFIED 2026-10-03]`

## Corrections (r2, 2026-10-03)

- r1 said `n_holdings` was "identical on every shared date" since 09-03. It is
  not: on 2026-10-02 the champion records 5 and `shadow_blend` 6 at identical
  cash 5316.84; it agrees on only 11 of the latest 22 cash-identical dates for
  profile_blend `[VERIFIED — read-only query on data/runs.alpaca*.db,
  2026-10-03]`. The shadow lanes write `n_holdings` from their own state, so it
  is not an account-identity field and r2 does not require it.
- r1 dated the cash identity "since 09-03"; the cent-identical run actually
  starts 2026-08-31 for profile_blend (earlier dates differ by dollars).

## What this does NOT do

It does not make the lanes comparable. That needs a paper book per shadow
lane — simulate fills from the lane's own recorded daily decisions, mark
daily, charge the cost model — and a bandit re-run from those books: a design
PR (allocation machine §2 premise repair). Until then the scheduled job exits
1 daily with the reason above, which is the honest state; the memory record
is `moe-l2-bandit-audit-20260921`.
