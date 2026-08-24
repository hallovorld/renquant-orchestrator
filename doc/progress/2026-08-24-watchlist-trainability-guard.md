# A ticker the operator asked for was inert for five days, wearing a normal warning

STATUS:   delivered. One read-only check + its tests. No production path
          written, no config changed, nothing deployed, no job wired — see
          NEXT for why the wiring is deliberately not in this PR.

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

NEXT:     Not done here, and each is someone's decision rather than a follow-up
          commit:
          1. **The three names themselves.** RKLB is 1,332 rows against a
             1,332-vs-1,344 empirical cohort floor — close, which is not the
             same as eligible. CRWV (293 rows) and SPCX (48) are far short.
             Whether a short-history ticker fails loudly or silently trains a
             bad model is NOT measured and must not be assumed.
          2. **Wiring it to a job.** The check is written to be scheduled, but
             adding a launchd entry is a run-surface change; it should land
             with an owner rather than by my hand.
