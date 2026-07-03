# S-REL experiment reliability program — design PR (2026-07-03)

STATUS:   design RFC + seeded standing-verdict ledger; docs only — no code, no config, no
          production behavior change.
REVISION: r1.
WHAT:     `doc/design/2026-07-03-s-rel-experiment-reliability.md` — the reliability contract
          for verdicts (R1 provisional-until-adversarially-verified with UPHELD/OVERTURNED/
          WEAKENED outcomes and a precise "load-bearing number" definition; R2 mandatory
          committed positive controls in every negative-result harness, planted at decision
          scale; R3 mandatory evidence-boundary block with a literal template; R4 mandatory
          reopening conditions, the E34→M8 pattern generalized), the retrospective audit queue
          (V1 S9 IN FLIGHT, V2 M8 IN FLIGHT, V3 M3 next, V4 C3 adjudication reconciliation,
          V5 pipeline#162 intercept finding, V6 phase −1 durability-then-verify, V7 low-load
          batch not dispatched) with per-item load-bearing numbers and flip conditions, the
          hardened evidence-JSON convention (input content hashes + code git-sha/dirty flag +
          env lock hash, new harnesses + verification runs only, no retro-editing), and scope
          discipline (no re-litigation without new evidence; one adversarial pass, no
          verification regress; no mass retrofit; no production surface; CI compliance checks
          deferred). Plus `doc/research/VERDICTS.md` seeded with 14 standing verdicts.
WHY/DIR:  operator directive 2026-07-03 ("试验可靠性优先级很高！放在短期p0，着重处理") after
          challenging whether rejected-direction experiments are 100% scientific. The proven
          precedent: λ-sweep round 1's harness never armed its mechanism (`qp_solver.py:468`
          both-params gate; merged #240's revision history) — the NULL was overturned by
          Codex's adversarial pass. Near-misses caught ad hoc (C3 substrate contamination, S9
          label-units, RS-5 prereg-contract drift) confirm the failure class is live. S-REL
          turns the ad-hoc pass into a contract.
EVIDENCE: audit-queue anchors — S9 `2026-07-03-s9-track-a-conditional.md` (#262, NULL); M8
          `2026-07-03-m8-cluster-wave1.md` (#261, NO-GO); M3 `2026-07-02-m3-haircut-replay.md`
          (AC FAIL, retired-era/SE-proxy/fwd_20d fragility); C3
          `2026-07-02-c3-residual-momentum.md` (UNADJUDICATED) vs the plan addendum's "C3
          MISS" wording (conflict = V4); pipeline#162 shadow replay (neutral −0.2902,
          laundered 44–45→0, floor admits ~0–1); phase −1 PR #199 CLOSED unmerged — its NO-GO
          is relied on by merged plans while its memo/script are not on main (V6 durability
          finding). Measured infra gap: `evidence/2026-07-03-m8/m8_verdict.json` stamps
          `generated_utc` only — no input hashes, code SHA, or env stamp.
NEXT:     V1/V2 verification memos land (UPHELD/WEAKENED/OVERTURNED) within the SHORT tier;
          dispatch V3 (M3) and V5 (#162) with this doc's load-bearing lists as frozen briefs;
          V4 reconciliation memo; V6 step-1 durability PR recommitting phase −1 evidence; next
          master-plan dated addendum references S-REL + the ledger; R2/R3/R4 enforced at PR
          review from merge forward.
