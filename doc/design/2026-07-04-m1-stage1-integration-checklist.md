# M1: Stage-1 integration checklist (readonly K=5)

DATE: 2026-07-04
STATUS: INTEGRATION SPEC (all code delivered; this documents the wiring + AC)
BLOCKS: M2 (frozen canary), S10 (full execution-leak study from live shadow data)

## Purpose

M1 is the integration milestone that wires the three delivered code slices into
a running intraday shadow loop. The code is done — this document specifies
what must be GREEN before the first readonly session and what the 5-session
acceptance criteria are.

---

## 1. Cross-repo dependency map

### 1.1 Import graph (runtime)

```
intraday_session_runner.py (orchestrator — entry point)
  ├── intraday_live_executor.py (orchestrator)
  │     ├── renquant_execution.order_state_machine   [SLICE 1]
  │     │     └── OrderStateBook, BrokerPort, ParentIntent, ...
  │     ├── renquant_common.notify
  │     └── renquant_artifacts.hash_jsonable
  ├── intraday_session_scheduler.py (orchestrator)
  │     ├── renquant_artifacts.hash_jsonable
  │     ├── renquant_pipeline.intraday_decisioning   [SLICE 2]
  │     │     └── run_intraday_decision_tick, FrozenDailySignal, ...
  │     └── intraday_quote_logger → renquant_common.market_calendar
  ├── software_stop.py (orchestrator)
  └── entry_timing_policy.py (orchestrator)
```

### 1.2 Slice status

| Slice | Repo | Module | PR | Status | Import path |
|---|---|---|---|---|---|
| 1 (OSM) | renquant-execution | `order_state_machine.py` | #20 | Merged | `renquant_execution.order_state_machine` |
| 2 (tick) | renquant-pipeline | `intraday_decisioning.py` | #163 | Merged | `renquant_pipeline.intraday_decisioning` |
| 3 (sched) | renquant-orchestrator | `intraday_session_scheduler.py` + runner | #268/#303/#335 | Merged | direct (same package) |

### 1.3 Shared library versions required

