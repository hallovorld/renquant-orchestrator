# Two live-surface tests were alarming on compliant behaviour

STATUS:    delivered. Tests only — two assertions re-aimed, two named
           constants added, no src, no ops script, no config, no live
           surface.

WHAT:      `make test` on `main` has been red on three live-surface tests.
           Two of them are alarms on DESIGNED behaviour, and both are the
           same failure mode: a tripwire pinned to a SNAPSHOT of a moving
           surface instead of to the thing the record actually stakes.

           (1) `test_position_cap_conformance.py::test_the_LIVE_book_is_
           what_the_record_describes` judges live buys against the retired
           BULL_CALM cap of 0.12 — deliberately, so that raising the cap
           cannot retroactively un-breach the 2026-07-28 TSLA/EME event.
           That is right. What it did not do is bound the retired cap to
           its OWN era. The deployed cap moved 0.12 → 0.30 on 2026-08-06
           (strategy-104 e00d935, operator directive), and buys sized
           WITHIN the 0.30 cap that governed them then started registering
           as breaches of a number that no longer applied: SPG 0.1604
           (2026-08-12) and APH 0.1214 (2026-08-14). Applying a retired cap
           forward is the mirror image of the rot the test exists to
           prevent.
           FIX: `CAP_RAISED_ON = "2026-08-06"`; the historical assertion
           now reads only its own era. Post-2026-08-06 buys are judged by
           `test_the_DEPLOYED_cap_is_read_and_stated_not_assumed`, which
           already asserts nothing exceeds the deployed 0.30 — so no
           coverage is lost in either era.

           (2) `test_goal7_arm_b_accrual_probe.py::test_the_LIVE_ledger_is_
           what_the_GOAL7_record_describes` pinned
           `projection.projected is False`. Its own docstring records that
           the FIRST version of this test broke when the Saturday job did
           its job — and the replacement then made the same mistake one
           layer up. `TestItRefusesToProjectFromNothing` is explicit that
           ≥2 cutoffs are exactly when the probe SHOULD project; the third
           append (2026-08-15) gave it three BULL_CALM cutoffs and a
           primary share of 1.0, so the probe started projecting, as
           designed, and the suite went red.
           FIX: assert CONSISTENCY rather than which branch the probe
           takes. If it projects, the date must be in the future AND not
           earlier than the registration's ~2027 estimate (a sooner date
           means the RECORD is stale — the thing worth alarming on). If it
           refuses, the refusal must state why. Neither assertion moves
           when the weekly job appends.

           NOT FIXED HERE — the third red test,
           `test_ops_audit_acks_ledger.py::test_the_LIVE_audit_reports_
           it_as_INFO_not_as_a_finding`, is NOT a stale assertion. The live
           `ops_audit` says `gate-stamp-parity` is `ACKED_BUT_CHANGED`
           (the ack's fingerprint no longer matches the detector's current
           summary) and reports `info: 0`, `findings: 12`, `new: 0`. That
           is real ack-ledger drift, not a test bug, and it needs an
           ack-re-affirmation decision rather than an edited assertion.
           Filed separately; left red on purpose so it keeps being visible.

EVIDENCE:
  artifact:      tests/test_position_cap_conformance.py,
                 tests/test_goal7_arm_b_accrual_probe.py
  prod or exp:   **exp** — docs/tests worktree off main `58cd53a6`. No
                 src, no ops script, no config, no live surface, no deploy.
                 The two ops probes under `ops/renquant104/` are unchanged;
                 only their tests moved.
  existing data: measured on the live surfaces, not assumed —
                 - live cap scan: deployed BULL_CALM cap **0.30**, 37 buys
                   since 2026-07-01, **0** over the deployed cap; over the
                   retired 0.12 cap: TSLA 0.2341 + EME 0.2109 (2026-07-28,
                   run `2026-07-28-live-6194047c`) in-era, SPG 0.1604 +
                   APH 0.1214 post-era [VERIFIED — `ops/renquant104/
                   position_cap_conformance.py --since 2026-07-01`]
                 - live Arm-B probe: 3 rows, cutoffs 2026-08-02 / 08-08 /
                   08-15, all BULL_CALM, `n_primary_matured` 0 of 30
                   needed, cadence 0.154/day, primary share 1.0,
                   `projected_eligible_on_or_after` **2027-05-24**
                   [VERIFIED — `ops/renquant104/goal7_arm_b_accrual_probe.py`
                   under the pytest pythonpath, 2026-08-18]
                 - suite before: `3 failed, 6489 passed, 2 skipped` at main
                   `58cd53a6`; after: the two files run `34 passed`
  best-known?:   yes for the two it fixes. Both replace a snapshot pin with
                 the invariant the record actually stakes, so neither can
                 go red again on designed accrual — and both keep a live
                 tripwire (an in-era breach; a projection that beats the
                 registration).
  scope:        tests only. Deliberately does NOT touch the ops_audit ack
                drift, which is a real finding and stays red.

NEXT:      The GOAL-7 number is the operationally interesting by-product:
           Arm B — the only arm that may CERTIFY the momentum model —
           projects eligibility **2027-05-24**. Under the operator's
           2026-08-18 backtest-replaces-accumulation policy that clock is
           meant to be collapsed by a backtest, and per
           `doc/research/2026-08-18-erratum-clf-backtest-attribution.md`
           orch#1007 is not that backtest.

REVIEW:    codex (haorensjtu-dev).
