# orch#799 blend-substitution — FEASIBILITY & POWER FINDING (not a preregistration)

STATUS: **NOT a preregistration; authorizes nothing.** An earlier revision was
titled and presented as FROZEN. It could not be: on independent units the paired
rule has power **0.17** at a win-rate of 0.65 (n_eff = 15 after removing the
60-day label overlap from a 21-day cadence), so the decisive rule cannot be
frozen at usable power today. Any future option-B implementation needs a NEW,
complete, independently reviewable prereg and inherits nothing here.

WHAT: records a measured feasibility result for the orch#799 option-B estimand,
and the defects found while attempting to preregister it. **It commits no
specification.** The option-B rule sketch that earlier revisions carried is
deleted (not fenced — fencing failed twice, with normative text surviving inside
the fence).

WHY/DIR: an attempt to freeze an option-B preregistration ran into a blocker that
is a property of the data, not of the drafting: a 21-day retrain cadence against
a 60-day forward label means the manifest's 43 rows are not 43 independent
trials. On a deterministic non-overlapping subsample n_eff = 15, giving a
one-sided exact sign test critical value k >= 12, alpha = 0.0176, and power
**0.17** at a true win-rate of 0.65. A gate may accept under-promotion, but it
may not present an independence calculation that does not hold as a valid
rejection threshold. So the honest output of the attempt is this finding, not a
preregistration.

EVIDENCE:
  artifact:      `doc/design/2026-08-12-orch799-blend-substitution-prereg.md`
                 (the feasibility finding + recorded defects) and this record. **No code, no specification.**
  prod or exp:   neither — a feasibility finding about a future production-gate rule.
                 It changes nothing today and authorizes no promotion; the gate
                 change it governs is separately operator-gated.
  existing data: yes — every quantity below was READ from the pinned system, not
                 chosen here, and none of them is frozen BY this document: the combine rule from
                 `renquant_pipeline/kernel/panel_pipeline/blend_scorer.py`; the
                 served blend's shape from `strategy_config.json` at
                 strategy-104 `e00d935`; and the gate's own bar from
                 `scripts/run_wf_gate.py` — placebo mode **`absolute`**
                 (`DEFAULT_PLACEBO_MODE`), whose authoritative bar is the
                 time-shift ceiling `max(0.005, 0.5×|aligned_real_ic|)` ALONE
                 `[VERIFIED — `run_wf_gate.py:276,500-520`, read 2026-08-12]`.
                 An earlier draft of this record also listed `margin +0.01` and
                 the real-IC floor as part of the bar; those feed the opt-in
                 `difference` verdict only, so listing them froze a hybrid rule
                 the gate never applies. Recorded as a defect in the finding,
                 not corrected into a spec. No run performed, no data generated.
  best-known?:   not applicable — this document selects no option and specifies
                 no rule. It records that the attempt to preregister option B
                 hit a data-level blocker (the 60-day label overlap on a 21-day
                 cadence) and stopped there. Whether option B remains the right
                 direction is for the future prereg to argue on its own
                 evidence; the only claim made here is the measured n_eff, α,
                 and power.
  scope:         "this is a feasibility finding about the orch#799
                 blend-substitution promote rule — NOT a prereg, nothing
                 implemented, specified, or authorized. What it establishes:
                 with a 21-day retrain cadence and a 60-day forward label, the
                 manifest's 43 rows yield n_eff = 15 independent units, giving
                 a one-sided exact sign test k >= 12, α = 0.0176, and power
                 0.17 at a win-rate of 0.65. That is the whole of the claim.
                 It makes no alpha claim, proposes no threshold, and does not
                 argue for or against implementing option B."

REMOVED FROM AN EARLIER DRAFT, deliberately: this record previously asserted
`exits 2`, `3 jobs stuck`, and `25/145 watchlist names` while its EVIDENCE line
said "no runtime claim". Those are operational measurements and this document
has no reproducible source for them, so they are gone rather than tagged. If
they are load-bearing for prioritization they belong in the document that
measures them, cited from there.

NEXT: nothing here authorizes anything, and no implementation is gated on this
PR's approval. A future option-B gate change requires a NEW, complete,
independently reviewable preregistration that inherits nothing from this
document — it must choose an inference unit that respects the 60-day overlap and
state its own alpha and power for a declared minimum effect. Two routes were
considered and NOT taken here, each needing its own prereg: block-aware paired
resampling (reintroduces block-length > h and rho1 assumptions) and prospective
accumulation (~60 days per additional independent unit). Separately, orch#976
carries the same class of defect and is being corrected on its own branch.
