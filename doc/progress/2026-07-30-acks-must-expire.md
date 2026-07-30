# An ack suppressed forever; the ledger already held the expiry dates   (PR pending)

STATUS:    delivered
WHAT:      `check_launchd_exits()` did `if ack:` — unconditional, permanent
           suppression — while `clears_when` sat as prose no code read. Acks now
           expire: an expired one stops suppressing and goes LOUD with its own reason
           and `clears_when` quoted.
WHY/DIR:   GOAL-1, issue #622. CLAUDE.md's CONTAINMENT PROTOCOL requires every
           suppression to carry "an explicit expiry or restore condition" and says the
           returning alarm is **the DESIGNED reminder to lift or legitimize it**. The
           ledger did the opposite — it silenced permanently — which is the
           guard-that-passes-forever shape inside the mechanism whose whole job is
           deciding what gets surfaced.
EVIDENCE:  §1.
NEXT:      The four expired acks below need dispositioning: fix the job, or re-ack
           with a fresh date and a condition that has not already passed.

## §1 EVIDENCE

All ten acks in the committed ledger were written on **2026-07-17**, thirteen days ago
`[VERIFIED — ops/renquant104/sentinel_acks.json, acked_at on every row]`. Under the new
rule, on 2026-07-30:

| | count |
|---|---|
| acks that stop suppressing NOW | **4** |
| still valid | 6 |

`[VERIFIED — ack_expiry() over the committed ledger, this session]`

**Positive control against a hand measurement.** #622 counted **four** acks past their
date by hand. The mechanism reproduces exactly that four, independently — and it does
not reach the count via the age window. Each of the four is killed by **a date written
inside its own `clears_when`**:

| ack | clears_when contains | expired |
|---|---|---|
| `com.renquant.daily104` | `(2026-07-20)` | 10 days ago |
| `com.renquant.rq105-batch-scores-export` | `(2026-07-20)` | 10 days ago |
| `com.renquant.shadow-ab-daily` | `(2026-07-20)` | 10 days ago |
| `com.renquant.weekly-retrain-patchtst` | `(2026-07-20)` | 10 days ago |

**The expiry dates were already in the ledger. Nothing read them.** That is the whole
finding: this is not a missing policy, it is an unimplemented one.

### How the expiry is derived

The **earliest** of three signals, so a parsing mistake can only make an ack expire
*sooner* — noisy and safe — never later, which is silent and is the failure being
removed:

1. an explicit `expires_at` field, giving the containment protocol's "explicit expiry"
   a machine-readable home;
2. the earliest ISO date appearing anywhere in `clears_when`;
3. `acked_at + ACK_MAX_AGE_DAYS` (14).

A missing or unparseable `acked_at` yields **already expired**. Absence must not buy
permanent suppression — that is precisely how a guard ends up passing forever.

14 days is a **review window**, not an estimate of how long a fix takes: long enough for
a change to land through CODEOWNERS review, short enough that a forgotten ack resurfaces
within a normal cadence.

### Operational consequence, stated rather than buried

Merging this turns **4 INFO lines into 4 LOUD lines** on the next sentinel firing, and
2 more expire on 2026-07-31 as the age window bites. That is the intended behaviour —
those conditions passed ten days ago — but it is a real change in what the sentinel says
tomorrow, so it is stated here with the number rather than discovered by whoever reads
the alert. The alarm text quotes each ack's original reason and `clears_when`, so a
reader can choose between fixing the job and re-acking without opening the ledger.

## §2 Tests

18 new. The load-bearing ones:

- `test_the_committed_ledger_has_exactly_four_expired_acks_on_2026_07_30` — the positive
  control above, on a fixed date so it does not rot, and it asserts each of the four
  expires **by its own `clears_when`** rather than by the age window. If that stopped
  being true the mechanism would be reaching the right count for the wrong reason.
- `test_the_EARLIEST_signal_wins_so_a_misparse_can_only_expire_sooner` — pins the safe
  direction.
- `test_a_missing_acked_at_means_ALREADY_EXPIRED` and six unparseable variants.
- `test_a_valid_ack_still_suppresses_and_shows_its_expiry` — the negative case, proving
  the new alarms come from expiry and not from acks being ignored wholesale.

## §3 Live-surface impact

No `program_args` change, so `program_args_sha256` in `ops/launchd_manifest.json` still
matches and this cannot cause manifest drift. **The ledger file itself is not edited** —
only the code that reads it — so this does not disposition anyone's ack on their behalf.

## §4 Suite

| tree | result |
|---|---|
| `origin/main` @ 7c6c14c1, separate worktree | 6 failed, 4523 passed, 5 skipped, 27 warnings in 123.88s (0:02:03) |
| this branch | 7 failed, 4540 passed, 5 skipped, 27 warnings in 121.52s (0:02:01) |

`[VERIFIED — python3 -m pytest -q in both worktrees, all sibling checkouts on PYTHONPATH]`
