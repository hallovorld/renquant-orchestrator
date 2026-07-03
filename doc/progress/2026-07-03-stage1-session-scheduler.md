# Progress — Stage-1 intraday session scheduler + shadow decisions + replay audit (M1 slice 3)

Date: 2026-07-03
Scope: renquant105 Stage-1 build, ORCHESTRATOR slice (RFC #208
`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md` §8 row 3).
Consumed contracts: slice 1 = renquant-execution #20 (MERGED, `order_state_machine`),
slice 2 = renquant-pipeline #163 (OPEN, `intraday_decisioning`).

## Why

§8's merge order puts the orchestrator LAST: execution owns the order lifecycle,
pipeline owns the decision logic on live state, and this repo owns scheduling,
control-plane flags, provenance, and the replay/audit harness. Slices 1–2 exist;
without this slice nothing drives the tick cadence, nothing records a shadow
session, and the §6 no-leak proof has no replay surface. Everything here is
default-OFF and observe-first — NOTHING wires into the live daily run.

## What (3 modules + tests + launchd package, all files-only)

`src/renquant_orchestrator/intraday_session_scheduler.py` — the tick driver:

- **§5 cadence / §11b windows** from the SAME half-day-aware NYSE primitive the
  quote logger uses (`intraday_quote_logger.default_session_calendar`): fixed
  tick (default 720 s), first eligible tick at open+5 min, **entries stop at
  close−30 min, exits continue to the bell** (`apply_entry_window_policy` moves
  post-cutoff entry intents to `skipped` with reason
  `entries_closed_window_cutoff` and backs them out of the session counters);
  early closes scale automatically; non-session days stamp a manifest and exit.
- **Flag plumbing (§10), triple-gated default-OFF**: pinned strategy config
  section `intraday_decisioning.{enabled,mode,tick_seconds,entry_open_delay_seconds,
  entry_close_cutoff_seconds,canary_allowlist,kill_switch_file}` (absent ⇒
  disabled; malformed values collect into `config_errors` and force disabled),
  AND env flag `RENQUANT_INTRADAY_DECISIONING` (default off), AND a kill-switch
  FILE (`data/rq105/intraday_decisioning.KILL`) re-checked every cycle — touch
  it mid-session and the loop halts before the next tick.
- **SHADOW MODE is the only mode**: `mode: "live"` downgrades to shadow with a
  counted warning (`live_mode_downgraded_count`; Stage-2 authorization is a
  separate §9.3a decision). `assert_shadow_never_submits` is a RUNTIME
  assertion on every tick BEFORE persisting: non-shadow mode or any
  broker-submission evidence (child ids / fill fields / broker statuses) in the
  decision payload raises `ShadowModeViolation` and halts the session. This is
  deliberately stronger than the repo's earlier shadow tasks, whose never-submit
  property was a docstring invariant with no enforcement.
- **Slice-2 seam**: the tick runner is injected; the default binding
  (`bind_pipeline_tick_runner`) lazily imports
  `renquant_pipeline.intraday_decisioning` and FAILS CLOSED
  (`PipelineContractUnavailable`) until #163 is merged and pinned — the
  orchestrator never invents a local decision path (CLAUDE.md boundary).
- Outputs (both under the operator data root, never the umbrella git tree):
  append-only schema-versioned `logs/renquant105_pilot/intraday_decisions_shadow.jsonl`
  (one line per tick: intents + blocked_by + envelope counters + input
  fingerprints + the class-C/D inputs) and the per-session run-bundle stamp
  `intraday_session_manifest_<date>.json` (frozen class-A/B inputs +
  fingerprints, tick count, calendar id, config fingerprint), updated
  atomically after every tick.

`src/renquant_orchestrator/intraday_session_inputs.py` — §6 input assembly:

