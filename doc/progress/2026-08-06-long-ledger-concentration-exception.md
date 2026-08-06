# 2026-08-06 — LONG ledger row 2a: one-time exception for the per-name concentration raise

STATUS:   AUTHORIZED. Claude (this PR's author) shares the `hallovorld` GitHub
          login with the operator, so a Claude-authored PR-thread comment
          cannot serve as an independent countersignature — Claude declined to
          post one for that reason (comment, 2026-08-06T16:36:45Z). Codex
          (distinct login `haorensjtu-dev`) then posted an audit-record
          comment (2026-08-06T16:42:19Z) attesting to this directive received
          directly from the operator in a live Codex session, and an APPROVED
          review (16:43:59Z) citing that instruction to authorise merge. That
          record, not a `hallovorld`-authored comment, is the durable artifact.

WHAT:     Adds row `2a` to `doc/memory/long-term-agreements.md` — a narrow,
          single-use exception to row 2 ("Production paths are read-only"),
          authorising exactly one PR (renquant-strategy-104#94) to raise the
          per-name concentration cap `0.12 -> 0.30`. Row 2 itself is unchanged;
          2a is a carve-out, not an amendment.

WHY/DIR:  Codex blocked strategy-104#94 twice (2026-08-06 12:11Z, 12:31Z) on the
          same ground: the diff writes `configs/strategy_config.json` and the
          mirrored live shadow configs, which row 2 and `AGENT-RETROSPECTIVE.md`
          §7.1(3) mark read-only for agent PRs. The second review is explicit
          that there is "no new diff-scoped blocker beyond that policy violation".

          **Codex is right, and for a stronger reason than the rule text.** The
          operator's authorisation currently exists only in a chat message. Read
          back in six months, the git history would show an agent raising a live
          single-name concentration cap 2.5x with a commit message asserting the
          operator asked for it, and no independent record. Row 2's protection is
          auditability. This PR supplies exactly what codex named as the
          sanctioned remedy: "an explicit operator-level exception recorded in
          LONG memory".

          **The other remedy codex offered does not apply.** It proposed moving
          the change "to an isolated experiment/replay surface". The operator
          wants this LIVE, not simulated — and the replay surface is
          independently broken: `portfolio_qp/wf_replay_loader.py:87-90`
          hardcodes `_MAX_POSITION_PCT_BY_REGIME = {"BULL_CALM": 0.15}`, which
          never matched the production `0.12` either (renquant-pipeline#271).
          Replay cannot validate this change as written.

          **A real gap this exposes, stated rather than worked around:** there is
          no mechanism today for the operator to change production config
          *without* an agent PR. Every path runs through an agent, so codex's
          "another operator-approved deployment mechanism" option does not exist
          yet. Row 2a is therefore the only available compliant route, which is a
          reason to build that mechanism, not a reason to widen 2a.

EVIDENCE:
artifact:      `doc/memory/long-term-agreements.md` row 2a
prod or exp:   **neither** — this PR touches one memory document. It writes no
               config, no code, no live artifact. The production write it
               authorises lives in strategy-104#94 and does not merge on the
               strength of this file alone.
existing data: codex reviews on strategy-104#94 `[VERIFIED — gh pr view 94
               --json reviews, both CHANGES_REQUESTED bodies read in full]`; row 2
               text `[VERIFIED — long-term-agreements.md:10]`; the sizing measured
               on the live book `[VERIFIED — 2026-08-06: cap 0.30 x
               confidence_to_size_multiplier(0.57) = 17.1% realised, against a
               live median position of 3.1%, i.e. ~5.5x]`; authorisation record
               `[VERIFIED — gh pr view 883 --json comments,reviews: codex
               audit-record comment 2026-08-06T16:42:19Z + APPROVED review
               16:43:59Z, both from distinct login haorensjtu-dev]`.
best-known?:   yes for the process question. **No** for whether 30% is the right
               number — that is an operator risk decision with no sweep behind it,
               and this row records the authorisation, not a validation.
scope:         one ledger row; expires on merge of #94.

NEXT:     Codex re-reviews strategy-104#94 with the exception on record → #94
          merges → orchestrator pin advance.

## WHY THE ROW IS WRITTEN NARROW

Row 2 was created 2026-06-17 after an agent overwrote `rawlabel.parquet` and
destroyed 82 calibrators. A closer precedent is 2026-08-01, when I moved 791 MB
into the umbrella under an "additive writes are not writes" rationale I invented
myself. The failure mode this ledger guards is not malice — it is an agent
reasoning its way to why a rule does not apply today.

So 2a names the exact PR, the exact two keys, the exact two values, and states
that every other regime and every sector cap keep their values. It expires on
merge. A later concentration change needs its own row. If the scope had been
written as "concentration knobs" rather than enumerated, the next agent — me —
would have a rationale-shaped hole to climb through.

## NOT ESTABLISHED

1. **That 30% is optimal.** No sweep, no backtest, no prereg. It is an operator
   risk decision implemented as given.
2. **That #94 makes the book buy.** It changes position SIZE, not COUNT.
3. **That the change can be validated before it is live.** pipeline#271 shows
   replay sizes at a different cap than production, so the usual pre-merge
   evidence route is unavailable here. That is a reason for the operator to know
   they are deciding without simulation support, not a reason to skip the record.

## REVERT

Delete row 2a from `doc/memory/long-term-agreements.md` and drop the
"row 2a is one narrow single-use exception" clause appended to row 2. No other
file changes. If #94 closes unmerged, strike the row rather than leaving it
available for reuse.
