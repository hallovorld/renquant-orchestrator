# Renew the `gate-stamp-parity` ack (ledger key `e3ecdd6587cdaf4e`)

Date: 2026-08-29 (read from `date`) · Branch: `ops/renew-gate-stamp-parity-ack` (from
`origin/main` @ `ef27bb80`) · Companion: `doc/progress/2026-08-29-twin-parity-manifest-live-broker.md`
(where the expiry was surfaced).

## Bottom line

The first ops-audit ack expired **2026-08-19**, not on its written `expires_at 2026-09-05`:
`ack_expiry` (`ops/renquant104/rq104_degradation_sentinel.py:527-574`) takes the EARLIEST of
`expires_at`, any date in `clears_when`, and `acked_at + ACK_MAX_AGE_DAYS` (=14), so
`acked_at 2026-08-05 + 14d` bound it. Since then `ops/ops_audit.py` has reported
`gate-stamp-parity` as `ACK_EXPIRED` and `tests/test_ops_audit_acks_ledger.py::test_the_LIVE_audit_reports_it_as_INFO_not_as_a_finding`
fails on the deploy machine. This PR renews the ack as a reviewed ledger edit; the situation
it covers was re-verified today; the numbers moved and are re-recorded.

## What is acked (and only this)

The gate-stamp parity CENSUS: 16 `panel-ltr.alpha158_fund*` artifacts under
`backtesting/renquant_104/artifacts/prod` carry BOTH a canonical (`metadata.wf_gate_metadata`)
and a legacy (top-level) WF-gate stamp; **0 of them are SERVED by a pinned config** — measured
by the detector itself (`served_artifact_basenames()` intersects every pinned
`strategy_config*.json` selection with the both-copy set) and carried in the fingerprinted
line. The one artifact whose two stamps disagree on the verdict
(`panel-ltr.alpha158_fund.weekly_rollback_2026-07-06.json`, canonical `passed=False`, legacy
`passed=True`) is explained by the legacy copy's `operator_authorized_override=true` with the
recorded 2026-07-05 reason.

## What is NOT acked

`booster-identity` (36+ artifacts collapsing to 15 distinct boosters under one recipe identity
`sha256:cfdd6cb8e950da0f`): a REAL open defect — the WF gate admits on the recipe hash and
never scores the candidate's booster. `not_acked_note` is unchanged and
`TestWhatWasDELIBERATELYNotAcked` still asserts the omission. No other member is acked by this
edit (`members == {"gate-stamp-parity", "strategy-config-parity"}` unchanged).

## The numbers delta `[VERIFIED — read-only detector run today]`

`RENQUANT_DATA_ROOT=/Users/renhao/git/github/RenQuant ops/renquant104/gate_stamp_parity.py`
emitted (copied, not typed):

```
gate-stamp parity: 46 artifact(s) scanned — 16 carry BOTH copies (0 of them SERVED by a pinned config), 30 canonical-only, 0 legacy-only, 0 no stamp, 0 malformed, 0 unreadable
```

| | scanned | both | served | canonical-only | legacy-only | no stamp | malformed | unreadable |
|---|---|---|---|---|---|---|---|---|
| acked 2026-08-05 | 36 | 16 | 0 | 20 | 0 | 0 | 0 | 0 |
| today 2026-08-29 | **46** | 16 | 0 | **30** | 0 | 0 | 0 | 0 |

Same fingerprint `e3ecdd6587cdaf4e` (digits are normalised). The 10 new artifacts are all
canonical-only: each carries ONE gate stamp and cannot disagree with itself, so the parity
situation is unchanged while the magnitude moved — had the ack not expired it would have
read `ACKED_BUT_CHANGED`, which is the designed behaviour ("an ack covers a situation, not a
magnitude"). `numbers_when_acked` is now `["46","16","0","30","0","0","0","0"]`.

## The effective 14-day bound

`acked_at 2026-08-29`, `expires_at 2026-09-12` = `acked_at + ACK_MAX_AGE_DAYS`, stated as the
effective bound in `reason` per Codex on orch#1058 (the second ack's ruling: never write an
`expires_at` the age cap silently overrides). One deviation from "clears_when unchanged",
made deliberately: the old `clears_when` ended "It also expires 2026-09-05 regardless", and
because `ack_expiry` also reads dates out of `clears_when`, leaving it would have made
2026-09-05 the binding date and the `reason`'s "expires_at IS the effective bound" false —
the exact defect being repaired. That sentence now reads 2026-09-12 with the formula written
WITHOUT any other date (a first draft wrote "acked_at 2026-08-29 + 14" inside it and
`ack_expiry` promptly bound the ack to 2026-08-29 — every ISO date in `clears_when` is an
expiry candidate, so that field must carry only the intended one); the rest of `clears_when` (served-count / legacy-only / both-copy movement re-fingerprints) is
byte-identical. `ack_expiry(...)` → `(2026-09-12, "expires_at")` `[VERIFIED — called directly]`.

## Test changes

`tests/test_ops_audit_acks_ledger.py` binds the ack to "the exact line the live detector
emits": `LIVE_TEXT` is now today's line (36→46, 20→30), the classify dates move 08-05→08-29,
the two escalation fixtures are rebased on the new counts, and the expiry test now asserts
ACKED on 2026-09-11 and EXPIRED on 2026-09-12 (the cap, not a later date).

Beside the siblings (`RENQUANT_SIBLINGS_ROOT=/Users/renhao/git/github`):
`tests/test_ops_audit_acks_ledger.py tests/test_ack_ledger_audit.py` — before this PR:
**2 failed / 65 passed / 1 skipped** once the ledger carried today's numbers (fixture still on
the 08-05 line); after: **67 passed / 1 skipped**. The skip is the end-to-end
`ops_audit.py --json` test, which cannot resolve the umbrella from a scratch worktree
(`rc=3`); its ACKED assertion is exercised directly: `classify(member, <today's line>,
ledger, 2026-08-29)` → `ACKED`, expiry `2026-09-12`. It will run for real on the deploy
machine's `make test` after merge + `-run` sync.

## Boundaries

Live umbrella read only (the detector is a read-only member). Nothing pushed, no PR opened;
the ledger edit is the reviewed diff.