- **Class A**: `load_frozen_daily_signal` reads the latest COMMITTED daily run
  from `runs.alpaca.db` (read-only sqlite URI) with export_batch_scores.py's
  selection discipline (joined `pipeline_runs`, `run_type='live'`, bound
  fingerprints, run-roster coverage floor). **Leak guard enforced twice**: the
  only date queried is the immediately preceding session per the injected
  calendar (today's run is structurally unselectable; an older run is refused,
  never silently served), plus a defensive `run_date < session_date` re-assert;
  the scheduler re-asserts again (`assert_signal_predates_session`) so the
  guard holds even under an injected test-double tick runner.
- **Class B**: `capture_session_start`/`verify_session_start` fingerprint the
  session-start gate inputs with the SAME `hash_jsonable` the pipeline's
  `SessionStartSnapshot.verify()` recomputes (byte-agreement on "frozen").
- **Class C**: `AlpacaLiveStateSource` — GET-only broker reads (`get_account`,
  `get_all_positions`); §7 reservations parsed from a slice-1
  `OrderStateBook.to_snapshot()` state file (`order-state-machine-v1`): open
  BUY children reserve `unfilled_qty × price`, all parents are in-flight dedup
  keys, stale/corrupt/wrong-day books are refused (never silently ignored).

`src/renquant_orchestrator/intraday_replay_audit.py` — §6/§9 auditability:
replays a recorded session against the same frozen inputs and asserts (1)
class-A constancy + the leak guard at rest, (2) class-B fingerprint constancy +
mutation-at-rest detection, (3) class-C/D integrity (each tick's recorded live
state re-hashes to its own `live_state_sha256`), (4) byte-for-byte decision
reproducibility (re-run tick runner + re-apply recorded window phase, canonical
JSON equality), (5) no entry intents in `exits_only` ticks. CLI exits non-zero
on any mismatch; report optionally persisted.

`ops/renquant105/run_session_scheduler.sh` + `com.renquant.rq105-session-scheduler.plist`
— launchd package following the existing house pattern (06:25 PT weekdays,
pinned `renquant-orchestrator-run` checkout, ntfy on failure). The wrapper
ships with `RENQUANT_INTRADAY_DECISIONING` deliberately NOT exported.
README addendum documents the triple gate + the harder-than-N1b activation
gate (pipeline #163 merged AND pinned). **Files only — nothing installed.**

## Tests

53 new tests, all green; full orchestrator suite **1357 passed / 3 skipped**
(CI-equivalent sibling-path setup, includes the new tests). Coverage of the
task's required list: calendar gating (holiday ⇒ no ticks; half-day ⇒ windows
scale; tiny session never inverts), leak guard (today's run refused as class A,
today-dated signal aborts the session, no-fallback-to-older), shadow never-submit
(mode assertion + submission-evidence scan + halted-before-persist + live-mode
downgrade counter), kill switch (pre-session + engaged mid-session between
ticks), replay determinism on a fixture session recorded by the REAL scheduler
(plus 6 tamper-detection cases), envelope cutoff semantics (entries stop /
exits continue, counters backed out), §7 reservations parsing against the
slice-1 snapshot shape, config safe-default/fail-closed parsing, CLI fail-closed
without the pipeline binding, plist/wrapper conventions.

## Landing checklist (install is a SEPARATE authorized step — ask first)

1. Prereqs before any activation: renquant-pipeline #163 merged + pins bumped;
   the N1b gate (#224/#227) already merged; operator authorization recorded.
2. `git -C /Users/renhao/git/github/renquant-orchestrator-run pull --ff-only`
   (pinned run checkout, never the working tree / live umbrella tree).
3. Copy + bootstrap `com.renquant.rq105-session-scheduler.plist` per the README
   (launchctl bootstrap gui/$UID), AFTER setting
   `intraday_decisioning.enabled=true` in the pinned strategy config and
   uncommenting `RENQUANT_INTRADAY_DECISIONING=1` in the wrapper.
4. Provide `--data-manifest`/`--artifact-manifest` JSONs the pipeline tick
   binds against (wrapper defaults point under `data/rq105/`).
5. First shadow session: run the replay audit against the produced manifest +
   JSONL; a clean report is the K=5 readonly clock's tick #1 (§9.3).

Boundary compliance: no broker adapters, no decision/sizing internals, no model
training here; run-bundle persisted per session; all broker/DB access read-only.
