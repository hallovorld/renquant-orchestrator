# MoE revision 2 — a power gate that can kill the line, and soft sector membership

STATUS:    DESIGN, operator-directed. Nothing deployed, nothing measured beyond
           the arithmetic below. Adds two BLOCKING stages ahead of the existing
           Stage 0, both runnable today because neither needs the served matrix.

WHAT:      (a) Stage -1 power gate: the effective sample size for a date-level
           claim under a 20-day label, the resulting MDE, and a kill condition
           if the MDE exceeds the plausible effect.
           (b) Stage 0' positive control with an empirical power curve — the
           design had a placebo but no positive control at all.
           (c) Sector membership becomes a soft vector from published ETF
           holdings instead of a hand-written thematic partition.

WHY/DIR:   Operator asked whether the design is optimal and whether the
           experiments and data are right. Two answers, both negative and both
           arithmetic rather than opinion:
           - The motivating measurement sits at its own detection threshold.
           - The hand labels are not a partition; four of the fifteen describe
             one correlated block, and a name that is genuinely in three of them
             must pick one.

EVIDENCE:  artifact:      strategy_config.json `sector_map` (159 names, 15
                          labels); the per-regime IC table in revision 1
                          (orch#904) read from
                          panel-ltr.alpha158_fund.weekly_20260706T230931Z.staging.json
           prod or exp:   prod — the live sector map and the gate's own stamped
                          per-regime profile
           existing data: no power analysis, no effective-sample-size
                          calculation, and no positive control exist anywhere in
                          revision 1 or its progress doc
           best-known?:   yes for the n_eff and MDE figures — first time either
                          has been computed for this line. The per-date IC
                          autocorrelation was measured earlier (the skill-gate
                          kill); this doc is the first to carry it through to a
                          power statement.
           scope:         design document only. No code, no config, no pin, no
                          production surface.

           n_eff = n_dates / H, H = 20:
             BULL_CALM 454 -> 22.7   BEAR 55 -> 2.8
             BULL_VOLATILE 41 -> 2.0   CHOPPY 41 -> 2.0
           MDE = 2.8 * sd(IC_t) / sqrt(n_eff); at sd = 0.15, BEAR MDE = 0.253.
           Reported BEAR genuine IC at 1x = +0.245. The motivating number is AT
           the noise floor.

           This is consistent with, and quantifies, something revision 1
           observed but could only call implausible: the BEAR placebo swinging
           +0.108 -> +0.016 -> -0.122 across shift multiples is sampling noise on
           fewer than three effective observations.

THE REORDERING THIS FORCES: revision 1 calls regime "the ONLY well-populated
           axis". True of dates, false of information. A regime effect is a
           date-level quantity (every name on a date shares the regime), so it is
           identified only across dates -> n_eff 2-3 in three of four regimes. A
           sector effect varies WITHIN a date. The axis treated as safe is the
           weak one; regime x sector inherits the worse of the two.

TESTS:     none — design only. The arithmetic in the doc is reproducible from
           n_dates and H; the empirical n_eff (block bootstrap, gap >= H) is
           specified as Stage -1's first deliverable rather than asserted here.

NEXT:      Run Stage -1, the power gate: estimate n_eff empirically per regime
           via block bootstrap (gap >= H), take min(rule-of-thumb, bootstrap),
           convert the MDE to bps via the section 4 transfer function, and
           apply the kill condition. Runs today — not blocked by orch#905.

NOT DECIDED HERE:

  * Whether to shorten the label horizon for the gating question, extend
    history, or drop regime conditioning and test membership pooled. Stage -1's
    output chooses; deciding in advance is what this doc exists to prevent.
  * Universe expansion. Breadth helps every date immediately, but NO amount of
    universe expansion changes n_eff — only history depth or label horizon does.
    Expansion is also a live-system change (traded universe, shadow config
    fingerprint re-stamp, history backfill) with its own gates.
  * orch#905 still blocks Stages 0-4. Stages -1 and 0' deliberately do not
    depend on it.
