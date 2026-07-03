# S-REL V4 — C3 verdict reconciliation: UNADJUDICATED governs, not MISS

STATUS:   RECONCILED (docs only — a reconciliation of recorded adjudications, NOT a
          recompute; the C3 numbers were recomputed twice under Codex review and are not
          in dispute). The governing memo
          (`doc/research/2026-07-02-c3-residual-momentum.md`) rules **UNADJUDICATED** —
          "substrate/provenance limitations, NOT a tested-and-failed MISS"; its §10
          explicitly withdraws the MISS ("This run casts NO formal vote (neither GO nor a
          design-rule-5 recorded MISS)"). The master plan's 2026-07-02 addendum recorded
          the opposite ("C3 = MISS (G106 now 2-of-3: C1/C2/C4; composite ≈0.35–0.45)").
          The memo governs: it is the evidence source of truth; the plan is a consumer.
WHAT:     Dated correction addendum appended to
          `doc/design/2026-07-02-unified-107-master-plan.md` (the §4 mechanism — dated
          addendum, stated reasons, never silent edits; the erroneous 07-02 delta line is
          marked in place, not rewritten). Corrections recorded: (1) C3 is OPEN
          (UNADJUDICATED-pending-clean-substrate) — the #230 §8.3 calculus returns to
          ≥2-of-4 candidates at individual P ≈ 0.4–0.5 each; (2) composite restored to the
          published **≈0.45–0.50** (P(≥2 of 4) = 0.52–0.69 raw independent at p=0.4–0.5,
          correlated-failure haircut → 0.45–0.50; the 07-02 line's 0.35–0.45 was the
          2-of-3 arithmetic — internally consistent, wrong premise); (3) second error
          removed: "2-of-3: C1/C2/C4" counted C1 as a voter, but C1 never votes (M-SIG
          §1.1/§2a/§3) — a true C3 MISS would have left 2-of-2 on C2/C4, harsher than
          recorded; (4) Bonferroni family unchanged on either reading ({C2,C3,C4}, k=3,
          frozen at spec time).
WHY/DIR:  G106's composition and its composite probability were being read off a verdict
          the evidence memo never issued. Disposition: C3's formal vote requires (a) a
          genuinely PIT rerun (PIT regime-label history + PIT universe/delisting — neither
          exists in the codebase per the memo's §6/§7 search; a materially larger
          data-engineering task) or (b) an explicit operator decision to accept the
          substrate under an amended protocol. V4 decision: the PIT rerun is NOT worth a
          dedicated near-term task (exploratory conditioned placebo-clean ≈ −0.0040 vs the
          +0.015 bar; the +0.0086 difference's every CI spans zero); the S5/S8 ledger
          accrues PIT-quality data but cannot reach n≥600 by 2027-Q3, so absent (a)/(b)
          C3 resolves INCONCLUSIVE per M-SIG §3 (excluded from the denominator, not a
          KILL) and the 2027-Q4 stack vote likely rides on C2/C4 needing 2-of-2.
LEDGER:   `doc/research/VERDICTS.md` V4 row lives on S-REL PR #265 (OPEN, unmerged at this
          writing) — to avoid conflicting with that in-flight branch, the row update is
          noted in this PR's body as a pending rebase item for #265, not edited here.
