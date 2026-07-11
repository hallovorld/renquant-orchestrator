# Shadow Manifest Preflight Ordering

STATUS: complete
WHAT: The shadow A/B wrapper now verifies the immutable run manifest before
      reading local market data or writing a price or market snapshot.
WHY-DIR: A dirty pinned checkout previously reached snapshot setup first and
         could return setup exit 2 instead of the required fail-closed
         manifest-precheck exit 3.
EVIDENCE: `TestRunManifestVerification` proves wrong-commit and dirty-tree
          manifests exit 3 before either snapshot artifact is created.
          [VERIFIED - 2026-07-11: 2 focused tests passed]
NEXT: Keep the runner-side verification before arming; no production shadow
      schedule or enablement state changes with this fix.
