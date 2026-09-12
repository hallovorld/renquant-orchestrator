# LONG-ledger row 2h — one-time authority for a SECOND dated A4-T1 window   (PR #1118)

STATUS: ledger-only PR, row-2a..2g precedent: the authority row lands on
orchestrator `main` BEFORE the licensed change merges. **AUTHORIZATION
PENDING** — this PR does not merge until the operator's first-hand
confirmation, naming the artifact AND the end date, is quoted verbatim in the
row's slot.

## The decision this row records (once confirmed)

Exactly one renquant-pipeline PR (#310, branch `feat/a4t1-window-extension`,
commit 28b59e10 at preparation) adds ONE registry entry extending the A4-T1
window of the SAME served artifact — run `20260831T141820Z`, digest
`760912ec…4af1e` — from the stamped 2026-09-07 to a confirmed end date
(prepared date 2026-09-28 — the artifact's age-bar ceiling). No artifact is rewritten, no gate is relaxed,
no other artifact is covered.

## Why a row is required

Row 2 makes the served surface read-only with no exception, and the first
A4-T1 grant set the precedent that a licensed serving exception is an
operator decision quoted verbatim. This is a second, longer window on a
candidate the standing policy refuses, so it needs its own single-use,
PR-named row. The operator's 09-04 「尽快修好104！asap！」 and 09-08
「104 105都坏了！马上修好！」 are urgency and are recorded as the reason the
package was prepared, NOT as authority.

## Evidence (citations are in the row itself)

- 2026-09-08 daily: `✗ P-REGIME-IC: no regime has enough OOS trades` →
  `PRE-FLIGHT FAILED` → sell-only, `no trade (no_candidates)`, held=3,
  eq $10,989 [VERIFIED — `logs/daily_104/2026-09-08.log:394-400` + ntfy].
- 105 and the shadow lanes are dark downstream of the same abort
  (FLEET-LANE-ALARM zero candidates, `rq105 shadow serving SKIPPED`, three
  lanes `shadow score feed DARK`) [VERIFIED — ntfy 13:45–14:51].
- No servable alternative: served 0 eligible regimes; previous 1 eligible
  regime but 37d old vs the 28d SLA; candidates 09-03/05/06 all 0 eligible
  regimes, genuine_ic 0.00024–0.00087 vs the 0.02 floor [VERIFIED —
  read-only WF metadata].
- pipeline#310: 55 tests green; read-only evaluation of the LIVE artifact —
  `REFUSED` today without the entry, `SERVED … until 2026-09-28` with it,
  stamped expiry unchanged [VERIFIED].

## What confirms this row

The operator states, first-hand, the artifact and the end date — e.g. reply
to the agent prompt 「确认 row 2h:把 A4-T1 窗口从 2026-09-07 延到 <日期>，
仍是同一工件 20260831T141820Z / 760912ec…4af1e」. Any end date may be named, but
**2026-09-28 is a hard ceiling, not a preference**: a window only decides
whether the regime-evidence exception applies, and the artifact must ALSO
hold the ordinary RFC#210 license, whose age bar is 28 days. Trained
2026-08-31, it is unservable from 2026-09-29 whatever the window says
[VERIFIED 2026-09-09 — read-only against the LIVE artifact with the registry
at 2026-10-16: SERVED=True through 09-28, SERVED=False from 09-29 on
"governance-served artifact aged out"; the last 18 days were inert].
**Scheduling consequence: this row helps only if it MERGES AND DEPLOYS by
2026-09-28, and codex is reported unavailable until 2026-10-03 — five days
too late. On the current quota timeline this row cannot restore the buy path
at all; restoring codex capacity before ~2026-09-26 is what makes it useful.** The verbatim text, date and channel go into
the row's slot and are posted with timestamp on this PR and on
renquant-pipeline#310. Until then both PRs stay open and unmerged.

## Memory tier touched

LONG (`doc/memory/long-term-agreements.md`, row 2h appended after 2f; no
existing row's meaning edited). Note row 2g (served-scorer pin, orch#1115) is
also pending and inserts at the same place — whichever lands first, the other
rebases.
