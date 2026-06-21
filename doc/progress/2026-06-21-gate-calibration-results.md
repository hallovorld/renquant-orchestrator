# WF-gate calibration audit — interim results

STATUS:   in-progress (T2/T3 done; T1-exact pending a build; gate looks VINDICATED so far)
WHAT:     interim results for the gate-calibration audit (#162). The evidence leans AGAINST the
          hopeful "gate over-blocks a good model" reading: the 05-22 live model recorded negative
          IC itself (-0.0246); the new checks enforce cross-sectional skill it never had; the
          BULL_CALM monotonicity inversion is real (n=93, spearman -0.24, not a low-sample artifact).
WHY/DIR:  operator asked if the gate (not the model) is the binding constraint. Honest finding:
          gate is the proximate cause (bar moved 05-24/25 after 05-22 trading) but is NOT killing a
          skilled model — it enforces skill the model lacked. Points the lever upstream (signal),
          not at the gate or the horizon. I raised the gate-doubt, so I flag the data refutes it.
EVIDENCE: live model oos_mean_ic -0.0246 (own json); fresh-recipe rebuild real_ic -0.0227 (gate
          log); BULL_CALM monotonicity n=93 spearman -0.24 (round_trips.csv); placebo threshold
          floored at IC~0 (symptom not cause). `[VERIFIED — artifact json + gate logs + round_trips]`
NEXT:     T1-exact: gate the exact live weights through today's full gate (needs recipe-matched
          corpus build) for confirmation. Then a properly-powered signal-existence diagnostic.
          NO gate loosening / bypass.
