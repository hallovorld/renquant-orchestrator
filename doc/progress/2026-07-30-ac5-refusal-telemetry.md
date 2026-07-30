# Progress: GOAL-5 AC5 — the refusals fire, nothing aggregates them

STATUS:   delivered. Read-only aggregator; no production surface touched.

WHAT:     `ops/refusal_telemetry.py` — parses the daily-run logs and reports
          funnel-integrity refusal firings, exiting non-zero when one fired
          inside an alert window.

WHY/DIR:  AC5 is "silent-refusal telemetry". My first framing was wrong twice
          before landing here, and both corrections matter:
          1. I nearly built a cross-reason mass-refusal DETECTOR. It already
             exists — `task_funnel_integrity.py` registers six checks
             (`single_gate_funnel_kill`, `universe_admission_collapse`,
             `threshold_scale_mismatch`, `fail_close_event`,
             `wash_sale_mass_block`, `zero_priced_candidates`). Checking the
             existing contract first is what stopped a duplicate.
          2. I then measured "0 firings" and almost reported that all six
             safety checks were dead. I had grepped `logs/*.log`, which holds
             ad-hoc TRAINING logs; the daily runner writes to
             `logs/daily_104/` (`daily_104.sh:35`, `LOG_DIR="$REPO_DIR/logs/daily_104"`).
             Wrong object, right method — the eighth instance in 24h.

EVIDENCE: artifact: `ops/refusal_telemetry.py`, read against the live
          `logs/daily_104/` directory (169 files), READ-ONLY.
          `[VERIFIED-now]` on the real directory, 169 log files:
            wash_sale_mass_block         13 firings / 12 files /  8 dates
            single_gate_funnel_kill       6 /  6 /  6
            fail_close_event              6 /  6 /  6
            universe_admission_collapse   1 /  1 /  1
            threshold_scale_mismatch      1 /  1 /  1
            zero_priced_candidates        0 /  0 /  0
          **20 firings in the 7 days to 2026-07-30**, across `fail_close_event`,
          `single_gate_funnel_kill` and `wash_sale_mass_block`. The
          `wash_sale_mass_block` count is consistent with the independently
          measured "buys zeroed on 3 of the last 5 sessions".
          And `runs.alpaca.db` holds **0 rows** for any of them
          `[VERIFIED-prior — this session]`.
  prod or exp:    Read-only. Opens log files; writes nothing.
  existing data:  Yes — logs already on disk. No compute, no spend.
  best-known?:    Yes for the aggregate. The tool states, rather than hides,
                  that parsing logs is a RECONSTRUCTION: its counts are a FLOOR,
                  because a firing whose log rotated away is invisible to it.
  scope:          `renquant-orchestrator` ops + this doc. No pipeline change, no
                  pin, no config.

SCOPE/LIMITS:
          This does NOT make the refusals durable — it makes existing evidence
          aggregatable. The durable fix is for the pipeline to persist each
          finding as a row; that belongs in renquant-pipeline and is not done
          here.
          It ABORTS with exit 2 when `--log-dir` is not a directory, and says
          why: pointing it at training logs yields zeros that read as "nothing
          fired". That is the exact error this tool was born from, so refusing is
          better than returning a clean-looking zero.
          An unknown check-like token near a funnel_integrity line is reported as
          UNTRACKED rather than dropped — a refusal reason the tool does not know
          about is the one it must not miss.
          `zero_priced_candidates` at 0 is NOT interpreted. It may never have
          occurred, or may never execute; distinguishing those needs the pipeline
          side and is left open rather than guessed.

VERIFICATION:
          Run against `logs/daily_104` (169 files) reproduces the table above and
          returns exit 1 on the 7-day window. Note for callers: the return code
          must not be swallowed by a pipe — `... | tail` reports tail's status,
          which cost a real push earlier in this programme.

NEXT:     Wire into the daily scan alongside the run-surface drift check, and
          file the durable-persistence half against renquant-pipeline so the
          reconstruction can eventually be retired.

FIX (codex CHANGES_REQUESTED, 2026-07-30, addressed by claude):
          P1 — `scan()` counted ANY line containing a check name as a firing
          (`if check in line`), so a non-event mention (e.g. "checks
          registered: single_gate_funnel_kill, ...") would raise a false
          alert; codex reproduced this on the PR head. Fixed by matching
          only the exact line `task_funnel_integrity.py::FunnelIntegrityTask`
          emits — `FunnelIntegrityAlert: STRUCTURAL_BLOCK ... fired=[...]`
          — and `ast.literal_eval`-ing the `fired=[...]` payload instead of
          scanning free text.
          P2 — the unknown-check fail-open path only recognized tokens
          ending in five hardcoded suffixes, so a new reason like
          `fired=['new_refusal']` was silently missed (codex reproduced:
          tool returned OK with zero untracked warnings). Fixed by reading
          every name directly out of the structured `fired=[...]` list —
          anything not in `KNOWN_CHECKS` is now UNTRACKED unconditionally,
          no suffix heuristic.
          P2 — added `tests/test_refusal_telemetry.py` (16 cases): known-
          event parsing, unknown-event parsing (with and without the old
          hardcoded suffixes), bare-mention non-firing (codex's exact
          repro), date filtering, malformed/undated files, and alert-window
          exit codes (0/1/2).
  EVIDENCE: artifact: `ops/refusal_telemetry.py`, re-run against the same
            live `logs/daily_104` directory (169 files), READ-ONLY.
            `[VERIFIED — this session, post-fix]`: counts are UNCHANGED —
            wash_sale_mass_block 13/12/8, single_gate_funnel_kill 6/6/6,
            fail_close_event 6/6/6, universe_admission_collapse 1/1/1,
            threshold_scale_mismatch 1/1/1, zero_priced_candidates 0/0/0 —
            confirming the current production log corpus had zero false
            positives under the old substring match; the fix hardens
            against a class of bug that hadn't yet fired here, not one
            that inflated the existing numbers.
    prod or exp:    Read-only. Opens log files; writes nothing.
    existing data:  Same 169 files as the original measurement.
    best-known?:    Yes — parses the exact structured emitted-event grammar
                     instead of substring scanning.
    scope:          `renquant-orchestrator` ops + this doc + new test file.
                     No pipeline change, no pin, no config.
  tests run: `pytest tests/test_refusal_telemetry.py -v` — 16 passed.
