# Gate 2 arming moves to an operator-owned runtime file (r2 after codex review)

Date: 2026-08-26
Branch: `ops/legitimize-intraday-decisioning` (PR #1067)

## r1 → r2

r1 committed the live dirty-tree export (`RENQUANT_INTRADAY_DECISIONING=1`)
verbatim. Codex correctly refused: that silently converts the repository
default from operator-armed to code-armed, contradicts the control-plane test
`test_session_scheduler_wrapper_does_not_hard_export_activation_flag` and the
documented triple-gate contract (wrapper header, ops README, 2026-07-03
progress doc, as-built), and infers a persistent-default authority from a
14-day-old dirty edit instead of a first-hand record.

r2 keeps BOTH properties instead of trading one for the other:

- **Committed default stays OFF.** The wrapper exports the flag ONLY when the
  operator-owned arming file validates:
  `data/rq105/intraday_decisioning.armed.json`
  (`{"armed": true, "operator", "armed_at", "authority"}`), checked
  fail-closed by the new `renquant_orchestrator.rq105_arming` module
  (absent / malformed / `armed != true` / missing provenance ⇒ OFF, reason
  logged). Mirrors the existing gate-3 kill-switch pattern — an operator-owned
  runtime file outside git.
- **An authorized activation survives checkout recovery.** The arming state no
  longer lives in the working tree, so a `git checkout --` or sync conflict
  (the 2026-08-24 #1044 near-loss) cannot silently disarm it.
- **Authority is first-hand, not inferred.** Merging this PR arms NOTHING.
  The operator arms by creating the file (a recorded landing step that
  re-expresses the standing 2026-08-12 G-H authorization, or declines to).
  Agents never write rq105 authorization files (LONG-ledger class).

## Surfaces updated coherently (codex point 2)

- `ops/renquant105/run_session_scheduler.sh` — header gate-2 wording + the
  arming block replacing the hard export.
- `src/renquant_orchestrator/rq105_arming.py` — NEW, the fail-closed
  validator (CLI: exit 0 armed / 1 not / 2 usage).
- `tests/test_intraday_session_scheduler.py` — the control-plane test is
  REPLACED (not weakened): the new test asserts exactly one activation export
  and that it sits INSIDE the arming-file conditional; plus 8 fail-closed
  unit tests for the module including the documented rollback
  (`armed: false` disarms) and CLI exit codes.
- `ops/renquant105/README.md` — triple-gate item 2 rewritten.
- `doc/design/renquant-105-as-built.md` — Stage-1 gate line annotated.
- `doc/progress/2026-07-03-stage1-session-scheduler.md` — dated amendment
  (history preserved; step 3's "uncomment the wrapper line" superseded).

## Deploy / transition (landing actions, operator-gated)

1. Merge + `-run` sync: the local dirty edit CONFLICTS with this change by
   design — resolution is `git checkout -- ops/renquant105/run_session_scheduler.sh`
   (accept the reviewed arming block). At that instant gate 2 is DISARMED
   (file does not exist yet).
2. Operator creates the arming file (one recorded landing step) citing the
   2026-08-12 authorization — decisioning resumes. Sequenced back-to-back,
   the gap is zero scheduled sessions (sync + arming both outside RTH).
3. Disarm forever after: delete the file or set `"armed": false`; kill-switch
   unchanged for mid-session halts.

## §4(b) evidence

- Module + wrapper policy tests: 9 new tests green locally [VERIFIED below].
- `bash -n` clean on the rewritten wrapper.
- The wrapper's arming block logs provenance into the session log, so every
  armed session records WHO/WHEN/UNDER-WHAT-AUTHORITY it ran armed.
