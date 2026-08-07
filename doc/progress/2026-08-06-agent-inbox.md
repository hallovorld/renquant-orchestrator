# 2026-08-06 — Agent inbox: one read-only answer to "what is broken right now"

STATUS:   READY FOR REVIEW. 20 new tests for the inbox + 1 new test and a
          correction in the position-cap conformance suite. Read-only: never
          acks, writes, or mutates a job.

WHAT:     `ops/agent_inbox.py` unions three EXISTING alert sources into one
          agent-facing view — `alert_incidents` (unacked), `ops_audit --json`
          findings, and `launchctl` nonzero last-exits split into DESIGNED vs
          UNKNOWN. It invents no new signal.

WHY/DIR:  Operator directive 2026-08-06: *"出现的问题应该直接推送给你这个 agent
          这样你可以直接开始修"*. Today the path is job → ntfy → the operator's
          phone → relayed in chat, so every fault costs a human round-trip and
          anything unread is never worked.

          What that was hiding, found the first time this ran
          `[VERIFIED — 2026-08-06]`:

          * **17 unacked incidents**, oldest `first_seen` 2026-06-22, all
            `score_drift/panel`. Neither party had seen them.
          * The launchd alarm lists ~14 jobs "with nonzero last exit" and reads
            as fourteen failures. Most are jobs REPORTING: `EXIT_NOT_WIRED=4`,
            `EXIT_ALARM=8`, "drift found", "findings present". Conflating "I have
            something to report" with "I crashed" is the same defect class as a
            rotation counter reading `considered=0` on a run that considered one.

EVIDENCE:
artifact:      `ops/agent_inbox.py`, `tests/test_agent_inbox.py`,
               `tests/test_position_cap_conformance.py`
prod or exp:   **neither** — a read-only reporting tool. No scheduled job, no
               config, no live surface.
existing data: `runs.alpaca.db::alert_incidents`, `ops_audit --json`,
               `launchctl list`.
best-known?:   yes for aggregation. **No** for whether the 17 incidents are
               genuine — see the severity finding below, which this surfaced but
               does not fix.
scope:         one new read-only module + its tests.

`DESIGNED_EXIT_CODES` is a claim about files in other directories, so
`test_designed_exit_codes_are_still_true_of_their_sources` re-greps each cited
source and fails when a wrapper's contract moves. Asserted in the module,
**measured in the test**. An unlisted code is UNKNOWN by construction: a map
that failed open would restate the defect it exists to fix.

The ops-audit schema was MEASURED, not guessed. A first cut read `members` as the
result list; it is an `int`, and the module crashed — the same invented-key error
the inbox exists to surface. The real shape is `results: [{member, status,
exit_code, detail, disposition}]`, and a changed schema is now REPORTED rather
than swallowed as an empty list, because a broken aggregator must not look like
a clean system.

## A SEVERITY INVERSION THIS SURFACED — not fixed here

The 17 incidents carry a `state` column that is **anti-correlated** with the
severity embedded in their own `cause_hash` `[VERIFIED — 2026-08-06, all 17 rows
parsed]`:

```
psi 10.6  8.6  6.8  5.9  5.3  5.1   ->  state = WARN
psi  0.4  0.3  0.2  0.1             ->  state = CRITICAL
17 rows: 3 consistent, 14 inconsistent; the ordering is exactly inverted
```

Anything triaging by `state` works the lightest incidents first and stays silent
on the heaviest. PSI > 0.25 is conventionally a significant shift; 10.6 is 42x
that, labelled WARN. The writer is `renquant-pipeline/kernel/persistence.py:2999`.
Filed separately — the inbox reports both fields side by side so the
contradiction is visible rather than averaged away.

## A RECORD THIS CHANGE ALSO CORRECTS

Advancing the live pin to `max_position_pct=0.30` earlier today made
`test_the_LIVE_book_is_what_the_record_describes` fail: `scan()` judges every
historical buy against the cap in the CURRENTLY DEPLOYED config, so raising the
cap **retroactively un-breached** the two 2026-07-28 buys and the assertion
silently became "0 breaches".

A policy change is not a reason for a past breach to leave the record. The test
now evaluates against a pinned `CAP_IN_FORCE_2026_07_28 = 0.12`, and a second
test asserts the other half — under today's deployed cap those buys are within
policy. Both are true; neither replaces the other; the scan result already names
the cap it judged against, and that is now asserted too.

## NOT ESTABLISHED

1. **That the 17 incidents are real drift.** They are unacked, not verified. The
   inbox reports them; diagnosing PSI ~10.6 is separate work.
2. **That the DESIGNED map is complete.** Six jobs still exit nonzero with no
   documented meaning (`monthly-calibrator-refresh`, `retrain-panel104`,
   `rq104-risk-budget`, `rq104-scorer-identity`, `weekly-apy104`=2,
   `agent-pr-loop`). They surface as UNKNOWN — correctly, that IS the work.
3. **That this closes the operator's loop.** It gives the agent a place to look;
   nothing yet PUSHES to the agent. Wiring it into the loop's fixed opening
   check is the next step and needs no code.

NEXT:     Wire the inbox into the loop's fixed opening check so a fault reaches
          the agent without a human relay — that is the directive's actual ask
          and needs no code, only the loop prompt. Then, in priority order:
          (a) file the `state`-vs-`cause_hash` severity inversion against
          `renquant-pipeline/kernel/persistence.py:2999` — 14 of 17 rows are
          mislabelled and triage-by-state is inverted today;
          (b) document or fix the six jobs that exit nonzero with no stated
          meaning, which is what the UNKNOWN bucket exists to drive;
          (c) decide whether the 17 unacked incidents are real drift or a
          broken detector — the inbox reports them, it does not diagnose them.

## REVERT

Delete `ops/agent_inbox.py` and `tests/test_agent_inbox.py`; restore
`test_the_LIVE_book_is_what_the_record_describes` to its pre-change body and
drop `CAP_IN_FORCE_2026_07_28` plus
`test_the_DEPLOYED_cap_is_read_and_stated_not_assumed`. No other file changes.
