# LONG-ledger row 2h — one-time authority for a SECOND dated A4-T1 window   (PR #1118)

STATUS:    ledger-only PR, row-2a..2g precedent: the authority row lands on
           orchestrator `main` BEFORE the licensed change merges.
           AUTHORIZATION RECEIVED 2026-09-12 — the operator's first-hand
           confirmation (Claude operator session 428feb92, chat, in direct
           reply to the message listing the 确认 prompts with keys and values;
           verbatim 「现在就落地！不要等任何时间！马上就做好一切！我今天就要修好的104重新跑一遍！」
           / 「不要卡住"能做的都做完了" 把所有都做好！不要被任何事情卡住！」,
           recorded as an explicit override of the reply format) is quoted in
           the row's slot [VERIFIED — row text on this branch, commit a61fcf6d],
           and the window extension LANDED the same day on the live tree under
           the CLAUDE.md §5 CONTAINMENT PROTOCOL as a live `subrepos.lock.json`
           pin edit (renquant-pipeline → pipeline#310's head), NOT a merge —
           record: `doc/progress/2026-09-12-containment-landing-rows-2g-2h.md`,
           carried by this PR as the containment's §5(b) durable record (that
           is why this PR holds two progress docs). This PR and pipeline#310
           still do NOT MERGE until the codex gate returns; merging lifts the
           containment. Hard ceiling unchanged: the artifact is unservable from
           2026-09-29 whatever the window says.
WHAT:      Appends LONG row 2h to `doc/memory/long-term-agreements.md` (after
           2f/2g; no existing row's meaning edited) plus this record and the
           containment landing record. The row is a ONE-TIME exception
           licensing exactly one renquant-pipeline PR (#310, branch
           `feat/a4t1-window-extension`, commit 28b59e10 at preparation) to
           add ONE registry entry extending the A4-T1 window of the SAME
           served artifact — run `20260831T141820Z`, digest `760912ec…4af1e` —
           from the stamped 2026-09-07 to 2026-09-28 (the artifact's age-bar
           ceiling). No artifact is rewritten, no gate is relaxed, no other
           artifact is covered. Details in the sections below.
WHY/DIR:   Row 2 makes the served surface read-only with no exception, and the
           first A4-T1 grant set the precedent that a licensed serving
           exception is an operator decision quoted verbatim. This is a
           second, longer window on a candidate the standing policy refuses,
           so it needs its own single-use, PR-named row. The operator's 09-04
           「尽快修好104！asap！」 and 09-08 「104 105都坏了！马上修好！」 are
           urgency and are recorded as the reason the package was prepared,
           NOT as authority. Direction: G-C (a SERVED outcome) — the buy path
           has been structurally closed since the first window expired
           2026-09-07 and no other artifact is servable.
EVIDENCE:  artifact:      served `artifacts/prod/panel-ltr.alpha158_fund.json` — A4-T1 run 20260831T141820Z, digest `760912ec122fa6e02628077df8b35e58145209ea3b6b395bd670d8ead9e4af1e`, trained 2026-08-31; the abort at `RenQuant/logs/daily_104/2026-09-08.log:394-400`; the licensed change is pipeline#310's registry entry (code, consulted only past the stamped expiry, bound to run id + digest + end date)
           prod or exp:   prod — a serving-window license for the LIVE served artifact; no artifact bytes rewritten (the stamped `fallback_a4t1_expiry` stays covered by the orchestrator's consumption receipt 2cd9d27b…), no gate relaxed
           existing data: the four dated bullets under "Evidence" below (2026-09-08 `P-REGIME-IC` HARD → `PRE-FLIGHT FAILED` → sell-only, held=3, eq $10,989; 105 and the shadow lanes dark downstream; no servable alternative — served 0 eligible regimes, previous 37d old vs the 28d SLA, candidates 09-03/05/06 genuine_ic 0.00024–0.00087 vs the 0.02 floor; pipeline#310 55 tests green and the read-only LIVE-artifact evaluation `REFUSED` without the entry / `SERVED … until 2026-09-28` with it). After the 09-12 containment landing the readonly probe on the live runtime reached `ECONOMIC_TRADE … candidates_final=70 buys=4` with no orders [VERIFIED — `RenQuant/logs/rq104/containment_probe_20260912T180627Z.log` re-read 2026-09-13: that decision line is present].
           best-known?:   n/a — no model claim; the served artifact has 0 eligible regimes and genuine_ic 0.00155, and every candidate is two orders of magnitude under the A4 floor. This row changes WHETHER the served model may buy, not whether it has edge (`live-policy-is-not-the-validated-policy`).
           scope:         "one LONG row licensing one registry entry for one artifact to one end date (2026-09-28) in one pipeline PR; no other artifact, gate, file or PR"
NEXT:      codex gate returns → review + merge this row → merge pipeline#310
           → umbrella pin advance (`subrepos.lock.json` renquant-pipeline →
           that merge) + snapshot re-render → live `git pull --ff-only` +
           `subrepo_assemble --sync`; at that sync the live lock equals main's
           and the §5 containment is lifted by construction. Scheduling: this
           only matters if it merges and deploys by 2026-09-28. Rollback =
           revert #310 + pin re-advance; the containment's literal revert is
           in the landing record.

## The decision this row records (confirmed 2026-09-12)

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

## What confirms this row (satisfied 2026-09-12 — see STATUS and the row's slot)

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
