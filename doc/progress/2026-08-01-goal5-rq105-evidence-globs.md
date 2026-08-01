# GOAL-5 / 105 lane — two jobs made judgeable, and the third really is dark

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-5 (105 intraday line)

## What was unjudgeable and why

Six `rq105-*` jobs share `RenQuant/logs/rq105`. Three declared an `evidence_glob`; three
did not, so `launchd_liveness_scan` fell back to a `StandardOutPath` shared with the other
five — **unattributable**, which is not the same as healthy.

Both missing globs are now declared, **derived from each job's own script** rather than
guessed `[本次实测 2026-08-01]`:

| job | script | writes | matches today |
|---|---|---|--:|
| `rq105-batch-scores-export` | `run_batch_scores_export.sh:28` | `batch_scores_export_$TS.log` | **4** |
| `rq105-postclose` | `run_postclose_loggers.sh:24` | `${MOD}_$TS.log` | **22** |

## And the finding underneath

With the ambiguity removed, one rq105 job stands out `[本次实测]`:

| job | glob matches | newest |
|---|--:|---|
| `rq105-quote-logger` | 22 | 2026-07-31 (**0d**) |
| `rq105-session-scheduler` | 21 | 2026-07-31 (**0d**) |
| `rq105-postclose` | 22 | 2026-07-31 (**0d**) |
| `rq105-batch-scores-export` | 4 | — |
| **`rq105-shadow-serving`** | **3** | **2026-07-13 — 18 days** |

Its siblings wrote today; it last wrote on **2026-07-13**. That is consistent with the
GOAL-5 anchor's *"shadow-serving 退出 1"* and it is now the **only** rq105 job the scan
flags, instead of being one of six indistinguishable ones. Its script
(`run_shadow_serving.sh:53,66`) writes the file the existing glob names, so the glob is not
the problem — the job is.

## A bug I wrote and measured out

My first `rq105-postclose` glob was
`{intraday_pairing_logger,entry_timing_shadow}_*.log`. **Python's `glob` does not expand
shell braces**, so it matched **0 files** — and a job whose evidence glob matches nothing is
reported stale forever. That is the failure mode this change exists to remove, reintroduced
by the change itself, and caught only because I globbed it instead of assuming.

One module is declared instead of both, and the manifest comment records why: brace
expansion is unavailable, `entry_timing_shadow` is the **last** module in the script's loop
so its freshness witnesses the whole job, and if it alone fails to write while the job runs
the scan reports STALE — **erring toward alarming, never toward false health**.

## Scope

Manifest-only, and the manifest is the reviewed surface — no plist installed, edited or
disabled, no job touched. Absolute paths are consistent with this file: **43 of 43** jobs
already carry absolute `program_args`.

## Not claimed

That `rq105-shadow-serving` is broken rather than deliberately idle — 18 days without a
write is a fact, and the disposition is the operator's. That `batch_scores_export`'s 4 files
vs its siblings' 22 is a fault; it may simply run on a different cadence, and this PR does
not judge it.

## Tests

11, and none of them looks at my disk — a test asserting that a glob matches files passes
or fails by whose machine runs it. They assert the patterns are Python-expandable (no
`{`, `$`, `~`, backtick), absolute, wildcarded, and inside a logs directory.

My first wildcard test rejected `daily_104/20[0-9][0-9]-…log` because I enumerated `*` and
`?` and forgot `[` — the same enumeration-with-a-gap shape this repo keeps hitting, in a
test written about a gap. Suite: **5195 passed, 2 skipped**.
