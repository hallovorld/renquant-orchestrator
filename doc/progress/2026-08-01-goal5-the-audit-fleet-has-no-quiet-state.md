# GOAL-5 — the audit fleet reports 10 of 10 every run, so a new finding cannot stand out

**Date:** 2026-08-01 · `renquant-orchestrator`

## Measured on current `main`

```
ops-audit: 10 detector(s) — ok=0 findings=10 unusable=0 crash=0 timeout=0 missing=0
```

Every member fires, every run `[本次实测 2026-08-01]`. And:

- `ops_audit.py` has **no ack / known / suppress / baseline concept of any kind** —
  grepped, and the only `ack` in the file is the *name* of the `ack-ledger` member.
- **`com.renquant.ops-audit`'s plist is not installed**, so the aggregator has never run on
  schedule (it is one of the 20 `ops/` files orch#715 measured as absent from the machine).

**A fleet that reports 10 of 10 forever is indistinguishable from one that always fires.**
A genuinely new finding cannot stand out against it — and adding an 11th detector makes the
report worse, not better. That is the honest counterweight to a night spent adding
detectors, several of them mine.

## What this adds

A disposition layer so a run can be **quiet**: each finding is fingerprinted, a committed
ledger may ack a fingerprint with a reason and an expiry, and an acked finding reports as
**INFO**. **Nothing is suppressed silently** — an acked finding is still printed, with its
reason. The tool **never writes the ledger**; acking is a human decision and a reviewed
diff, asserted by a test over the source.

## The fingerprint is the whole problem, and both failure modes are real

| choice | failure |
|---|---|
| fingerprint the **raw message** | every ack dies the moment a count ticks (`"has not acted on 4 runs"` → `5`) — the ledger is write-only |
| **normalise the digits away** | `4` and `40` fingerprint identically; an escalation is silently covered |

So digits are normalised **and recorded**. A finding whose magnitudes moved reports
**`ACKED_BUT_CHANGED`**, never INFO: *an ack covers a situation, not a magnitude.* Measured
directly:

```
same fingerprint when the count ticks 4 -> 40 : True
but numbers differ                            : ['4'] -> ['40']   -> ACKED_BUT_CHANGED
different job -> different fingerprint         : True
```

Timestamps and `/Users/<name>` paths are normalised for the fingerprint too — both drift
without the situation changing — while the **recorded text stays verbatim**.

`ack_expiry` is **imported** from the degradation sentinel, never re-implemented; a test
asserts no local `def ack_expiry` exists.

## Not claimed

That any current finding *should* be acked — the ledger ships **empty**, so today's run is
unchanged and all 10 still report as NEW. That this makes the fleet correct; it makes it
*readable*, which is a precondition. That the aggregator now runs: installing its plist is
a machine landing and the operator's call.

## Tests

13, including both traps as executable checks and the "never writes the ledger" assertion.
Suite: **5300 passed, 2 skipped**.

## Wiring the layer into the aggregator (codex review, 2026-08-01)

> *"it does not modify `ops/ops_audit.py` … the new ledger is dead code."*

Correct, and it is the failure this repo has a rule against — a disposition layer that
nothing calls quiets nothing. `ops_audit.audit()` now dispositions at the per-finding
counting boundary:

* only `STATUS_FINDINGS` rows are eligible; an ACKED-and-unchanged one becomes the new
  `STATUS_INFO` and stops counting toward `EXIT_FINDINGS`, so a fully acked fleet
  actually exits **0**;
* `NEW`, `ACKED_BUT_CHANGED` and `ACK_EXPIRED` all stay findings;
* **crash / timeout / missing / unusable are never dispositioned at all.** An ack that
  could reach them would let a broken detector read as an acknowledged one — the
  crash-vs-alarm confusion this aggregator exists to prevent, re-entered through the
  quieting layer. A test asserts the ack is ignored for both a traceback and an
  out-of-contract exit 2.

The ledger (`ops/ops_audit_acks.json`) is **absent on purpose**. With no ledger every
finding is NEW and the aggregator behaves exactly as before; acking stays a human
decision and a reviewed diff, and nothing here ever writes it (a test compares the
file's bytes before and after a run).

Five end-to-end tests through `audit()` itself, not the classifier in isolation:
the four dispositions in one report, an all-acked fleet exiting 0, the harness
statuses being unquietable, and a missing-or-malformed ledger leaving everything loud.

One thing the tests taught me: `acked_at` is **mandatory**. `ack_expiry` returns `None`
— treated as already expired — when it is missing, however distant `expires_at` is. My
first ledger fixture omitted it and the "quiet" cases came back `ACK_EXPIRED`; the code
was right and the fixture was wrong. Noted in the test so the next reader does not
repeat it.

Suite: **5304 passed, 2 skipped** [本次实测].
