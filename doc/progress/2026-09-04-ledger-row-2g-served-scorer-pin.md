# LONG-ledger row 2g — one-time authority for the served-scorer content-pin move (A4-T1 promotion)   (PR #1115)

STATUS: ledger-only PR, row-2a..2f precedent: the authority row lands on
orchestrator `main` BEFORE the config PR merges. **AUTHORIZATION PENDING** —
this PR does not merge until the operator's first-hand, change-specific
confirmation is quoted verbatim in the row's slot.

## The decision this row records (once confirmed)

Exactly one renquant-strategy-104 PR (#107, branch
`fix/served-scorer-pin-a4t1-20260831`, commit f5a428fe at preparation) moves
`ranking.panel_scoring.components[0].expected_content_sha256` from
`sha256:6461b827ab2339a8` (the 2026-08-02 model) to `sha256:f1b1c1322e3b66f7`
(the A4-T1 promoted artifact, candidate 20260831T141820Z, trained 2026-08-31,
promoted 2026-09-03 09:09 PDT) in the seven carriers that hold the key, plus a
named `_expected_content_sha256_reason` in each. No other key, file or PR; the
08-04 audit manifest untouched; no artifact written or promoted.

## Why a row is required

Row 2 makes `strategy_config.json` read-only with no exception. This is a
production-config write, so it needs its own single-use, PR-named row with
first-hand operator authority. The A4-T1 authorization (2026-08-31 session;
「go」 2026-09-02) and the 2026-09-03 blanket 「授权，加速」 name no key and are
recorded as the reason the package was prepared, NOT as authority.

## Evidence (file:line citations are in the row itself)

- 2026-09-04 06:06 dawn funnel preflight: `LoadScorerTask … blend component[0]
  content_sha256 MISMATCH … pinned='sha256:6461b827ab2339a8'
  observed=sha256:f1b1c1322e3b66f7…` → `panel_scorer_load_failed`, 6 buy
  candidates cleared, buy path fail-closed [VERIFIED —
  `RenQuant/logs/rq104/dawn_funnel_preflight_2026-09-04.log:227-228`].
- Served artifact: trained 2026-08-31, `promotion_basis=freshness_fallback_rfc210`,
  A4-T1 run 20260831T141820Z, receipt 2cd9d27b…, sha256 prefix f1b1c1322e3b66f7;
  `.previous.json` = 6461b827ab2339a8, trained 2026-08-02 [VERIFIED — read-only].
- Pin history: strategy-104 `git log -S expected_content_sha256 --
  configs/strategy_config.json` → 0bd93d6 (2026-08-04) and 40640d1 (2026-07-26);
  no move since [VERIFIED].
- strategy-104#107 suite: 104 passed, 1 skipped, 1 pre-existing failure
  (`test_config_drift_cli_exposes_repo_root`, identical on the unmodified
  pinned checkout) [VERIFIED].

## What confirms this row

Operator states, first-hand, in any operator channel, that exactly this pin
move is approved — e.g. reply 「确认」 to the agent prompt 「确认 row 2g:
components[0].expected_content_sha256 6461b827ab2339a8 → f1b1c1322e3b66f7
(A4-T1 晋升工件 20260831T141820Z)」 (the 2e/2f pattern: a one-word reply is
change-specific through the prompt it answers). The verbatim text, date and
channel go into the row's slot; the same confirmation is posted with
timestamp on this PR and on renquant-strategy-104#107. Until then both PRs
stay open and unmerged.

## Memory tier touched

LONG (`doc/memory/long-term-agreements.md`, row 2g appended after 2f; no
existing row's meaning edited).
