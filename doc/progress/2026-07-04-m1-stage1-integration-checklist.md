# M1 Stage-1 integration checklist

STATUS: design spec delivered.
WHAT: `doc/design/2026-07-04-m1-stage1-integration-checklist.md` — the M1
      integration spec: cross-repo dependency map, 7 prerequisites, 5-session
      acceptance criteria (with replay audit), risk register, activation sequence.
WHY: all 3 code slices delivered (orchestrator #268/#303/#335, execution #20,
     pipeline #163) but never wired together. M1 is the integration milestone
     that proves the slices compose into a working shadow loop.
NEXT: operator activates per §5 sequence (landing action — ask-first);
      5 sessions → replay audit → M1 AC → unlocks M2 (frozen canary).

## Round 2 (Codex review — contract drift)

Codex found §2.4's documented strategy-config keys didn't match
`load_intraday_config()`'s real contract in `intraday_session_scheduler.py`:
the doc had invented `tick_cadence_seconds`/`entry_cutoff_before_close_minutes`,
while the real keys are `tick_seconds`/`entry_open_delay_seconds`/
`entry_close_cutoff_seconds` — a config drift that would leave an operator's
settings silently ignored (the loader falls back to defaults on an unknown/
malformed key rather than raising). Fixed: §2.4 now uses the real key names,
their real defaults (720s/300s/1800s), and their real semantics read directly
from the loader's code, plus a note on the silent-fallback failure mode.

Also fixed §2.6/§5's deprecated `launchctl load` verb — replaced with the
current-macOS `launchctl bootstrap "gui/$UID_NUM" <plist>` convention already
established in `ops/renquant105/README.md` and enforced by
`tests/test_rq105_collector_scheduling.py::test_readme_documents_mkdir_before_load_and_current_launchctl_verbs`.

Generalized §2.1's `make test` row from an exact, rot-prone count ("currently
2255") to "All pass" — the exact number added no information the CI gate
itself doesn't already enforce, and would drift out of date immediately.
