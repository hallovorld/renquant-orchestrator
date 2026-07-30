# Progress: GOAL-5 AC5 — the refusals fire, nothing aggregates them

STATUS:   delivered. Round-2 fix (codex P1): an unknown or undated
          structural event no longer reads as a clean scan.

          THE DEFECT. `untracked_candidates` was printed in the report, but
          `recent` -- the only thing the exit code consulted -- was built
          solely from KNOWN_CHECKS. So a dated `fired=['new_refusal']` printed
          an UNTRACKED note and then exited 0 with "OK: no refusal firing":
          a silent failure on exactly the case this tool's own docstring says
          it must not miss. Undated events had the same shape --
          `if h["date"] and ...` dropped them from `recent`, so they too could
          reach 0.

          THE FIX. `scan()` records untracked firings WITH date/file/line
          instead of only counting names (a bare count cannot be windowed or
          reported per occurrence). Exit policy, most severe first:
            2 = the scan CANNOT be certified clean -- an untracked refusal
                name, or an event whose time cannot be established;
            1 = a known refusal genuinely fired inside the window;
            0 = clean.
          `cannot_certify` is evaluated BEFORE `recent`, so an unknown reason
          is never masked by an ordinary in-window alert. The undated policy
          is now explicit, as the review asked: undated events FAIL with 2
          rather than being counted in the aggregate and silently excluded
          from the window.

          Applies to BOTH output modes. The `--json` path returns early, so it
          needed the policy wired separately -- otherwise a machine caller
          would have received 0 on an untracked reason while the text mode
          failed, which is the worse half of the same bug.

          7 new tests (25 total): unknown name -> 2, unknown event carries
          date+file, undated known firing -> 2, clean -> 0, dated in-window ->
          1 unchanged, severity ordering when both are present, and json mode
          honouring the same policy while still emitting pure JSON. Verified
          load-bearing -- with the `cannot_certify` check disabled, 3 fail.

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
          `[VERIFIED — python3 ops/refusal_telemetry.py --log-dir
          /Users/renhao/git/github/RenQuant/logs/daily_104 --today 2026-07-30]`
          on the real directory, 169 log files:
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
          And `data/runs.alpaca.db` (the live 131 MB DB, not the empty
          root-level stub of the same name) holds **0 rows** naming any of
          the six checks in either table that could hold them
          `[VERIFIED — sqlite3 /Users/renhao/git/github/RenQuant/data/runs.alpaca.db
          "SELECT COUNT(*) FROM gate_verdicts WHERE gate LIKE '%<check>%' OR
          reason LIKE '%<check>%' OR inputs_json LIKE '%<check>%'" and the
          same query against alert_incidents(audit, scope, cause_hash), run
          for all six check names, 2026-07-30]`.
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
            `[VERIFIED — python3 ops/refusal_telemetry.py --log-dir
            /Users/renhao/git/github/RenQuant/logs/daily_104 --today
            2026-07-30, re-run on HEAD]`: counts are UNCHANGED —
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
  tests run: `[VERIFIED — pytest tests/test_refusal_telemetry.py -v, re-run
             on HEAD]` — 25 passed (16 at the time of this fix; the file has
             grown to 25 across later fixes in this same PR).

FIX (codex CHANGES_REQUESTED, 2026-07-30, addressed by claude):
          MED — `--json` was not actually machine-readable: `main()` always
          printed the human summary/CAVEAT/ALERT-or-OK lines to stdout
          around the JSON blob, so a caller piping the output into a JSON
          parser got `JSONDecodeError`; codex reproduced this against the
          real log directory. Fixed by branching in `main()`: when
          `a.json` is set, stdout carries ONLY the `json.dumps(...)` blob
          and nothing else; the summary/per-check/CAVEAT/ALERT-or-OK prose
          now prints only in the default (non-JSON) path. Exit-code logic
          (0 clean / 1 alert) is unchanged and shared by both paths.
  EVIDENCE: artifact: `ops/refusal_telemetry.py`, re-run against the same
            live `logs/daily_104` directory (169 files), READ-ONLY.
            `[VERIFIED — python3 ops/refusal_telemetry.py --log-dir
            /Users/renhao/git/github/RenQuant/logs/daily_104 --today
            2026-07-30 --since 2100-01-01 --json | python3 -c "import
            json,sys; json.load(sys.stdin)", re-run on HEAD]`: codex's exact
            repro now parses cleanly (previously raised `JSONDecodeError`).
            Non-JSON mode re-run confirms counts UNCHANGED: wash_sale_mass_block
            13/12/8, single_gate_funnel_kill 6/6/6, fail_close_event 6/6/6,
            universe_admission_collapse 1/1/1, threshold_scale_mismatch 1/1/1,
            zero_priced_candidates 0/0/0.
    prod or exp:    Read-only. Opens log files; writes nothing.
    existing data:  Same 169 files as the original measurement.
    best-known?:    Yes — `--json` stdout is now pure JSON as advertised.
    scope:          `renquant-orchestrator` ops + this doc + 2 new tests.
                     No pipeline change, no pin, no config.
  tests run: `pytest tests/test_refusal_telemetry.py -v` — 18 passed (2 new:
             `TestJsonModeIsPureJson::test_json_stdout_parses_with_a_firing`,
             `test_json_stdout_parses_when_clean`).
