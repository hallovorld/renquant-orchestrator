# Replay staleness: 150s frozen for the shadow-serving checkpoints

STATUS: one-constant fix with the measurement that forced it.

WHAT/WHY: the first scheduled S3-b serve (2026-08-25 13:45) crashed all
four checkpoints on the zero-fresh-rows refusal — the guard working as
designed on a wrong parameter. The collector's 15s staleness default is
real-time semantics; the wrapper is a post-close replay at :00 checkpoints
against the #216 quote logger. MEASURED 2026-08-25 [full-file scan, not a
tail window — an earlier tail-window read produced a false "logger only ran
20 minutes" conclusion, corrected by the full scan: 295 AAPL ticks, 394
logger cycles, full session]: logger cadence median 60.3s; nearest-prior-
tick ages at the four checkpoints 101/12/105/25s. With 15s only the lucky
12s checkpoint could serve. 150s = 2.5x cadence: admits the last one-to-two
logger cycles, still censors dead names. The zero-fresh crash path is
retained unchanged — it caught this loudly, which is its job.

Effect on the S3-c evidence base: day-1 (2026-08-25) records four named
refusals (serving_failed rc=1 at the entry loop — the P1-1 gate chain from
#1059 worked end-to-end on its first real firing); the clean-session count
starts when this deploys, i.e. tomorrow's 13:45 run.

§4(b): measurements above [MEASURED — intraday_ticks.jsonl full scan +
quote_logger_2026-08-25.log cycle count]; today's serving log shows 4
ProvenanceError refusals and the entry-plan record carries
`serving_failed rc=1` [VERIFIED — both logs read].
