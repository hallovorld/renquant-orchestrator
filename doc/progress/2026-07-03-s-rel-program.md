# S-REL experiment reliability program — design PR (2026-07-03)

STATUS:   design RFC + seeded standing-verdict ledger; docs only — no code, no config, no
          production behavior change. Round 2: tightened per codex review (2026-07-03) —
          R1 renamed/narrowed to "adversarial reimplementation/recheck" (no institutional-
          independence overclaim), R2 split into Class A (mechanism, positive control
          mandatory) vs Class B (observational, shuffle/placebo fallback), audit queue cut to
          a 2-in-flight capacity bound with V1–V3 ACTIVE and V4–V7 explicitly DEFERRED.
REVISION: r2.
WHAT:     `doc/design/2026-07-03-s-rel-experiment-reliability.md` — the reliability contract
          for verdicts (R1 provisional-until-adversarially-*rechecked*, honestly scoped as
          reimplementation/recheck rather than institutional independence, with UPHELD/
          OVERTURNED/WEAKENED outcomes and a precise "load-bearing number" definition; R2 now
          splits Class A mechanism tests — code-level ON/OFF switches like λ-round-1's solver
          gate, positive control MANDATORY — from Class B observational/cross-sectional panel
          studies — S9/M8/M3-style, where planting a "realistic" effect is itself a modeling
          choice, so a shuffle/placebo-detection fallback plus an explicit no-positive-control
          acknowledgment applies instead; R3 mandatory evidence-boundary block; R4 mandatory
          reopening conditions), the retrospective audit queue now capacity-bounded at 2
          in-flight items with explicit sequencing (V1 S9 ACTIVE — recheck UPHELD #263,
          merged; V2 M8 ACTIVE — recheck UPHELD #264, merged; V3 M3 ACTIVE — recheck WEAKENED
          #269, landing; V4 C3 reconciliation, V5 pipeline#162 intercept finding, V6 phase −1
          durability-then-verify, V7 low-load batch — all four DEFERRED, each with its own
          explicit promotion condition, not queued for automatic dispatch), the hardened
          evidence-JSON convention (input content hashes + code git-sha/dirty flag + env lock
          hash, new harnesses + verification runs only, no retro-editing), and scope
          discipline (no re-litigation without new evidence; one adversarial pass, no
          verification regress; no mass retrofit; no production surface; CI compliance checks
          deferred). Plus `doc/research/VERDICTS.md` seeded with 14 standing verdicts.
WHY/DIR:  operator directive 2026-07-03 ("试验可靠性优先级很高！放在短期p0，着重处理") after
          challenging whether rejected-direction experiments are 100% scientific. The proven
          precedent: λ-sweep round 1's harness never armed its mechanism (`qp_solver.py:468`
          both-params gate; merged #240's revision history) — the NULL was overturned by
          Codex's adversarial pass. Near-misses caught ad hoc (C3 substrate contamination, S9
          label-units, RS-5 prereg-contract drift) confirm the failure class is live. S-REL
          turns the ad-hoc pass into a contract. Round-2 direction: codex requested changes
          (r1 overshot governance weight for a one-operator team) — R1 overstated
          independence, R2 didn't distinguish mechanism from observational tests, and stacking
          V3–V6 into the same P0/P1 wave as V1/V2 read as reliability theater. V1–V3's actual
          landed outcomes (2× UPHELD, 1× WEAKENED) are now the direct evidence for right-sizing
          scope to the smallest version that already caught a real fragility.
EVIDENCE: audit-queue anchors — S9 `2026-07-03-s9-track-a-conditional.md` (#262, NULL); M8
          `2026-07-03-m8-cluster-wave1.md` (#261, NO-GO); M3 `2026-07-02-m3-haircut-replay.md`
          (AC FAIL, retired-era/SE-proxy/fwd_20d fragility); C3
          `2026-07-02-c3-residual-momentum.md` (UNADJUDICATED) vs the plan addendum's "C3
          MISS" wording (conflict = V4); pipeline#162 shadow replay (neutral −0.2902,
          laundered 44–45→0, floor admits ~0–1); phase −1 PR #199 CLOSED unmerged — its NO-GO
          is relied on by merged plans while its memo/script are not on main (V6 durability
          finding). Measured infra gap: `evidence/2026-07-03-m8/m8_verdict.json` stamps
          `generated_utc` only — no input hashes, code SHA, or env stamp. `[VERIFIED — direct
          `gh pr view` confirms #263 (S9/V1) and #264 (M8/V2) merged as UPHELD; #269 (M3/V3)
          open with a WEAKENED verdict; `scripts/require_progress_doc.py` passes against this
          PR's actual changed-file list]`
NEXT:     V3's WEAKENED verification (#269) lands, completing all 3 ACTIVE-tier items; V4–V7
          stay DEFERRED until a capacity slot opens under the 2-in-flight bound AND their own
          explicit promotion condition fires (no automatic dispatch); next master-plan dated
          addendum references S-REL + the ledger; R1 (reimplementation/recheck)/R2
          (Class A/B split)/R3/R4 enforced at PR review from merge forward.
