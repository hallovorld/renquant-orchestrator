# rq105 collector scheduling — N1 landing package (#231 N1; #208 Stage-1; #212 liveness rule)

OBSERVE-ONLY. Nothing here places orders, touches positions/cash/pins/gates, or writes any
canonical prod path. This package makes the merged Stage-1 collectors (#215 pairing harness,
#216 quote logger, #220 entry-timing shadow) RUN on a schedule with a lapse alert — the
"collectors built but never running = deployed-but-dark" failure this repo has already paid for.

## Contents

| File | Role | Schedule (PT, weekdays) |
|---|---|---|
| `run_quote_logger.sh` | session-long tick feed (`intraday_quote_logger`, self-loops with internal NYSE session gate) | 06:25 start |
| `run_postclose_loggers.sh` | `intraday_pairing_logger` + `entry_timing_shadow` for today's session | 13:15 |
| `rq105_liveness_check.py` | verifies today's outputs exist; **ntfy per missing item** (liveness ≠ freshness, #212) | 14:00 |
| `com.renquant.rq105-{quote-logger,postclose,liveness}.plist` | launchd jobs for the above | as above |

## This package is split N1a / N1b — read before running anything

Per #229 (H2 execution roadmap)'s dependency DAG: live rq105 collection may not start until
**both #224** (broker-regulatory/settlement envelope) **and #227** (Stage-1 measurement-integrity
pins) have merged to `main` — starting earlier risks a retroactively-dirty pilot corpus, since the
envelope/census gates those PRs add are exactly what makes the collected data trustworthy later.

- **N1a — safe now, no gate.** Copy/validate the plists, run the test suite, exercise the
  liveness-check logic in isolation. Nothing here touches real launchd state or places any live
  job on a schedule.
- **N1b — GATED, do not run early.** The actual `launchctl bootstrap` step. `ops/renquant105/
  check_activation_prereqs.py` enforces this mechanically (heuristic RFC-text check, not a
  cryptographic proof — see its own docstring) and will refuse with a non-zero exit if #224/#227
  haven't landed; **do not rely on the script alone** — confirm directly first
  (`gh pr view 224 227 --repo hallovorld/renquant-orchestrator --json state`).

### N1a — install + validate (safe now)

Schedules below are evaluated in the launchd host's LOCAL system time zone (launchd
`StartCalendarInterval` has no explicit-TZ field); the Hour/Minute values in the committed
plists assume the host's local time zone is already Pacific — re-derive them if lander deploys
to a host in a different zone.

```bash
# 1. Pinned RUN checkout (never the working tree; never the live umbrella tree):
git clone --branch main https://github.com/hallovorld/renquant-orchestrator.git \
  /Users/renhao/git/github/renquant-orchestrator-run
# (subsequent syncs: git -C .../renquant-orchestrator-run pull --ff-only)

# 2. Create the log directories — safe to do now, independent of the N1b gate
#    (launchd needs StandardOutPath/StandardErrorPath's parent directory to
#    exist on first launch; it will not create it):
mkdir -p /Users/renhao/git/github/RenQuant/logs/rq105
mkdir -p /Users/renhao/git/github/RenQuant/logs/renquant105_pilot

# 3. Validate the plists parse and the liveness-check logic works, WITHOUT
#    touching real launchd state:
chmod +x /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/*.sh
PYTHONPATH=/Users/renhao/git/github/renquant-orchestrator-run/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python -m pytest \
  /Users/renhao/git/github/renquant-orchestrator-run/tests/test_rq105_collector_scheduling.py -q
```

### N1b — activate live collection (BLOCKED until #224 + #227 merge)

```bash
# 0. MANDATORY gate check — refuses (non-zero exit) if #224/#227 haven't landed
#    on the pinned checkout's main. Do NOT proceed past this step on failure:
/Users/renhao/git/github/RenQuant/.venv/bin/python \
  /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/check_activation_prereqs.py

# 1. Install + load the jobs (current-macOS launchctl — `load`/`unload` are
#    deprecated; use bootstrap/bootout against the per-user GUI domain):
UID_NUM="$(id -u)"
for p in quote-logger postclose liveness; do
  cp /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/com.renquant.rq105-$p.plist \
     ~/Library/LaunchAgents/
  launchctl bootstrap "gui/$UID_NUM" ~/Library/LaunchAgents/com.renquant.rq105-$p.plist
done
# Unload (e.g. before re-installing an updated plist):
#   launchctl bootout "gui/$UID_NUM/com.renquant.rq105-<p>"
# Force-run once now, off-schedule, for a real end-to-end smoke test:
#   launchctl kickstart "gui/$UID_NUM/com.renquant.rq105-<p>"

# 2. Smoke (off-hours safe): one forced sample + a liveness dry-run
PYTHONPATH=/Users/renhao/git/github/renquant-orchestrator-run/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python -m renquant_orchestrator.intraday_quote_logger \
  --env-file /Users/renhao/git/github/RenQuant/.env --data-root /Users/renhao/git/github/RenQuant \
  --once --force --json
/Users/renhao/git/github/RenQuant/.venv/bin/python \
  /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/rq105_liveness_check.py
```

