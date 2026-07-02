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

## Install (operator / lander — one command per step)

```bash
# 1. Pinned RUN checkout (never the working tree; never the live umbrella tree):
git clone --branch main https://github.com/hallovorld/renquant-orchestrator.git \
  /Users/renhao/git/github/renquant-orchestrator-run
# (subsequent syncs: git -C .../renquant-orchestrator-run pull --ff-only)

# 2. Install + load the jobs:
chmod +x /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/*.sh
for p in quote-logger postclose liveness; do
  cp /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/com.renquant.rq105-$p.plist \
     ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.renquant.rq105-$p.plist
done

# 3. Smoke (off-hours safe): one forced sample + a liveness dry-run
PYTHONPATH=/Users/renhao/git/github/renquant-orchestrator-run/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/python -m renquant_orchestrator.intraday_quote_logger \
  --env-file /Users/renhao/git/github/RenQuant/.env --data-root /Users/renhao/git/github/RenQuant \
  --once --force --json
/Users/renhao/git/github/RenQuant/.venv/bin/python \
  /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/rq105_liveness_check.py
```

## Acceptance (N1 AC, #231 §1)

3 consecutive sessions with (a) quote-log rows for ≥90% of the watchlist, (b) a pairing row per
live buy, (c) entry-timing shadow rows present — plus one test-fired lapse alert (delete a day's
log and run the liveness check).

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
