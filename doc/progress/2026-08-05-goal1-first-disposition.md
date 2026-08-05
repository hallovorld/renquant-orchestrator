# 2026-08-05 — GOAL-1: the ack ledger gets its first entry, and it is a small one

## What orch#823 left behind

`com.renquant.ops-audit` fires **9 of 11** detectors every run, and
`ops_audit_acks.json` **did not exist** — the disposition mechanism was built,
merged, and never used. That record deliberately stopped short of saying the
findings should be acked. This is the follow-through, and it starts by asking
whether they are real.

## First I checked whether the detectors could even pass. They can

My hypothesis was that several detectors report a census and exit 1
unconditionally — noise by construction. **Refuted.** `gate-stamp-parity` and
`booster-identity` both name real conditions:

- `gate-stamp-parity`: `panel-ltr.alpha158_fund.weekly_rollback_2026-07-06.json`
  carries two stamps that disagree on **57 paths, including `passed` itself** —
  canonical `False`, legacy `True`.
- `booster-identity`: **36 artifacts → 15 distinct boosters** under one identity
  `sha256:cfdd6cb8e950da0f`.

*(A first pass of mine read both as exiting 0. That measured `tail`'s exit code
through a pipe, not the detector's — the same wrong-object mistake this repo
keeps meeting. Re-measured without the pipe.)*

## Then whether the parity finding is reachable. It is not `[VERIFIED — this session]`

- **All 11** pinned `strategy_config*.json` under
  `.subrepo_runtime/repos/renquant-strategy-104/configs` point
  `ranking.panel_scoring` / `panel_ltr` at
  `artifacts/prod/panel-ltr.alpha158_fund.json`. **None names a both-copy file.**
- The one artifact whose stamps disagree on the verdict is **explained, not
  unexplained**: the legacy copy carries `operator_authorized_override=true`
  with the recorded 2026-07-05 reason, so it holds the **post**-override verdict
  while the canonical copy holds the **pre**-override one.

Historical, unserved, and explained — that is what an ack is for.

## The first ack

```
findings=9 info=0   →   findings=8 info=1
```

The acked finding is **still printed**, with its reason. Nothing is suppressed
silently, and `ops_audit.py` never writes the ledger — acking is a reviewed diff.

It covers a **situation, not a magnitude**: any legacy-only stamp appearing, or
the both-copy count moving, changes the recorded numbers and the finding returns
as `ACKED_BUT_CHANGED` rather than INFO. It also **expires 2026-09-05**
regardless, because "no config points at it" is a fact about *today's* configs.
Both are asserted by tests, not merely intended.

## What was DELIBERATELY not acked

**`booster-identity` stays loud.** 36 artifacts collapsing to 15 distinct
boosters under one identity is a real open defect — the WF gate admits on the
recipe hash and never scores the candidate's booster. Acking it would be exactly
the failure this ledger exists to avoid, and **a test asserts the omission**
rather than trusting that I meant it.

Eight findings remain loud. One ledger entry is not a cleanup; the value of an
ack ledger is destroyed by a single dishonest entry, so the first one is the one
I could fully evidence.

Suites: 12 tests — the ledger's shape, the fingerprint bound to what the live
detector actually emits, three escalations that break the ack, its expiry, the
deliberate omission, and an end-to-end check that the report really changed ·
full suite green.
