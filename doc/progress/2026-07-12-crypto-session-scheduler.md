# 2026-07-12 — Crypto session scheduler (D-C11)

## Bottom line

24/7 crypto session scheduler module implementing crypto RFC §3.5. Sessions
span one UTC calendar day. Entry gating via triple gate (config + env +
kill-switch), quiet interval (first 15 min, configurable), watermark +
externally-verified signal-snapshot-digest checks, an unbypassable
`crypto_trading.mode in {"live", "paper"}` gate, and an unbypassable
execution-side stop-coverage precondition. Exits always allowed. See
"Revision note" and "Reconciliation note (round 2)" below
for the post-CHANGES_REQUESTED fixes — the initial version below described
the pre-revision state (watermark/digest were computed but not enforced;
mode/stop-coverage were not gated at all).

## What this PR contains

- `src/renquant_orchestrator/crypto_session.py` — session scheduler core:
  `SessionWindow` (UTC day boundaries), `SignalSnapshot` (immutable digest),
  `CryptoSessionConfig` (from-dict), `evaluate_tick` (triple gate + quiet +
  snapshot verification), `build_session_bundle` (run-bundle factory),
  `watermark_for_session` (bar-close watermark).
- `tests/test_crypto_session.py` — 26 tests: session windows (incl. weekend),
  signal digest determinism, triple gate (3 failure modes + pass), tick
  evaluation (6 scenarios), serialization, bundle, watermark, config, session
  date boundary.

## Key design choices

1. Exits ALWAYS allowed (even kill-switched) per §5.4 precedence
2. Fail-closed: no signal snapshot → no entries (not degraded/stale)
3. Signal snapshot date must match current session (stale snapshot rejected)
4. Triple gate re-checked every tick (config + env + file)
5. 15-min quiet interval at UTC midnight for signal computation

## Verification

- 26/26 tests pass `[VERIFIED]`
- No existing tests regressed (7 pre-existing failures unchanged) `[VERIFIED]`
- Module has no external dependencies beyond stdlib `[VERIFIED]`

## Revision note (2026-07-12, post CHANGES_REQUESTED)

Codex (GitHub `haorensjtu-dev`) left a CHANGES_REQUESTED review on this PR
(#497, 2026-07-12T21:33:31Z) — verbatim:

> Blocking review.
>
> The module is in the correct repository as orchestration/session policy,
> but it does not implement the leakage-proof contract claimed by the PR.
>
> 1. `evaluate_tick` never validates `signal_snapshot.bar_watermark_utc`
>    against `watermark_for_session(session_date)`. A snapshot whose bars
>    include the current UTC session or future data passes whenever its
>    `session_date` matches. The watermark is only a field and a helper
>    function, not an enforced gate.
> 2. The digest is computed and echoed, never verified against an expected
>    immutable digest from the run bundle/artifact ledger. Self-hashing
>    untrusted input is provenance decoration, not verification. Require an
>    expected digest/fingerprint supplied by the approved artifact path,
>    compare it in `evaluate_tick`, and fail closed on mismatch or missing
>    expected value.
> 3. `crypto_trading.mode` is not part of the entry gate. A config marked
>    shadow can return `entries_allowed=True`, while no explicit
>    live-authorization state is checked. Entries must be impossible unless
>    the configured mode and an independently authorized runtime state
>    permit them; DARK/shadow should produce decision records only.
> 4. `quiet_interval_minutes` is configurable but `SessionWindow` always
>    uses the module constant. Either remove the setting or pass and
>    validate the configured value. Also validate tick cadence and resolve
>    the default kill-switch path from the audited run root, not process
>    CWD.
> 5. Before any entry decision, wire the execution-side
>    stop-coverage/liveness precondition through a public contract. A
>    scheduler that can admit an entry without proving protective-order
>    readiness is not fail-closed.
>
> Please rebase on merged model #48 and revise the implementation/tests.
> Add explicit tests for a future watermark, digest mismatch, shadow-mode
> non-admission, configured quiet interval, and unavailable protective
> coverage.

The "rebase on merged model #48" sentence was investigated and found to be
an erroneous cross-reference: `model#48` is an unrelated, already-merged
docs PR in a different repo about ensemble-promotion confirmation, with no
connection to this crypto session scheduler. Not acted on. This branch was
still rebased onto this repo's own `origin/main` as normal hygiene (it was
1 commit behind, a docs-only architecture-audit commit — no conflicts).

All 5 findings were confirmed correct against the actual code and fixed in
`src/renquant_orchestrator/crypto_session.py`:

