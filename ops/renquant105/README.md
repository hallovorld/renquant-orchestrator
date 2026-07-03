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
