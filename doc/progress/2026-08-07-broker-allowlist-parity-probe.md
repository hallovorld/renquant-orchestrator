# 2026-08-07 — Compare the allow-lists programmatically, because grepping them is how I got it wrong

STATUS:   READY FOR REVIEW. 8 new tests; ops-audit suite 49 passed
          `[VERIFIED — python3 -m pytest tests/test_ops_audit.py
          tests/test_broker_allowlist_parity.py -q]`. The aggregator now runs
          15 detectors and the new one reports a live finding
          `[VERIFIED — python3 ops/ops_audit.py]`.

WHAT:     `ops/renquant104/broker_allowlist_parity_probe.py`, registered in
          `ops_audit.py` as `broker-allowlist-parity`. It IMPORTS both copies of
          `ALLOWED_BROKERS` and compares the objects.

WHY/DIR:  `runs_db_path()` fail-closes on an unknown `broker_name`. The umbrella
          copy of that allow-list is a strict SUBSET of the pinned one
          `[VERIFIED — 2026-08-07, both modules imported]`:

```
pinned    15 tags        umbrella  10 tags
missing from umbrella:
  alpaca_shadow_a
  alpaca_shadow_b
  alpaca_shadow_blend_mom_fast     <- live fleet lane
  alpaca_shadow_blend_rb_fast      <- live fleet lane
  alpaca_shadow_blend_rb_mom       <- live fleet lane
only in umbrella: none
```

          It bites only under `RQ_DAILY_RUNNER=umbrella`, which
          `scripts/daily_104.sh:135-139` documents as the escape hatch for a
          missing pinned subrepo — so it fails **in exactly the degraded moment
          the fallback exists for**, and presents as
          `ValueError: Unknown broker_name`: a lane crash, not a stale list.

## THE MEASUREMENT METHOD IS THE POINT

I first "measured" this by grepping each file for `alpaca[a-z_-]*` and reported
in orch#893 that the two PINNED copies ALSO diverged, 15 vs 3. **They do not.**
Imported, both are 15 and identical, and
`renquant-pipeline/tests/test_shadow_arm_broker_tags.py:37` already asserts that
equality. Counting string literals in a file is not reading the constant a module
exports; the kernel copy simply does not spell every tag as a literal.

That was the seventh instance in one session of measuring a proxy and reporting
it as the object. So this probe imports and compares objects and **never reads
source text** — and `test_the_probe_never_reads_source_text` fails if anyone adds
`open(`, `read_text(`, `re.findall` or `readlines` to its body. A text-based
version of this probe would reproduce the very error it exists to catch.

EVIDENCE:
artifact:      `ops/renquant104/broker_allowlist_parity_probe.py`,
               `tests/test_broker_allowlist_parity.py`, `ops/ops_audit.py`,
               `tests/test_ops_audit.py`
prod or exp:   **neither** — a read-only detector. No job, config, or live
               surface changes; it imports two modules and diffs two sets.
existing data: the two `state_paths` modules, imported this session.
best-known?:   yes for this pair. Whether other fail-closed allow-lists are
               similarly forked is NOT checked — see NOT ESTABLISHED.
scope:         one probe + its registration + the provenance-pin update.

Exit contract, declared narrowly on purpose: `1` = the umbrella list is missing
tags; `2` = a copy could not be imported. Only `1` is registered as a finding
exit, so an unimportable copy lands on HARNESS rather than reading as "the lists
agree" — unreadability is this detector's own defect class, the same reasoning
`model-load-coverage` uses.

`test_the_cited_contract_is_the_one_in_force` is a provenance pin and was
updated in the SAME change, as its docstring requires.

NEXT:     Sync the umbrella copy, or make the umbrella fallback refuse loudly
          when a configured lane's broker tag is not in its list. Which one is
          right depends on whether that copy is deliberately frozen — unknown,
          and worth asking before editing an umbrella file. The detector now
          keeps the drift visible either way, which is what was missing.

## NOT ESTABLISHED

1. **Whether the umbrella copy is deliberately frozen.** If it is, syncing is
   wrong and the fallback should refuse loudly instead.
2. **Whether other fail-closed allow-lists are forked the same way.** Only this
   one was compared.
3. **That the live book is affected.** It is not, today: `daily_104.sh` defaults
   to `multirepo`, which imports the pinned copy, and all five fleet lanes wrote
   their DBs on 2026-08-06. The exposure is the fallback path.

## REVERT

Delete `ops/renquant104/broker_allowlist_parity_probe.py` and
`tests/test_broker_allowlist_parity.py`, drop the `broker-allowlist-parity` row
from `ops_audit.MEMBERS` and from the provenance pin in
`tests/test_ops_audit.py`. No other file changes.
