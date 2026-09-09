# A promotion that leaves the pin behind is not a promotion   (PR #TBD)

STATUS:    design for review — no code. `doc/design/2026-09-09-promotion-emits-the-pin-delta.md`.
WHAT:      The recurrence guard for the 2026-09-04 zero-buy incident, stated as
           a change to what "promoted" MEANS: a promotion that changes served
           bytes is not complete while any config pin still names the old bytes.
           D1 the promotion computes a `pin_delta` (`{config, field, pinned,
           required}` per carrier); D2 the delta lands IN the receipt, so the
           record of what was promoted carries what the promotion still owes;
           D3 a non-empty delta reports `PROMOTED_PIN_PENDING` and pages with the
           exact `config → field → required` lines instead of plain success;
           D4 no second digest implementation — call the existing comparator;
           D5 the promotion NEVER writes the config (that is a LONG row-2 write
           and needs its own authority row — row 2g is exactly that). Seams,
           five acceptance criteria, three rejected alternatives and one open
           question for the reviewer are in the design.
WHY/DIR:   The A4-T1 promotion reported `PROMOTED` and exited 0 on 09-03 09:09,
           and the buy path was fail-closed from that moment: the served config
           pins `components[0]` by content digest across seven carriers, the
           promotion swapped the bytes, and no step in either promote path moves
           the pin. It surfaced 21h later as `panel_scorer_load_failed` at dawn
           preflight — by the loader, not by any gate. Direction: G-B/G-D — a
           chain that reports success while leaving the system unservable is the
           gate lying, and the fix belongs at promotion time, not in one more
           downstream alarm.
EVIDENCE:  artifact:      `RenQuant/logs/rq104/dawn_funnel_preflight_2026-09-04.log:227-228` — `content_sha256 MISMATCH pinned='sha256:6461b827ab2339a8' observed=sha256:f1b1c1322e3b66f7… → panel_scorer_load_failed`, 6 buy candidates cleared [VERIFIED — read 2026-09-04]
           prod or exp:   design only — this PR adds two documents and changes no code, no gate, no artifact and no schedule
           existing data: the comparator ALREADY EXISTS and is correct — `RenQuant/scripts/check_config_artifact_paths.py:33-41` fails on a config-pinned `expected_content_sha256` mismatch. It cannot fire on a promotion for three independent reasons, each sufficient alone [all VERIFIED — `.github/workflows/config-artifact-path-gate.yml`, read 2026-09-09]: (1) wrong trigger — the step is guarded `if: steps.changes.outputs.lock_changed == 'true'` (:128) and a promotion does not touch `subrepos.lock.json`; (2) wrong bytes — it runs `--data-root .` against the CI checkout (:138-142), comparing the committed artifact to the committed pin, both old and mutually consistent, while the bytes that moved are on the serving machine; (3) after RenQuant#642 untracks the live-mutated pair the committed copy is gone and CI cannot check this pin on ANY trigger, which makes the serving machine the only place the comparison remains possible. Nothing else closes it: `weekly_wf_promote.sh:121` already resolves the component artifact paths out of the served config but the string `expected_content_sha256` does not appear in that file at all [VERIFIED — grep 2026-09-09]; `a4t1_governance.py:263-264` returns `PROMOTED` with no pin step [VERIFIED]; `scorer_identity_monitor.py:481-494` reads the field only out of promotion receipts to explain lane transitions, never comparing a pin to the bytes the config points at today [VERIFIED]
           best-known?:   n/a — governance design, no model claim. It does not extend, shorten or judge any window and promotes nothing
           scope:         "this adds a design document and its progress doc; it changes no code, no schedule and no config, and it does not authorise the row-2g pin write it describes"
NEXT:      review the open question first — whether `PROMOTED_PIN_PENDING` should
           exit non-zero. Non-zero is the honest signal, but the A4-T1 exception
           burns its ledger marker on consumption, so a failure-shaped exit after
           the marker is written invites a retry against an already-consumed
           exception; the design's recommendation is exit 0 + the distinct status
           + a priority-5 page, and it asks for a reviewer's call. Implementation
           is a separate PR per AC1-AC5 and does NOT depend on row 2g landing —
           the delta is computed and reported whatever the pin currently says.
           Related in flight: LONG row 2g (orch#1115) + s104#107 apply the ONE
           pin move this incident already requires; RenQuant#642 is what makes
           the CI-side check terminal.
