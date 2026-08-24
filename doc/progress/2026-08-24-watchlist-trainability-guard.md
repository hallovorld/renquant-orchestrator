# A ticker the operator asked for was inert for five days, wearing a normal warning

STATUS:   delivered. One read-only check, REGISTERED with ops_audit in the same
          PR, + its tests. No production path written, no config changed.

WHAT:     `ops/watchlist_trainability_check.py` enforces the invariant the
          design already implies: **served ∖ tournament ∖ declared == ∅**.
          Run against the live tree today it FAILS, naming CRWV, RKLB, SPCX.

WHY/DIR:  orch#1020. There are two watchlists and they drifted:

          | file | n |
          |---|---:|
          | `.subrepo_runtime/.../strategy_config.json` (the daily decision) | **145** |
          | `backtesting/renquant_104/strategy_config.json` (the tournament's universe) | **142** |

          Artifacts come from the tournament, so a ticker added to the served
          list alone is scored NEVER. CRWV was added on the operator's request
          on 2026-08-19 and has been silently inert every session since.

          The reason nobody saw it is the interesting part: it logs
          `no_artifact` — the *same* WARNING that SPY and seven sector ETFs log
          **by design**, because those are declared untrainable with a
          per-ticker reason. The design has two states, trained or declared;
          CRWV/RKLB/SPCX are a third that looks exactly like the second.

EVIDENCE:
  artifact:      ops/watchlist_trainability_check.py,
                 tests/test_watchlist_trainability_check.py.
  prod or exp:   neither — read-only. It parses two configs and one declaration
                 file and returns an exit code.
  existing data: [VERIFIED 2026-08-24] served=145, tournament=142, difference
                 exactly {CRWV, RKLB, SPCX}; all three plus SPY log
                 `no_artifact` in logs/daily_104/2026-08-21.log; the newest
                 declaration file (2026-08-23) holds 8 entries with reasons.
                 Running the check on the live tree: exit 1, naming the three.
  best-known?:   yes, because it refuses the third STATE rather than judging
                 trainability. Deciding whether CRWV *should* be trainable needs
                 a minimum-history threshold that, per #1020's own measurement,
                 is not coded anywhere — 1,344 rows is the empirical floor of
                 the current 142, not a declared requirement. A check that
                 guessed that number would be inventing policy inside a guard.
                 This one says only: add it to the universe, or declare it with
                 a reason. Both are reviewed acts; drifting into neither is not.
  scope:         one check + tests. It does not edit either watchlist, does not
                 write the declaration file, and is not yet wired to a job.

VERIFICATION:
  11 passed. Mutation-verified per property, because "the evidence is present"
  is not "the comparison happens" — this repo's recurring shape:
    make the guard report but never enforce (`offenders = []`)  -> 4 failed
    accept an EMPTY watchlist as a set to compare               -> 1 failed
    accept a BLANK reason as a declaration                      -> 1 failed
    restored                                                    -> 11 passed
  [VERIFIED 2026-08-24]

  Two properties worth calling out because they are the ones that usually rot:
   * **It can go GREEN.** Both documented remedies are tested — adding the
     ticker to the tournament universe, and declaring it with a reason. A check
     that cannot pass after the fix is a ratchet, not a check.
   * **Absence never reads as agreement.** A missing config, an empty
     watchlist, or a missing declaration file RAISES `InputMissing` (exit 2),
     because empty-minus-empty is empty and would otherwise pass on a tree the
     check never inspected. Exit 1 (violation) and exit 2 (unreadable input)
     are deliberately different codes.

## Review round 2 (codex) — three findings, all correct

1. **Nothing invoked it.** I had deferred the wiring, calling it a run-surface
   change that should land with an owner. That was wrong, and codex named why:
   an unwired script would have allowed the identical five-day silence it
   exists to end — which is `ops_audit`'s own founding finding (#723, "merged
   with no caller"), committed one more time by me. It is now a MEMBER, so it
   runs wherever the aggregator runs, and exit 1/2 keep their distinct meaning
   there: 1 is a finding, 2 lands UNUSABLE. `test_the_detector_is_REGISTERED_
   with_the_aggregator` asserts against `MEMBERS`, not against a docstring —
   a comment saying it is wired is exactly the claim that outlives the wiring.

2. **A stale declaration could authorise forever.** Selecting the newest
   filename binds nothing: if the weekly producer stops, an old file goes on
   silencing a newly served ticker indefinitely. The declaration is now BOUND
   to the run it describes via the sibling `*.expected_watchlist.json` the same
   weekly job writes — the universe that run actually used. If it differs from
   the tournament config now, the declaration is `InputMissing`
   (unverifiable), never authorisation. A 21-day freshness backstop
   (three missed weekly runs) covers the case where the binding still matches
   but nothing is refreshing the file, and the age is reported in the evidence.
   [VERIFIED 2026-08-24: the 08-23 sibling's universe is 142 and the tournament
   config's is 142, identical — so the binding passes on the live tree today.]

3. **`["   "]` slipped through.** A non-empty LIST that normalises to an empty
   SET passed the presence check and then compared as nothing. Emptiness is now
   decided AFTER normalisation, on both inputs, since the set is what the
   comparison uses.

  Mutation-verified per fix: unregistering the detector -> 2 failed; dropping
  the run-universe binding -> 1; dropping the freshness backstop -> 1;
  accepting a watchlist that normalises to nothing -> 3; restored -> 62 passed.

NEXT:     Not done here, and each is someone's decision rather than a follow-up
          commit:
          1. **The three names themselves.** RKLB is 1,332 rows against a
             1,332-vs-1,344 empirical cohort floor — close, which is not the
             same as eligible. CRWV (293 rows) and SPCX (48) are far short.
             Whether a short-history ticker fails loudly or silently trains a
             bad model is NOT measured and must not be assumed.
          2. ~~Wiring it to a job.~~ Done in review round 2 — registered with
             `ops_audit`, which is already scheduled and already reaches the
             operator and the agent inbox. No new launchd entry needed.
