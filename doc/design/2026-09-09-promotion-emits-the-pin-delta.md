# Promotion emits the pin delta

**Status:** design, for review. No code in this PR.
**Direction:** G-B (honest gates) / G-D (ops truth).
**Origin:** the 2026-09-04 zero-buy incident; memory
`promotion-never-moves-the-served-config-pin`, LONG row 2g (orch#1115) +
renquant-strategy-104#107.

## The defect in one sentence

A promotion replaces the served panel bytes; the served config pins those bytes
by content digest; **no step in the promote chain moves the pin**; and the one
gate that compares pin against bytes runs only in CI, only when the subrepo lock
changes, and only against *committed* bytes — so a promotion reports `PROMOTED`
and exits 0 while leaving the buy path fail-closed.

## What happened

The A4-T1 promotion ran 2026-09-03 09:09 PDT and reported `PROMOTED`. The next
funnel probe to reach the loader — dawn preflight 2026-09-04 06:06 — said:

```
LoadScorerTask: failed to load blend artifact … blend component[0]
content_sha256 MISMATCH … pinned='sha256:6461b827ab2339a8'
observed=sha256:f1b1c1322e3b66f7…   → panel_scorer_load_failed
```

Six buy candidates were cleared and the buy path fail-closed
[VERIFIED — `RenQuant/logs/rq104/dawn_funnel_preflight_2026-09-04.log:227-228`,
read 2026-09-04].

Since the 2026-08-04 z-blend override the served config pins the blend's
`components[0]` by content digest (`expected_content_sha256`) across **seven
carriers**: active, golden, and five `shadow_blend*` lanes
[VERIFIED — renquant-strategy-104#107]. Between 08-04 and 09-03 no promotion
happened, so the gap was latent; the A4-T1 promotion was the first one to
exercise it.

## Why the existing comparator cannot catch this

The comparison already exists and is well built.
`RenQuant/scripts/check_config_artifact_paths.py` design point 3 states that when
a profile entry carries a config-pinned `expected_content_sha256`, **a mismatch
FAILS** [VERIFIED — `check_config_artifact_paths.py:33-41`]. It is not missing
and it does not need a twin.

It cannot fire on this event for three independent reasons, each sufficient on
its own [all VERIFIED — `.github/workflows/config-artifact-path-gate.yml`, read
2026-09-09]:

1. **Wrong trigger.** The gate step is guarded by
   `if: steps.changes.outputs.lock_changed == 'true'` (line 128). A promotion
   changes artifact bytes; it does not touch `subrepos.lock.json`. The gate does
   not run at all.
2. **Wrong bytes.** It runs `--strategy-dir backtesting/renquant_104 --data-root .`
   against the CI checkout (lines 138-142). Even on a pin advance it compares the
   *committed* artifact against the *committed* pin — both old, both mutually
   consistent. The bytes that moved live on the serving machine and are never
   presented to it.
3. **Soon, no bytes at all.** RenQuant#642 untracks the live-mutated served pair.
   After it lands the committed copy is gone, and CI cannot check this pin on any
   trigger. The serving machine becomes the *only* place the comparison is
   possible.

This is the programme's recurring shape — a check that passes forever because its
subject is not the thing that moves (memory `guards-that-validate-the-wrong-object`).
The gate is right; it is pointed at the wrong object.

Nothing else closes the gap. `weekly_wf_promote.sh` already resolves the
component artifact paths out of the served config
[VERIFIED — `weekly_wf_promote.sh:121`] but never reads the
`expected_content_sha256` sitting beside them — the string does not appear in
that file at all [VERIFIED — grep, 2026-09-09]. `a4t1_governance._promote`
returns `{"status": "PROMOTED", …}` with no pin step
[VERIFIED — `src/renquant_orchestrator/a4t1_governance.py:263-264`]. And
`scorer_identity_monitor` reads `expected_content_sha256` only out of promotion
*receipts*, to explain lane transitions — it never compares a pin to the bytes
the config points at today [VERIFIED — `scorer_identity_monitor.py:481-494`].

## What `promoted` should mean

> A promotion that changes served bytes is **not complete** while any config pin
> still names the old bytes.

The current chain's definition ends at "the new artifact is stamped and the
ledger marker is written". That is the definition that let a successful
promotion produce an unservable system.

## Design

**D1 — the promotion computes the delta.** At the point where the chain already
holds both the new artifact and the served config, it resolves every carrier's
`expected_content_sha256` and compares it to the new bytes. Output is a
`pin_delta`: a list of `{config, field, pinned, required}` entries, empty when
the promotion needs no pin move.

**D2 — the delta is part of the receipt, not a side effect.** `pin_delta` goes
into the promotion receipt next to `proof` and `verdict`, so the record of what
was promoted carries the record of what the promotion still owes. A receipt with
a non-empty delta is evidence of an incomplete promotion for as long as it exists.

**D3 — the exit status stops lying.** A promotion with a non-empty delta reports
`PROMOTED_PIN_PENDING`, not `PROMOTED`, and pages with the exact
`config → field → required` lines. It must not report plain success. Whether that
status should also be a non-zero exit is the one open question below.

**D4 — no second implementation of the digest.** The delta is computed by calling
the existing comparator with the serving tree as its subject, not by re-deriving
content digests in the orchestrator. The pinned pipeline's resolver stays the
single source (memory `respect-pipeline-boundaries`,
`pipeline-has-twin-task-implementations`).

**D5 — the promotion never writes the config.** Moving a served-config pin is a
production-config write under LONG row 2 and needs its own authority row (this is
exactly what row 2g is). The promotion's job is to make the required change
**known and unmissable**, never to apply it. A chain that silently edited the
served config would be a worse defect than the one being fixed.

## Seams

| seam | file | what changes |
|---|---|---|
| A4-T1 path | `src/renquant_orchestrator/a4t1_governance.py` (`_promote`, ~176-264) | compute delta before returning; add `pin_delta` to the record and to the returned dict; status per D3 |
| weekly path | `RenQuant/scripts/weekly_wf_promote.sh` (~121, and the Step-5 replace dance) | same delta after the incoming/replace, from the config it already resolved |
| comparator | `RenQuant/scripts/check_config_artifact_paths.py` | none expected — it is called, not modified. If it needs a `--json` verdict surface, that is the whole of its change |
| gate workflow | `.github/workflows/config-artifact-path-gate.yml` | out of scope here; note in the doc that after #642 its committed-bytes subject is gone |

## Acceptance criteria

- **AC1** Replaying the 2026-09-03 A4-T1 promotion against a fixture whose config
  pins `6461b827ab2339a8` while the new bytes hash to `f1b1c1322e3b66f7`
  produces a `pin_delta` naming all seven carriers, and the status is
  `PROMOTED_PIN_PENDING`.
- **AC2** The same replay with a config already pinning the new digest produces
  an empty delta and plain `PROMOTED` — the alarm is silent when the promotion is
  complete.
- **AC3** An unreadable config or an unresolvable component is reported, never
  treated as an empty delta. Fail closed: "I could not check" is not "nothing to do".
- **AC4** No promotion path writes a config file. Asserted behaviourally against
  the serving tree's config mtimes, not by reading the source
  (memory `source-regex-cannot-see-runtime-writes`).
- **AC5** The delta is computed by invoking the existing comparator; no second
  content-digest implementation appears in this repo.

## Open question for review

**Should `PROMOTED_PIN_PENDING` exit non-zero?** Non-zero is the honest signal and
the wrapper's callers already branch on it — but the A4-T1 exception is
single-use and burns its ledger marker on consumption, so an exit code that reads
as failure after the marker is written risks a retry against an already-consumed
exception. The safer shape is probably: exit 0 (the promotion did happen and must
not be retried), status `PROMOTED_PIN_PENDING`, and a priority-5 page. Requesting
a reviewer's call on this specifically.

## Alternatives considered

- **A2 — make the primary leg ledger-served, like the momentum leg.** Removes the
  content pin as a separate object that can drift, and is the structurally better
  end state. Much larger, spans three repos, and does not help the served config
  that exists today. Recommend as a follow-on, not instead.
- **A3 — a daily comparator on the serving machine.** Cheap and it would have
  caught this by the next morning. But the dawn preflight loader already catches
  it by the next morning — that is how 09-04 was found. It would add a second
  alarm on the same latency, not a new capability. The gap worth closing is
  between a promotion reporting success and the next probe that reaches the
  loader — ~21h on this occurrence (promotion 09-03 09:09 → dawn preflight 09-04
  06:06) [VERIFIED], unbounded in general, since a probe that aborts earlier in
  the funnel never reaches the loader at all. Only D1-D3 close that.
- **A4 — have the promotion write the pin itself.** Rejected under D5.