## Acceptance — split N1a / N1b, do not conflate

- **N1a acceptance (achievable now):** `tests/test_rq105_collector_scheduling.py` passes (16/16);
  all 3 plists parse with valid 0-23 hours matching the documented 06:25/13:15/14:00 PT schedule;
  the liveness-check logic correctly identifies session vs. non-session days against the real NYSE
  calendar in a dry run (no real job scheduled).
- **N1b acceptance (#231 §1 — starts ONLY once N1b is actually activated, which is gated above):**
  3 consecutive LIVE sessions with (a) quote-log rows for ≥90% of the watchlist, (b) a pairing row
  per live buy, (c) entry-timing shadow rows present — plus one test-fired lapse alert (delete a
  day's log and run the liveness check). This clock has NOT started as of this PR; it starts only
  once an operator has confirmed #224+#227 are merged and completed the N1b activation steps above.

## Open items

1. **`shadow_realtime_serving` is NOT scheduled**: it requires `--batch-scores-json` (the frozen
   T-1 batch score vector). The producer — an export step at the end of the daily run — does not
   exist yet; wiring it is a small follow-up PR (daily_104 post-run export →
   `data/rq105/batch_scores_<date>.json`), after which a fourth plist mirrors the quote logger.
2. Env assumptions: `RQ_ROOT=/Users/renhao/git/github/RenQuant` (has `.env` with Alpaca keys +
   `NTFY_TOPIC`), umbrella `.venv` as the interpreter. Override via env vars in the wrappers.
3. This package intentionally ships as REPO FILES + install doc: the loop that produced it
   advances direction only — installation on the machine is the landing step and stays with the
   operator/lander per the loop's charter.

## Addendum (batch-scores export + shadow serving — resolves open item #1)

| File | Role | Schedule (PT, weekdays) |
|---|---|---|
| `export_batch_scores.py` | export the FROZEN batch score vector (latest pre-session full run → `data/rq105/batch_scores_<date>.json` + meta) | 06:15 |
| `run_shadow_serving.sh` | post-close replay of `shadow_realtime_serving` at 4 fixed ET checkpoints (10:00/12:00/14:00/15:30, DST-correct) against the frozen vector | 13:45 |
| `com.renquant.rq105-{batch-scores-export,shadow-serving}.plist` | launchd jobs | as above |

These two jobs are N1b (GATED) exactly like the main package — installing/bootstrapping them
early risks the same retroactively-dirty pilot corpus #229's dependency DAG exists to prevent.
Install mirrors the main package (current-macOS launchctl verbs — `load`/`unload` are
deprecated, per the N1a/N1b section above):
```bash
# 0. MANDATORY gate check — same guard as the main package, refuses (non-zero
#    exit) if #224/#227 haven't landed on the pinned checkout's main:
/Users/renhao/git/github/RenQuant/.venv/bin/python \
  /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/check_activation_prereqs.py

UID_NUM="$(id -u)"
for p in batch-scores-export shadow-serving; do
  cp /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/com.renquant.rq105-$p.plist \
     ~/Library/LaunchAgents/ && launchctl bootstrap "gui/$UID_NUM" ~/Library/LaunchAgents/com.renquant.rq105-$p.plist
done
# unload: launchctl bootout "gui/$UID_NUM/com.renquant.rq105-<p>"
```
Fail-safety: no export, a stale/hash-mismatched bundle, or coverage below the run's own
90%-of-roster floor → shadow serving SKIPS the day with an ntfy alert (never serves a stale or
unfingerprinted vector silently); the exporter requires a completed `pipeline_runs` row with a
bound strategy/config/artifact fingerprint before it will export anything at all.

## Addendum 2 (Stage-1 SHADOW session scheduler — M1 slice 3, #208 §8 row 3)

| File | Role | Schedule (PT, weekdays) |
|---|---|---|
| `run_session_scheduler.sh` | shadow-only intraday decision scheduler (`intraday_session_scheduler`, self-loops on the config tick cadence with an internal NYSE session gate; §11b windows) | 06:25 start |
| `com.renquant.rq105-session-scheduler.plist` | launchd job for the above | as above |

This job is **shadow-only and default-OFF behind a TRIPLE gate**: (1) the pinned strategy
config must set `intraday_decisioning.enabled: true`, (2) the env flag
`RENQUANT_INTRADAY_DECISIONING=1` must be set (the wrapper ships with it commented out),
(3) the kill-switch file `data/rq105/intraday_decisioning.KILL` must be absent — touching it
mid-session halts the loop before the next tick. Shadow mode is RUNTIME-ASSERTED in the
module (`assert_shadow_never_submits`): it logs decision intents to
`logs/renquant105_pilot/intraday_decisions_shadow.jsonl` + a per-session manifest and can
never place anything; `mode: "live"` in config downgrades to shadow with a counted warning
(Stage-2 authorization is a separate §9.3a decision).

Activation is gated HARDER than N1b: in addition to the #224/#227 prereq check, the real
pipeline tick requires **renquant-pipeline #163 (slice 2) merged AND pinned** — until then the
scheduler fails closed at startup (`renquant_pipeline.intraday_decisioning` not importable)
rather than inventing a local decision path. Do NOT bootstrap this plist until an operator
has recorded that authorization; installing the files is a landing step (ask first).

Replay/audit (run any time, read-only): verifies a recorded session reproduces byte-for-byte
from its frozen inputs and that the §6 four-class invariants held (see #208 §6/§9):
```bash
PYTHONPATH=/Users/renhao/git/github/renquant-orchestrator-run/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python -m renquant_orchestrator.intraday_replay_audit \
  --manifest /Users/renhao/git/github/RenQuant/logs/renquant105_pilot/intraday_session_manifest_<date>.json \
  --shadow-log /Users/renhao/git/github/RenQuant/logs/renquant105_pilot/intraday_decisions_shadow.jsonl \
  --strategy-config <pinned strategy_config.json> \
  --data-manifest <data_manifest.json> --artifact-manifest <artifact_manifest.json> --json
```

## Paper trading setup (Stage-2 paper canary — #365)

Paper trading is the pre-registration experiment for rq105 live canary trading. It uses
`PaperBrokerPort` (zero capital risk) with a relaxed evidence floor
(`MIN_SHADOW_SESSIONS_CLEAN_PAPER = 1` vs the live `MIN_SHADOW_SESSIONS_CLEAN = 5`).

### Pre-flight: readiness checker (read-only)

Run the readiness checker BEFORE attempting to enable paper trading. It verifies every
prerequisite the session runner will evaluate at startup, prints a pass/fail checklist,
and provides remediation instructions for any failures. It modifies nothing.

```bash
PYTHONPATH=/Users/renhao/git/github/renquant-orchestrator-run/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python \
  /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/check_paper_trading_readiness.py
```

### Enablement steps (operator — one-time setup)

All steps below are OPERATOR actions. The readiness checker tells you which are missing.

1. **Create the section 9.4 economic authorization file** (the paper-mode gate):
   ```bash
   mkdir -p /Users/renhao/git/github/RenQuant/data/rq105
   cat > /Users/renhao/git/github/RenQuant/data/rq105/section_9_4_economic_authorization.json << 'EOF'
   {"authorized": true, "prereg_id": "rq105-paper-canary-prereg-v1"}
   EOF
   ```
   The `prereg_id` value `rq105-paper-canary-prereg-v1` is what triggers paper mode in the
   session runner — it derives `config.paper=True` from this, NOT from a config flag.

2. **Create the stage2 authorization file** (the §9.3a gate 2):
   ```bash
   # This file declares the canary envelope — allowlist, loss budget, caps.
   # The operator must fill in the actual values for their deployment.
   # See Stage2Authorization in intraday_live_executor.py for the full schema.
   ```

3. **Set the env flag** (§9.3a gate 3):
   ```bash
   export RENQUANT_INTRADAY_LIVE=1
   # Or add to the .env file / launchd plist for persistent sessions.
   ```

4. **Ensure kill switch is absent** (§9.3a gate 4 — should be absent by default):
   ```bash
   # Verify:
   ls /Users/renhao/git/github/RenQuant/data/rq105/intraday_decisioning.KILL
   # If present, remove: rm <path>
   ```

5. **Ensure at least 1 clean shadow session** has been recorded (paper-mode evidence floor):
   ```bash
   ls /Users/renhao/git/github/RenQuant/logs/renquant105_pilot/session_manifest_*.json
   ```

6. **Re-run the readiness checker** to confirm all checks pass:
   ```bash
   PYTHONPATH=/Users/renhao/git/github/renquant-orchestrator-run/src \
     /Users/renhao/git/github/RenQuant/.venv/bin/python \
     /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/check_paper_trading_readiness.py
   ```

### Safety properties

- Paper mode is RUNTIME-ASSERTED: the session runner verifies the port returned by
  `port_factory()` is a genuine `PaperBrokerPort` — a mismatch (e.g., a real broker port
  under a paper prereg_id) is a hard refusal, not a warning.
- The `RENQUANT_INTRADAY_LIVE` env flag and the kill switch file provide independent
  circuit breakers: touch `data/rq105/intraday_decisioning.KILL` to halt mid-session.
- The readiness checker is READ-ONLY — it never creates or modifies any files.
