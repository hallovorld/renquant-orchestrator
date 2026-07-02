# RS-3 data-vendor stack recommendation — research PR

STATUS:   research recommendation under the delegated-decision protocol (operator NOTIFIED,
          not asked; docs only — the purchases themselves are operator/lander actions listed
          as immediate actions in the memo).
REVISION: r1.
WHAT:     `doc/research/2026-07-02-rs3-data-vendor-stack.md` — the RS-3 deliverable (#231 §6,
          due within a week of 2026-07-02): ONE recommendation per need with evidence tier and
          timing. (b) consolidated tape: **Alpaca Algo Trader Plus $99/mo** (full SIP CTA+UTP
          + OPRA, zero integration — collectors already speak the SDK), buy NOW; beats
          Polygon/Massive Advanced ($199) at identical tape coverage. (a) PIT
          fundamentals/estimates: **hold FMP** — existing key verified returning stable-API
          estimates 2026-07-02; the legacy-v3 "402 plan-locked" memory must be re-measured by
          N2's --min-coverage before spending ($29 Starter conditional); true IBES-class PIT
          revisions are institutionally priced → #233's forward accrual stays the load-bearing
          asset. (c) survivorship-free small/mid for M7: **Norgate US Platinum**
          (~$40–60/mo, verify-at-checkout) — index-constituency-BY-DATE is exactly RS-5's
          panel requirement; Sharadar Core bundle conditional on FMP quality-factor gaps.
          Steady-state new spend $99/mo now, ceiling ≈$170–230/mo by August.
WHY/DIR:  #231 Term IC (N2/N3/M-SIG substrate) + Term EXEC (#223 A5.3: IEX-only NBBO
          mis-measures IS; the S10 corpus should mark the feed regime change date).
EVIDENCE: probed this session — alpaca.markets/data (ATP $99 full SIP + OPRA + 10k rpm),
          polygon.io/pricing (Advanced $199 full SIP), FMP stable analyst-estimates returning
          data on the existing key; [verify-at-checkout] flags on Norgate/Sharadar price
          points not directly probed.
NEXT:     Codex re-review; operator/lander executes the CORRECTED immediate actions (r2, below)
          — entitlement verification before any Alpaca subscription, POC/trial before any
          Norgate commitment; N2 first run renders the FMP verdict against the explicit
          decision rule.

## Round 2 (Codex CHANGES_REQUESTED — pricing/integration errors + overstated claims)

**Finding.** 5 issues: (1) Norgate priced as "~$40-60/mo" — wrong; official pricing is a
fixed-term $476.50/6mo or $833/12mo, no monthly plan, and the data model requires a
Windows/VM + per-security/date boolean plugin interface, not downloadable constituent lists —
this changes both the cost commitment and the integration shape. (2) Alpaca's "zero
integration" claim was overstated — a subscription doesn't prove the collectors request
`feed=sip`, persist feed identity, or that the live key's entitlements are actually active.
(3) The FMP "returned data" claim didn't establish coverage/cadence/PIT-semantics or define a
concrete upgrade trigger. (4) "No retail vendor sells true PIT estimate revisions" was an
unsupported categorical claim. (5) Sharadar was listed as an estimates-axis substitute despite
its `datekey` being a filing date, not an estimate-revision timestamp.

**Fix.** Corrected `doc/research/2026-07-02-rs3-data-vendor-stack.md` (r2): Norgate
recommendation downgraded from "M7 kickoff purchase" to "trial/POC-first," with the corrected
fixed-term pricing and a 4-point pre-purchase prerequisite list (Windows/VM+plugin POC,
export/licensing review, accept the fixed-term commitment, 3-week trial acceptance test).
Alpaca ATP downgraded from unconditional "NOW" to "conditional GO, pending entitlement
verification," with 4 required steps (entitlement probe, SIP-vs-IEX A/B capture, per-row feed
provenance stamping, subscription start aligned to the #224/#227-gated N1b activation date so
paid time isn't burned before collection is authorized). FMP upgrade trigger made an explicit,
falsifiable decision rule tied to N2's `--min-coverage` report against the Stage-1 census
requirement. PIT-vendor claim narrowed to "none verified in this survey, at the authorized
budget" with the actual vendors/fields checked listed. Sharadar reclassified as a separate
fundamentals-axis candidate (not an estimates substitute), pricing marked unverified.

**Evidence:** this is a pure-documentation fix (no code/tests in this PR); Norgate's corrected
pricing/integration facts are taken directly from Codex's review (current official
documentation per its stated check) — not independently re-probed in this round.

**Scope:** the overall recommendation shape (Alpaca now, FMP hold, Norgate later, Sharadar
conditional) is unchanged; what changed is that every claim now carries its actual evidentiary
weight instead of being stated as settled.