1. **Watermark enforcement** — `evaluate_tick` now computes
   `expected_watermark = watermark_for_session(session_d)` and compares it
   against `signal_snapshot.bar_watermark_utc` EXACTLY (after the existing
   session-date-mismatch check). A mismatch fails closed
   (`entries_allowed=False`) naming both the expected and actual watermark
   values in `reason`, while still populating `signal_snapshot_digest` on
   the record.
2. **Externally-supplied expected digest** — `evaluate_tick` gained
   `expected_signal_snapshot_digest: str | None = None`. `None` (never
   supplied) and a mismatch both fail closed, with distinct reason text
   ("no expected signal-snapshot digest supplied by the caller" vs.
   "signal snapshot digest mismatch: expected X, got Y" — the latter names
   both digests). The caller is responsible for sourcing the expected
   digest independently (run bundle / artifact ledger); `crypto_session.py`
   never derives it from `signal_snapshot` itself.
3. **`crypto_trading.mode` entry gate** — a new `_apply_final_entry_gates`
   helper forces `entries_allowed = entries_allowed and (config.mode ==
   "live")` as the FINAL step of `evaluate_tick`, after the full tick
   evaluation (triple gate, quiet interval, snapshot checks) runs exactly
   as before. Shadow/DARK mode still produces a complete, richly-populated
   `TickResult` (digest, watermark outcome, quiet flag, ...) — a decision
   RECORD — just with `entries_allowed` forced to `False` and a `"; mode=
   shadow, not authorized for live entries"` suffix appended to `reason`
   (only when mode was the actual reason a would-be-True result flipped).
   Added `TickResult.mode: str` (also emitted in `to_jsonable()`) so every
   record shows what mode produced it.
4. **Quiet interval + tick-cadence validation + kill-switch root** —
   `SessionWindow.for_date` now takes `quiet_interval_minutes` (default =
   the module constant for old call sites); `evaluate_tick` passes
   `config.quiet_interval_minutes` through. `CryptoSessionConfig.__post_init__`
   now validates `0 <= quiet_interval_minutes < 1440` and `0 <
   tick_cadence_seconds <= 3600`, raising `ValueError` (matching this
   repo's existing config-validation convention, e.g.
   `decision_outcome_validator.py`, `live_rehearsal_plan.py`) — this runs
   for BOTH direct construction and `from_dict`. The default kill-switch
   path is now resolved via a new `default_crypto_kill_switch_path()`,
   which joins `CRYPTO_KILL_SWITCH_RELPATH` onto
   `renquant_orchestrator.runtime_paths.default_data_root()` instead of a
   bare `Path(...)` resolved against process CWD — the same convention
   `intraday_session_scheduler.default_kill_switch_path` already uses for
   the analogous rq105 kill switch (found via `RENQUANT_DATA_ROOT` /
   `default_repo_root()` prior art; no new convention invented).
5. **Execution-side stop-coverage precondition** — `evaluate_tick` gained
   `crypto_stop_coverage_violations: list[dict[str, Any]] | None = None`,
   representing the result of `renquant_execution`'s
   `AlpacaBroker.check_crypto_stop_coverage()` (empty list = fully
   covered). Applied as the same kind of unbypassable final gate as the
   mode check (fix 3): `None` — the caller never evaluated the
   precondition — is explicitly documented and tested as NOT "assume
   covered"; it fails closed exactly like a confirmed violation, naming
   "stop-coverage precondition not evaluated". A non-empty list fails
   closed naming the affected symbols. `crypto_session.py` does not import
   `renquant_execution` or construct a broker connection — the caller
   (which holds the live broker connection) is responsible for calling
   `check_crypto_stop_coverage()` and passing its result in, keeping this
   module's own tests hermetic/dependency-free.

Constraints honored: exits remain unconditionally allowed in every new gate
(never touched by `_apply_final_entry_gates`); the PR was not merged by me,
left open for Codex re-review.

### Tests added

`tests/test_crypto_session.py` grew from 26 to 46 tests, covering:
future/mismatched watermark (blocked, both values named in `reason`) and a
matching-watermark control; digest mismatch and missing-expected-digest
(both blocked, distinct reasons); shadow-mode full-record non-admission
plus a live-mode-all-clear control; a configured non-default
`quiet_interval_minutes` (30 min) honored by both `SessionWindow` directly
and by `evaluate_tick`; invalid `quiet_interval_minutes`/`tick_cadence_seconds`
raising `ValueError` at construction time (including via `from_dict`);
default kill-switch path resolution from `RENQUANT_DATA_ROOT` (and explicit
override); and the three `crypto_stop_coverage_violations` states (`None`
blocks, `[]` allows, non-empty blocks and names symbols, including multiple
symbols).

### Verification (2026-07-12, post-fix)

