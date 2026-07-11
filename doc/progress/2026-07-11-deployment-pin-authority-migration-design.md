# Deployment-pin authority migration design (R-PIN)

STATUS:    design PR open, awaiting Codex review — DESIGN ONLY, no
           implementation, no migration execution
WHAT:      `doc/design/2026-07-11-deployment-pin-authority-migration.md` —
           move deployment-pin authority from the umbrella
           `subrepos.lock.json` into an orchestrator-owned, PR-reviewed
           deployment manifest; umbrella becomes a pure consumer via a
           generated, provenance-stamped mirror; five verified stages, no
           big-bang.
WHY/DIR:   Codex blocked umbrella PRs #460/#461 (verbatim in the design §2.1):
           the umbrella "must not regain runtime artifact or deployment
           ownership"; "Move the active run-manifest/pin consumer to
           renquant-orchestrator … Do not record further current deployment
           state in the umbrella lock." Slots into the architecture registry
           (`doc/design/2026-07-10-architecture-compliance-registry.md`) as
           stage R-PIN under T2/T4, with the audit A §3 ownership
           disposition explicitly revised on the record (§3 of the design).
EVIDENCE:  [VERIFIED] 7 of 9 deployed pins currently differ from the last
           committed umbrella lock (table in design §2.2; gh-api committed
           state vs on-disk lock, 2026-07-11) — the deployed state has NO
           durable record anywhere today. [VERIFIED] consumer inventory:
           18 launchd plists → umbrella scripts; only 2 read the lock
           directly, 8 via 3–4 choke-point modules, 8 none (per-script grep,
           design §4.1). [VERIFIED] promote_pin.py guarantee set mapped
           line-by-line (design §6). Target pattern already proven by
           D6-§2a run-manifest + artifact_store binding (orchestrator #460/
           #464, shadow_ab_runner.py:562/589).
NEXT:      Codex review of the design (esp. §7 apply-then-record vs
           record-first — flagged as the most review-worthy decision and
           §12 open questions). After merge: Stage 1 implementation PR
           (schema + capture + FIRST durable record of today's deployed
           state — closes the current gap with zero consumer change).

## Bottom line

The only channel that recorded deployed pin state (umbrella lock PRs) is
now review-blocked by design; the deployed state is unrecorded. The design
gives the pins a new home where recording is mechanically reviewable
(renquant-orchestrator), preserves every promote_pin.py guarantee
(dry-run → apply → e2e-verify → auto-revert, promote-bak pair, M9 snapshot
backstop, pin-advance CI gate), defines a single transition invariant
(one authority at every instant; every derived pin document hash-verified
at every consumer entry, fail-closed on divergence; the deploy↔record gap
bounded to one trading session and alarmed, never silent), and lands in
five individually-shippable, individually-revertible stages — Stage 1 alone
resolves today's unrecorded-state problem.

## r2 (Codex review, 2026-07-11 — revised PERSONALLY per the design-PR rule)

All five objections incorporated:
1. **Record-first is the default** (§7 rewritten): pin-bump PR merges before
   any machine apply; apply executes only a manifest hash-equal to
   origin/main. The emergency lane is a separately privileged, ssh-signed
   (#465 pattern), expiring authorization with an immutable receipt and a
   1-session reconciliation SLA; stacking blocks all applies.
2. **Invariant honesty** (§8 matrix + stage restructure): choke-point
   verification is installed and armed in Stage 3, one full stage BEFORE
   the Stage 4 authority flip; pre-flip, no reader ever consumes an
   unverifiable derivative (the manifest is explicitly labeled shadow).
3. **Replay defense**: monotonic `generation` epoch + forward-only
   expected-generation record (§5.1/§5.2); reverts advance the epoch;
   stale-pair restore and torn-apply are named failure modes with an
   explicit `reconcile-generation` recovery and mandated drills.
4. **No umbrella anchoring of state** (§5.2): neutral host root
   `~/.renquant/deploy/` from Stage 1; A14's convention explicitly
   superseded for the pin plane; the on-disk lock survives only as the
   legacy mirror until the Stage 5 tombstone.
5. **Portable authority** (§5.1): no host paths in the durable manifest —
   repo identity only; paths live in the per-host verified runtime
   inventory.
