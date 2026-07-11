# Shadow A/B Price-Snapshot CI Import Closure

STATUS: complete
WHAT: The hermetic shadow A/B wrapper fixture now supplies the four real
      checkout sources used by the price-snapshot import path:
      `renquant-common`, `renquant-base-data`, `renquant-artifacts`, and
      `renquant-pipeline`.
WHY-DIR: `LocalStore` initializes the pipeline package, which imports common,
         base-data, and artifacts on this path. The fixture previously exposed
         only common and pipeline, failing price-snapshot setup before the
         watchdog assertions could execute. Model packages are lazy optional
         imports and are intentionally not fixture dependencies.
EVIDENCE: An isolated import probe reproduced the missing-artifacts failure
          before the change; both CI test jobs and the progress-doc gate pass
          with the four-repository closure. `renquant-execution` remains fake,
          preserving the dirty-repository fail-closed test's isolation.
NEXT: No runtime, deployment, strategy, or pipeline behavior changes. Keep
      this fixture limited to modules actually imported by the exercised path.