| Library | Min version | Key export used |
|---|---|---|
| `renquant-common` | ≥0.10.0 | `market_calendar.SessionBounds`, `notify.send` |
| `renquant-artifacts` | ≥0.1.0 | `hash_jsonable` |
| `renquant-execution` | ≥0.1.0 (post-#20) | `order_state_machine.*` (14 symbols) |
| `renquant-pipeline` | post-#163 | `intraday_decisioning.run_intraday_decision_tick` |

---

## 2. Prerequisites (all must be GREEN before session 1)

### 2.1 Test suites

| Repo | Command | Required state |
|---|---|---|
| renquant-orchestrator | `make test` | All pass |
| renquant-execution | `pytest tests/` | All pass; OSM tests specifically |
| renquant-pipeline | `pytest kernel/tests/test_intraday_decisioning.py` | All pass |
| renquant-common | `pytest` | All pass |

### 2.2 Pin alignment

The orchestrator run checkout (`renquant-orchestrator-run`) must pin to
commits that include all three slices:

- `renquant-execution` pin: ≥ commit that merged #20
- `renquant-pipeline` pin: ≥ commit that merged #163
- `renquant-common` pin: ≥ v0.10.0 (market_calendar)
- `renquant-artifacts` pin: current main (hash_jsonable stable)

**Verification**: `python -c "from renquant_pipeline import intraday_decisioning; print('OK')"` succeeds in the run venv.

### 2.3 Import census

Every symbol in the import graph (§1.1) must resolve at runtime. The census
script verifies this mechanically:

```bash
python -c "
from renquant_orchestrator.intraday_session_runner import SessionRunner, SessionRunnerConfig
from renquant_orchestrator.intraday_session_scheduler import bind_pipeline_tick_runner, SessionScheduler
from renquant_orchestrator.intraday_live_executor import resolve_stage2_arming
from renquant_orchestrator.software_stop import SoftwareStopEvaluator
from renquant_execution.order_state_machine import OrderStateBook, BrokerPort
from renquant_pipeline.intraday_decisioning import run_intraday_decision_tick
from renquant_common.market_calendar import SessionBounds
from renquant_artifacts import hash_jsonable
print('CENSUS PASS — all imports resolve')
"
```

**Fail mode**: `ImportError` → pin not advanced or package not installed.

### 2.4 Configuration

Strategy config (`strategy_config.json`) must contain:

```json
{
  "intraday_decisioning": {
    "enabled": true,
    "mode": "shadow",
    "tick_seconds": 720,
    "entry_open_delay_seconds": 300,
    "entry_close_cutoff_seconds": 1800
  }
}
```

- `enabled: true` — gate 1 of the triple gate
- `mode: "shadow"` — CRITICAL: live mode is downgraded to shadow with warning (code enforces this)
- `tick_seconds` — decision-tick cadence in seconds (default 720 = the RFC's fixed
  12-min Stage-1 cadence; `load_intraday_config()` rejects non-positive values and
  falls back to the default, recording a `config_errors` entry)
- `entry_open_delay_seconds` — no new entries in the first N seconds after session
  open (default 300 = 5 min)
- `entry_close_cutoff_seconds` — no new entries in the last N seconds before session
  close (default 1800 = 30 min); exits are not affected by this cutoff

These three keys, `enabled`, and `mode` are read by `load_intraday_config()` in
`src/renquant_orchestrator/intraday_session_scheduler.py`. A missing/malformed key
does NOT fail the section outright — `load_intraday_config()` falls back to that
key's default and appends a message to `config_errors`, so a typo'd key name here
is silently ignored rather than raising, which is exactly the failure mode this
checklist exists to prevent operators from hitting unnoticed.

### 2.5 Environment

- `RENQUANT_INTRADAY_DECISIONING=1` exported in `run_session_scheduler.sh` (gate 2)
- Kill-switch file ABSENT: `data/rq105/intraday_decisioning.KILL` must not exist (gate 3)
- The env flag is NOT exported by default in the wrapper — activation = uncommenting one line

### 2.6 Collector infrastructure

| Collector | Plist | Status |
|---|---|---|
| Quote logger | `ops/renquant105/com.renquant.rq105-quote-logger.plist` | Exists; must be `launchctl bootstrap`ed |
| Session scheduler | `ops/renquant105/com.renquant.rq105-session-scheduler.plist` | Exists; fires weekdays 06:25 ET |
| Liveness checker | `ops/renquant105/com.renquant.rq105-liveness.plist` | Exists; alerts on stale outputs |
| Batch scores export | `ops/renquant105/com.renquant.rq105-batch-scores-export.plist` | Exists; feeds class-A signals |

Current-macOS launchctl verbs only (`load`/`unload` are deprecated, per
`ops/renquant105/README.md` and `tests/test_rq105_collector_scheduling.py`):

```bash
launchctl bootstrap "gui/$UID_NUM" ~/Library/LaunchAgents/com.renquant.rq105-<p>.plist
# unload: launchctl bootout "gui/$UID_NUM/com.renquant.rq105-<p>"
# force-run once: launchctl kickstart "gui/$UID_NUM/com.renquant.rq105-<p>"
```

### 2.7 Kill switch test

Before session 1, verify the kill switch works:
1. Start the scheduler with gates satisfied
2. `touch $DATA_ROOT/data/rq105/intraday_decisioning.KILL`
3. Observe: next tick cycle detects file, logs "kill switch active", exits cleanly
4. Remove the file; restart; session resumes

---

## 3. Five-session acceptance criteria

From RFC #208 §8: "5 readonly sessions, replay green, census complete."

### 3.1 Per-session checks

| Check | Criterion | Evidence |
|---|---|---|
| No errors | Session completes without exception; exit code 0 | launchd stdout log |
| Shadow log populated | `intraday_decisions_shadow.jsonl` has ≥1 tick record per session | file inspection |
| Schema valid | Every record has `schema_version: "rq105-intraday-shadow-v1"`, all required fields present | `jq` validation |
| Tick count plausible | ~30-32 ticks for full session (6.5h / 720s); ~15-16 for half day | count vs calendar |
| Manifest written | `intraday_session_manifest_<date>.json` exists with fingerprints | file inspection |
| Entry window enforced | No entry intents after `close - 30min`; exits continue | log grep |
| Signal inputs frozen | Class-A/B unchanged within session (manifest fingerprint stable) | manifest hash |

### 3.2 Replay audit (after 5 sessions)

Run `intraday_replay_audit.py` against the 5 sessions' persisted inputs:

```bash
python -m renquant_orchestrator.intraday_replay_audit \
  --data-root $DATA_ROOT \
  --sessions 5
```

**Pass criterion**: every replayed tick produces the SAME decision payload as
the original shadow log entry (bit-exact JSON match after key-sort).
**Fail criterion**: any decision divergence → non-determinism in the pipeline
tick (state leak, random seed, or clock dependency).

### 3.3 Census complete

The census from §2.3 passes in the SAME environment the sessions ran in (not
a dev venv, not a fresh install — the production-like run venv).

### 3.4 Overall M1 AC

All of the following simultaneously:
- [ ] 5 sessions complete (§3.1 all GREEN for each)
- [ ] 0 replay divergences (§3.2)
- [ ] Census PASS in run venv (§2.3)
- [ ] Kill switch test passed (§2.7)
- [ ] No manual intervention required during any session

---

## 4. Risk register

| Risk | Impact | Mitigation | Rollback |
|---|---|---|---|
| Pipeline tick raises on unexpected market data | Session aborts mid-day; no shadow data for that day | Wrap tick call in try/except; log error; continue to next tick | Kill switch; next session starts clean |
| Import fails at runtime (pin drift) | Session won't start | Census check (§2.3) before activation; CI pin-freshness check | Don't advance pin until census passes |
| Quote logger not running (no class-D) | Ticks run but produce censored observations (no intraday quotes to pair) | Liveness checker alerts; §2.6 all collectors loaded | Start quote logger; session still runs (decisions don't depend on D) |
| Strategy config missing `intraday_decisioning` section | Triple gate: disabled → immediate exit | Verified in §2.4 before activation | Add section; restart |
| Deterministic replay fails | Signals non-determinism in the pipeline tick path | Investigate: floating-point? clock? state mutation? | Disable scheduler until root cause fixed |
| Shadow log grows unbounded | Disk pressure over months | Log rotation (date-partitioned by design: one file per session) | n/a — already date-stamped |
| Half-day session miscounts | Fewer ticks than expected; not a failure | Calendar-aware session windows handle this; check against known half-days | n/a — expected behavior |

### 4.1 What constitutes a session FAILURE

- Uncaught exception causing non-zero exit
- Zero tick records in the shadow log (session ran but produced nothing)
- Kill switch was needed to recover (indicates instability)

### 4.2 What is EXPECTED behavior (not a failure)

- Non-session day → immediate exit with `status=non_session_day`
- Gates not satisfied → immediate exit (before activation)
- Fewer ticks on half-days
- No entry intents past the entry cutoff (entry window enforcement working correctly)

---

## 5. Activation sequence

```
1. Verify all §2 prerequisites GREEN
2. `launchctl bootstrap "gui/$UID_NUM" <plist>` the session scheduler plist (§2.6)
3. Wait for first weekday session
4. After session: verify §3.1 checks
5. Repeat for 5 sessions
6. Run replay audit (§3.2)
7. Run census in run venv (§2.3 / §3.3)
8. All pass → M1 AC MET → unlock M2
```

---

## 6. What M1 unlocks

- **M2 (frozen canary)**: live arming requires M1 GREEN (5 clean shadow sessions)
- **S10 (execution leak)**: shadow tick data feeds the paired IS study
- **Entry-timing pilot**: shadow evaluator produces comparative timing data
- **Software stop validation**: stop signals logged each tick; after 20+ sessions
  can validate stop thresholds against realized outcomes
