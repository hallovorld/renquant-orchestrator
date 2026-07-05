# Wire train_gbdt + patchtst_weekly_cutoff into CLI

STATUS: delivered
WHAT: Added `train-gbdt` and `patchtst-cutoff` subcommands to the orchestrator CLI
WHY/DIR: Both modules had `main()` entry points but were only usable via
`python -m renquant_orchestrator.train_gbdt` / `.patchtst_weekly_cutoff`.
Wiring them into the CLI makes them discoverable and consistent with all other
orchestrator commands.
EVIDENCE: 2887 passed, 3 skipped (pre-existing), 0 new failures
NEXT: none