- `tests/test_crypto_session.py`: 46/46 pass `[VERIFIED]`
- Full suite (`pytest -q` with the repo's sibling-src `PYTHONPATH`, matching
  `make test`): 3778 passed, 5 skipped, 0 failed `[VERIFIED]`
- `tests/test_doc_alignment.py::test_snapshot_not_stale`: passes
  `[VERIFIED]` — the committed `data/strategy_snapshot.json` already
  reflected the `crypto_session` module (fixed by the prior commit on this
  branch, `aeee14f3`); re-ran
  `python scripts/generate_strategy_snapshot.py --update` after this
  revision's code changes and confirmed zero diff, so no further snapshot
  commit was needed.
- Rebased onto `origin/main` (1 commit behind, docs-only architecture-audit
  commit, no conflicts) `[VERIFIED]`

### Judgment calls to double-check

- Exact validation bounds: `quiet_interval_minutes` in `[0, 1440)` (one UTC
  day), `tick_cadence_seconds` in `(0, 3600]`. Not specified anywhere else
  in the RFC; chosen as the loosest sane bounds consistent with "a quiet
  interval can't exceed a session" and "a tick cadence must be positive and
  not absurdly coarse."
- Kill-switch audited root: reused
  `renquant_orchestrator.runtime_paths.default_data_root()` verbatim
  (`RENQUANT_DATA_ROOT` env override, else the umbrella `RenQuant/` runtime
  root) — the same resolver `intraday_session_scheduler.py` already uses
  for the rq105 kill switch, rather than inventing a crypto-specific root.
- `TickResult.mode` added as a plain `str` field (default `"shadow"`,
  always set to `config.mode` by `evaluate_tick`); no enum/literal type
  introduced since `CryptoSessionConfig.mode` itself is an unconstrained
  `str` (existing test `test_full_config` exercises `mode="paper"`).
- Gate ordering in `_apply_final_entry_gates`: mode checked before
  stop-coverage. If both would independently block, only the mode message
  appears in `reason` (short-circuited) — the property "entries allowed
  iff ALL gates pass" still holds regardless of this ordering; each gate's
  own tests hold every other gate constant.

## Reconciliation note (round 2): a duplicate PR surfaced a real gap in the mode gate

A separate PR (`feat/crypto-session-scheduler-v2`, #499) independently
re-implemented the same 5 Codex fixes against the same underlying findings —
a genuine duplication, not a disagreement about what to fix. Comparing the
two surfaced one substantive difference worth keeping: #499 gated entries on
`config.mode in ("live", "paper")`, not `mode == "live"` alone as this PR's
round-1 fix did.

That difference matters and #499 was right to make it: "paper" mode trades
against Alpaca's paper (fake-money) endpoint — the same account this
codebase's Stage-0 paper battery (D-C12, execution#32 / orchestrator#500)
exercises — so it is a genuinely authorized, no-real-capital-at-risk runtime
state, not a record-only one like "shadow". Restricting entries to "live"
alone would have made it impossible to ever validate this scheduler
end-to-end (real order placement, real fill/reject handling) before flipping
to live capital — an oversight in the round-1 fix, not a deliberate choice.

#499's own implementation traded this correct mode-list for a real
regression, though: it checked `config.mode` early (right after the triple
gate) and returned immediately on a non-eligible mode, meaning a
`"shadow"`-mode tick never reached the watermark/digest/quiet-interval
checks at all — the returned `TickResult` would NOT be the full,
richly-populated decision record Codex's finding asked for ("DARK/shadow
should produce decision records only" implies the record itself should still
reflect what the other gates found, not stop short of evaluating them).
This PR's `_apply_final_entry_gates` architecture (every other gate
evaluates fully first; the mode and stop-coverage gates are applied last,
and can only ever narrow `entries_allowed` from `True` to `False`, never
skip evaluation of anything else) already gets this right.

Resolution: kept this PR's architecture, adopted #499's mode-list insight —
`CRYPTO_ENTRY_ELIGIBLE_MODES = frozenset({"live", "paper"})` replaces the
single `mode == CRYPTO_LIVE_MODE` check in `_apply_final_entry_gates`.
`CRYPTO_LIVE_MODE` and the new `CRYPTO_PAPER_MODE` are both kept as named
constants. Two new tests: `test_paper_mode_with_all_gates_clear_allows_entries`
(paper mode reaches `entries_allowed=True` like live) and
`test_unknown_mode_blocks_entries_but_full_record` (an unrecognized mode
value fails closed exactly like shadow, proving the gate checks explicit
set membership, not merely "not shadow"). Full suite: 48 passed (was 46).
#499 was closed in favor of this PR with a comment crediting the mode-list
finding and explaining the decision-record-completeness reasoning above.
