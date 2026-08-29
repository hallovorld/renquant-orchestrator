# Twin-parity manifest re-pin: umbrella `live/broker.py` + `live/alpaca_broker.py` (RenQuant#610 / #612)

Date: 2026-08-29 · Branch: `chore/twin-parity-manifest-live-broker` · Scope: one manifest
re-pin (the deliberate review act the tripwire asks for) + one ack-ledger question
SURFACED, not resolved.

## Bottom line

* `tests/test_twin_parity.py::test_live_twin_parity_manifest_current` fired on the deploy
  machine because the umbrella side of two KNOWN-diverged twins moved and the pin did not.
  The drift is real and intended: RenQuant#610 (fractional gate leg (a) — `is_fractionable`
  + no-submit classifier on the live `AlpacaBroker`, umbrella `5ebe64d`, 2026-08-28) and
  RenQuant#612 (no silent truncation — fractional intents refused or submitted exactly,
  umbrella `f9d696a`, 2026-08-29). The live tree is at `f9d696a` and its working copies of
  both files are byte-identical to `f9d696a` (sha256 checked against `git show f9d696a:…`)
  `[VERIFIED 2026-08-29 — shasum on /Users/renhao/git/github/RenQuant/live/*.py vs git show]`.
* Re-pinned by the manifest's own contract (`scripts/check_twin_parity.py --write-manifest
  --siblings-root /Users/renhao/git/github`, i.e. against the CURRENT sibling checkouts —
  `scripts/check_twin_parity.py:55,270-332`). The regenerated manifest differs from the
  committed one in EXACTLY the two umbrella shas; every other pin (execution side of all four
  broker twins, paper/readonly, model twin, constants, function pins, tax trio, meta-label
  twins) is unchanged `[VERIFIED — git diff data/twin_parity_manifest.json: 2 lines]`.

| twin | side | old sha256 | new sha256 |
|---|---|---|---|
| `broker` | umbrella `live/broker.py` | `4a9dc2092e9f7b176497c0781217432ea63cf278ccc67f655cce000a5064c943` | `7c1595fbc12f4a91507744d5eae57fe9a8c48378b8c2fc60b45fbf360cca26a2` |
| `alpaca_broker` | umbrella `live/alpaca_broker.py` | `4a165e0bcada9a14bed9d1e5a339af7c1d8168c40890b2e352dba34ad927d812` | `8be6d5298180e81662114e7b3677f5adb11c1749a890047e833635cc5ab9e7fa` |

Execution-side shas (`renquant-execution` @ `91c7bf88`) are unchanged: `broker.py`
`9d352f00…`, `alpaca_broker.py` `1ab378e2…`. The execution twin has NOT received #610/#612
— the divergence between the stacks WIDENED, which is exactly what the pin now records.
Reconciling the execution twin is a renquant-execution PR, not this one.

## Tests (beside the real siblings, `RENQUANT_SIBLINGS_ROOT=/Users/renhao/git/github`)

* before: `tests/test_twin_parity.py tests/test_ack_ledger_audit.py` → **1 failed, 81 passed**
  (the one failure = `diverged_pin:broker` + `diverged_pin:alpaca_broker`, both "umbrella side
  changed").
* after: same two files + `tests/test_ops_audit_acks_ledger.py` → **98 passed, 1 skipped**
  (the skip is `test_the_LIVE_audit_reports_it_as_INFO_not_as_a_finding`, which skips in a
  worktree because `ops_audit.py` cannot resolve the umbrella from a scratch parent dir —
  see below for what it reports in the real checkout).
* standalone: `scripts/check_twin_parity.py --siblings-root /Users/renhao/git/github` →
  **24 pass, 0 fail, 0 skip**.

## The `ACK_EXPIRED` question — SURFACED, NOT RESOLVED

`tests/test_ack_ledger_audit.py` itself passes (81/81 above). The `ACK_EXPIRED` comes from
the end-to-end test `tests/test_ops_audit_acks_ledger.py::test_the_LIVE_audit_reports_it_as_INFO_not_as_a_finding`
(line 143), which runs the real `ops/ops_audit.py --json` and asserts the `gate-stamp-parity`
row is `ACKED`. In the deploy-machine checkout it is not:

* Ledger entry `ops/ops_audit_acks.json` key `e3ecdd6587cdaf4e`, member `gate-stamp-parity`,
  `acked_at 2026-08-05`, `expires_at 2026-09-05`.
* `ack_expiry` takes the EARLIEST of `expires_at`, any date in `clears_when`, and
  `acked_at + ACK_MAX_AGE_DAYS` (`ops/renquant104/rq104_degradation_sentinel.py:527-574`,
  `ACK_MAX_AGE_DAYS = 14`). So the effective expiry was **2026-08-19**, and
  `classify(...)` returns `ACK_EXPIRED` with `expiry_why = "acked_at 2026-08-05 + 14d"` for
  every date from 2026-08-19 on `[VERIFIED — classify() run locally with dates 08-19/08-20/08-29]`.
  The written `expires_at 2026-09-05` was never the binding date — the same defect Codex
  ruled on for the second ack (orch#1058: `expires_at` must EQUAL `acked_at + 14`, stated in
  `reason`; `doc/progress/2026-08-24-watchlist-parity-audit-member-1020.md:54-68`).
* What the ack covers: the gate-stamp parity CENSUS only — 16 `panel-ltr.alpha158_fund*`
  artifacts carrying both a canonical and a legacy WF-gate stamp, NONE served by a pinned
  config, the one verdict-disagreeing artifact
  (`panel-ltr.alpha158_fund.weekly_rollback_2026-07-06.json`) explained by the recorded
  2026-07-05 operator override. It explicitly does NOT ack `booster-identity`.
* **It is not a date bump.** The live detector line today is
  `gate-stamp parity: 46 artifact(s) scanned — 16 carry BOTH copies (0 of them SERVED by a
  pinned config), 30 canonical-only, 0 legacy-only, 0 no stamp, 0 malformed, 0 unreadable`
  `[VERIFIED — RENQUANT_DATA_ROOT=/Users/renhao/git/github/RenQuant ops/renquant104/gate_stamp_parity.py, 2026-08-29]`.
  Same fingerprint `e3ecdd6587cdaf4e`, but `numbers` `46/16/0/30/0/0/0/0` vs the acked
  `36/16/0/20/0/0/0/0`: ten new canonical-only artifacts since 08-05. Had the ack not expired
  it would report `ACKED_BUT_CHANGED` (verified with `classify(..., 2026-08-18)`). The
  situation the ack describes (16 both-copy, 0 served, 0 legacy-only) is unchanged; the
  magnitude moved.
* No in-repo renewal procedure exists (grepped `renew|re-ack|extend` across `ops/` and
  `doc/memory`; nothing). Renewal = a reviewed edit of the ledger, so it is NOT done here.

### Proposed renewal text (for the reviewed ledger edit, same key `e3ecdd6587cdaf4e`)

```
"acked_at": "<date of the reviewed edit>",
"expires_at": "<acked_at + 14 days — equals acked_at + ACK_MAX_AGE_DAYS; the effective bound>",
"acked_by": "claude",
"numbers_when_acked": ["46", "16", "0", "30", "0", "0", "0", "0"],
"reason": "Renewal of the 2026-08-05 ack, which expired 2026-08-19 under the
  ACK_MAX_AGE_DAYS=14 cap (its written expires_at 2026-09-05 was never binding). Re-verified
  <date>: the same 16 both-copy artifacts are historical and NONE IS SERVED, measured BY THE
  DETECTOR ('0 of them SERVED by a pinned config'); the census grew 36->46 scanned / 20->30
  canonical-only — the 10 new artifacts are canonical-only, i.e. they carry ONE stamp and
  cannot disagree with themselves. The one artifact whose two stamps disagree on the VERDICT,
  panel-ltr.alpha158_fund.weekly_rollback_2026-07-06.json, is still explained by the legacy
  copy's operator_authorized_override=true with the recorded 2026-07-05 reason. expires_at
  IS acked_at + ACK_MAX_AGE_DAYS, stated here per codex on orch#1058.",
"clears_when": "<unchanged from the 2026-08-05 entry>",
"not_acked_note": "<unchanged: booster-identity is NOT acked>"
```

Before that edit lands, the reviewer should re-run the detector on the day of the edit and
copy the numbers from ITS line, not from this document.

## Boundaries honoured

Isolated worktree; the live umbrella tree and the `-run` checkout were only READ (shasum,
`git show`, `git log`, the read-only detector). Nothing pushed, no PR opened.
