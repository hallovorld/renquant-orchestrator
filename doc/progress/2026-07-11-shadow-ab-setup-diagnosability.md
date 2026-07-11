# 2026-07-11 — shadow-ab wrapper SETUP diagnosability

Three CI occurrences on 2026-07-11 (main's #463 merge run, #465, #464 — all
healed on rerun) of `test_shadow_ab_daily_script` failing with the wrapper
exiting 2 and **empty stdout/stderr**: the wrapper's first act is
`exec >>"$LOG" 2>&1`, so every SETUP failure reason lands in a log file CI
never captures. The flake's root cause is therefore still unknown — this PR
makes the NEXT occurrence self-diagnosing instead of guessing now:

- wrapper: original stderr saved on fd3; all eight SETUP failure sites route
  through one `setup_fail` helper that mirrors the reason to fd3; the final
  `shadow-ab exit=N` line is mirrored too.
- tests: every script invocation goes through `_run_script`, which prints the
  session-log tail + stderr so pytest surfaces them on failure.

No behavioral change to any exit code or to the launchd path (fd3 writes go
to launchd's stderr file). Local sandbox baseline for this suite (8F/2P,
fixture `git -C` env issue) unchanged and pre-existing on origin/main.
