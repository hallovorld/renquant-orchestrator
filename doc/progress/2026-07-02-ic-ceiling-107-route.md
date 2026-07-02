# IC ceiling + institutional gap + 107 route — research PR

STATUS:   research + route design for review (docs only — no code/config/broker/risk/sizing
          change). Durable record of the 2026-07-02 strategy discussion; extends roadmap #229 to
          2028 and supersedes its §9 sign-off list per the operator's delegation grant.
REVISION: r3 — operator directive "每个论点需要理论或数据支持；允许POC；严肃科研": four read-only,
          reproducible POCs executed and committed (scripts/poc_*.py + evidence JSONs +
          `doc/research/2026-07-02-roadmap-poc-verification.md`), converting the route's
          load-bearing reasoned-tier claims to measured-tier: POC-A effective breadth
          BR_eff ≈ 131/yr point [77,500] (route §7.1 re-anchored: current-universe active IR
          0.24, post-M8 0.40); POC-B conviction-scarcity claim REFUTED as stated (post-retrain
          raw-Kelly ceiling 93–95%; shrinkage-realistic ≈40–43%, state-dependent → S6 rationale
          rewritten); POC-C real broker fills (N=41) confirm fills = open auction, buy-day
          open-vs-close +48.6bps mean/+58.1 median (t≈1.0 — direction measured, significance =
          S10), overnight/intraday split corrected to 62/38 (not ~100/0); POC-D intra-family
          factor |ρ| = 0.217 ⇒ stacking 3×0.02 → 0.029 not 0.035 (§2.4 planning range
          0.028–0.033). Prior: r2 — operator review ("规划不够专业不够深入不够负责任"): the route lacked bounds, per-
          milestone contingencies, and a whole-roadmap confidence audit. Added: §7 BOUNDS (the
          ceiling in IC/book/dollar layers + an ABOVE-ceiling leakage alarm at IC>0.08/Sharpe>2;
          the floor in three tiers — engineered benchmark-sleeve floor, the UNBOUNDED
          undisciplined floor that makes the ops track load-bearing, and the fact we sit BELOW
          the engineered floor today); §8 PER-MILESTONE RISK REGISTER (every N/S/M/L milestone
          and composite gate: P(success) with basis, dominant failure modes, a Plan B written
          before outcomes are known, and the downstream-impact propagation — incl. the key
          resilience facts that G106 does not depend on the WF gate and the route's P is nearly
          independent of D1's verdict); §9 REASONABLENESS AUDIT (failure-independence /
          resource-realism / sequence-risk tests; July capacity priority order fixed now:
          S1–S5 > S8–S10 > S6–S7 > S11–S12) + the MASTER FALLBACK LADDER (four stable,
          pre-valued terminal states — the direct answer to "实现不来怎么办") + the confidence
          statement: P(rung 1) ≈ 0.60–0.70 dominated by G106 ≈ 0.45–0.50 (a coin flip, named as
          the plan's honest heart), P(rung ≥2) ≈ 0.85, P(rung ≥3) ≈ 0.97. Prior: r1.
WHAT:     `doc/research/2026-07-02-ic-ceiling-institutional-gap-107-route.md` — (1) the
          delegated-decision protocol operationalizing the operator's grant (the four §9
          sign-offs now author-decided, conditional on a six-point research standard:
          evidence-tier declaration, pre-registration, Codex adversarial review with
          escalate-on-disagreement, staged capital + rollback, notify-not-approve, hard safety
          limits unchanged); (2) the model-IC ceiling analysis (fundamental law IR = TC·IC·√BR;
          ceiling table by information set: current 0.02–0.04, +PIT orthogonal 0.03–0.05,
          down-cap 0.05–0.08 gross; we measure genuine ≈ 0 — floor, not ceiling); (3) the
          institutional gap dissected in five layers with the quantitative reframe that
          institutions win on √BR and TC at per-forecast ICs at-or-below our ceiling —
          IC 0.01 × √500k × TC 0.5 ≈ IR 3.5; (4) the "ordinary professional institution" bar
          quantified from SPIVA/HFRI evidence (median pro: net Sharpe 0.5–0.8, alpha ≈ 0 —
          ~85–90% of large-cap funds underperform SPX net over 10–15y); (5) VERDICT: 107 can
          reach that bar by end-2028 with ~60–70% probability via a four-increment stack
          (sleeve baseline → execution expectancy +0.5–1.5%/yr → orthogonal IC stack +1–2%/yr →
          risk shaping +0.1–0.2 Sharpe), needing increment 0 plus any two others; (6) the
          105→106→107 route with pre-registered exit gates (G105/G106/G107), kill branches
          (2027-Q4 no signal ≥0.02 ⇒ benchmark-sleeve default + 107 re-scoped
          execution-only), and the verification-horizon honesty: SE(Sharpe) ≈ √((1+SR²/2)/T) ⇒
          built-and-tracking by 2028, statistically proven only 2029–30 — all route gates are
          therefore LEADING indicators (measured IC, TC, IS savings), never trailing Sharpe.
WHY/DIR:  operator directives (2026-07-02 evening): the four sign-offs are delegated with the
          explicit condition of deep/professional/responsible research; the question "can 107
          catch up to an ORDINARY professional institution" needs a falsifiable answer — so the
          bar is quantified from median-professional data (not top-tier), the probability is
          decomposed per increment instead of asserted, the single dominant risk is named (the
          D3 information-set bet, ~50%), and the statistical limits of verifying Sharpe parity
          on 2 years of data are stated up front rather than discovered in 2028.
EVIDENCE: measured tier — A1 genuine IC ≈ 0.04 CI [−0.031,+0.129], BULL_CALM ≈ −0.003; #256
          61% persistence; embargo floor ~+0.04; E27/E33 (linear > transformers); E34 (blind
          breadth NO-GO); E35 naive +0.066; sim Sharpe 0.77 ≈ benchmark, live flat; TC drag
          artifacts from the 07-01 OXY forensics. Cited tier — McLean–Pontiff 2016 (~26%/~58%
          decay), Hou–Xue–Zhang 2020, Gu–Kelly–Xiu 2020 (monthly OOS R² ≈ 0.4%), SPIVA
          (~85–90% underperform net), HFRI equity-hedge median Sharpe 0.5–0.8,
          Clarke–de Silva–Thorley 2002 (TC), Qlib CSI300 benchmarks (reference market).
NEXT:     Codex review; operator reads the verdict + route (notification per the delegation
          protocol). On merge: G105/G106/G107 gates and the kill branches become the standing
          assessment criteria cited by thesis reviews (M10/L7 of #229); the §1 protocol governs
          every future exercise of the delegated decisions, starting with RS-1 (sleeve) and the
          M2 canary envelope.
