# Progress: blend readout horizon 20d -> 60d (operator decision)

STATUS:   delivered (code + amendment + 10/10 tests). Amends a frozen rule, on
          operator authority (see `best-known?` below for the governance-trail
          caveat). Round-2 (this revision): closes a real BLOCKER — the
          `MATURITY_TDAYS` gate was declared but not enforced — and fills in
          the required §4(b) evidence-block fields (codex-caught, PR #598).

WHAT:     `mature_fill` now backfills from `fwd_60d`, and `MATURITY_TDAYS`
          moves 21 -> 61 with it. Adds
          `doc/research/2026-07-29-blend-readout-horizon-amendment.md`
          recording the change against the frozen pipeline#213 rule. THIS
          REVISION additionally adds `_aged_dates()` and wires it into
          `mature_fill` so `MATURITY_TDAYS` is an enforced trading-session
          maturity gate, not just a documented constant — a row now only
          realizes once >= `MATURITY_TDAYS` LATER sessions exist in
          `ticker_forward_returns`, in addition to (not instead of) the
          existing all-picks-resolvable check.

WHY/DIR:  The 120-session forward ledger is the one piece of evidence here
          that cannot be re-derived later, and it was backfilling a 20-day
          spread while the certified effect (+0.0687, CI lower +0.0156) and
          both scored models are fwd_60d recipes. The Feb-2027 GATE read would
          have answered a question the certification never asked.

          Round-2 root cause: the original `mature_fill` realized a row as
          soon as every pick had a non-null `fwd_60d`, with no separate age
          check — so `MATURITY_TDAYS` was dead. Codex's BLOCKER cited a real
          risk documented elsewhere in this same repo:
          `scripts/research_panel_exit_predictiveness.py`'s "TRADING-SESSION
          AGING" note states a row's `fwd_60d` "can carry a non-NULL value
          that was written before its full horizon elapsed" on this exact
          `ticker_forward_returns` table — so `fwd_60d IS NOT NULL` alone does
          not prove a date is aged. The fix mirrors that script's own
          session-calendar aging technique (`_session_calendar`/
          `_aged_cutoff`) rather than inventing a new one (§7.10).

EVIDENCE:
artifact:      `ops/renquant104/rq104_blend_readout.py` (`mature_fill`,
               new `_aged_dates`, `MATURITY_TDAYS`);
               `tests/test_rq104_blend_readout.py` (10 tests, incl. new
               `test_premature_fwd_60d_write_does_not_realize_before_maturity_tdays`
               and the seeded-calendar updates to
               `test_mature_fill_only_when_all_returns_present` and
               `test_backfill_reads_the_60d_column`);
               `doc/research/2026-07-29-blend-readout-horizon-amendment.md`;
               `ops/renquant104/com.renquant.rq104-blend-readout.plist`
               (the scheduled invocation, unchanged this PR).
prod or exp:   prod — `com.renquant.rq104-blend-readout.plist` runs this
               script daily at 15:21 via launchd `[VERIFIED — plist read,
               this session]`. It is READ-ONLY against the live decision
               surfaces (`candidate_scores`, `pipeline_runs`,
               `ticker_forward_returns` in `data/runs.alpaca.db`) and writes
               only its own append-only ledger
               (`data/rq104_blend_readout/ledger.jsonl`) — it does not feed
               order placement, sizing, or the pinned scorer artifacts. It is
               evidentiary/reporting infrastructure for the Feb-2027 GATE
               read, not a live-trading decision path.
existing data: the ledger currently holds exactly 2 sessions, both still
               `"realized": false` under any horizon
               `[VERIFIED — direct read of
               /Users/renhao/git/github/RenQuant/data/rq104_blend_readout/ledger.jsonl,
               this session: run_date 2026-07-27 and 2026-07-28, both
               realized=false]`. The 20d ledger therefore never produced a
               realized row before this switch — nothing computed under the
               old horizon is discarded, which is a property of timing
               (caught before any row matured), not of the fix. Re-verified
               `fwd_60d` availability this session (independent of the
               original author's claim):
               `SELECT COUNT(*) FROM ticker_forward_returns WHERE fwd_60d IS
               NOT NULL` -> 17084, `MAX(as_of_date)` -> 2026-04-30, matching
               the amendment doc's figures exactly
               `[VERIFIED — direct sqlite3 read-only query against
               data/runs.alpaca.db, this session]`. Also newly checked for
               this revision: `SELECT COUNT(DISTINCT as_of_date) FROM
               ticker_forward_returns` -> 632 distinct sessions
               `[VERIFIED — same query]`, i.e. comfortably more than
               `MATURITY_TDAYS` (61), so the new aging gate is exercisable in
               production rather than permanently empty. GOAL-6 Stage 0
               separately measured that the shorter horizon buys no power
               (H2 NOT SUPPORTED: ~3x the blocks, proportionately smaller
               effect) — carried over from the original doc, not
               re-measured this session.
best-known?:   the horizon value (60d over 20d) is the best-known choice
               given the stated reasons (measures the same quantity as the
               certified effect; H2 showed no power advantage to 20d) — this
               is a technical, checkable claim and IS verified above.
               Separately: the PR title/amendment doc assert this was an
               "operator decision" ("改成 60d，重算已有场次"). **That specific
               authorization claim is n/a — not independently checkable from
               this repo.** Searched `doc/memory/long-term-agreements.md`
               (LONG tier, binding decisions) and every `doc/memory/mid-term/`
               workstream file that mentions "60d" / "blend ledger" /
               `MATURITY_TDAYS` (`model-edge.md`, `decision-ledger.md`,
               `win-rate-payoff.md`) — none records this specific horizon
               decision `[VERIFIED — grep, this session, zero matches]`. The
               only source for the quoted instruction is this PR's own
               commit message and the amendment doc, both agent-authored, not
               an external issue/comment/decision-record. This gap is
               reported, not resolved — creating a new self-referential
               record would not make the claim independently checkable, and
               this fix-agent has no channel to the original conversation to
               verify it against.
scope:         claim is scoped to (a) the horizon math being internally
               consistent and data-available, which is verified above, and
               (b) the aging-gate code fix now doing what the docstring
               claims. It does NOT extend to independently confirming the
               operator actually issued the quoted instruction — see
               `best-known?` above. No IC/Sharpe/APY number is claimed here,
               so the §7.2 sanity triad does not apply; this is a
               data-plumbing correctness fix, not a model-performance claim.

NEXT:     Realized rows now arrive ~40 trading days later than under the old
          20d horizon (unchanged from round 1); the INFO read slips
          accordingly. Newly, because realization also now waits for the
          `MATURITY_TDAYS` session-count gate (not just non-null `fwd_60d`),
          the earliest a session can realize is bounded by the trading
          calendar, not just by when `ticker_forward_returns` happens to be
          backfilled. If the operator-authorization gap above needs to be
          closed for governance purposes, that requires a human-sourced
          record (issue/comment/chat log) — outside what a fix-agent can
          manufacture.
