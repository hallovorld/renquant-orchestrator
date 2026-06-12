# Mainline Engineering Census PR

**Status:** implementation PR owned by codex.

## Scope

This PR turns the current engineering-census arguments into executable output:

- repo SHAs and dirty flags for orchestrator / pipeline / strategy / umbrella;
- key file LOC for the current god modules;
- strategy-config recursive-key and prose-key counts;
- AST-counted `buy_blocked=True` writer sites with file and line evidence;
- CLI and script entrypoints suitable for CI and review branches.

The core rule is: future architecture docs should cite
`renquant-orchestrator engineering-census`, not hand counts from comments.

## Non-Scope

This PR does not change trading behavior, model promotion gates, broker state,
or live scheduler cutover. It is the evidence substrate for the larger
GateRegistry / LiveStateV2 / ArtifactResolver work.

## Commands

```bash
renquant-orchestrator engineering-census --strict
renquant-orchestrator engineering-census --expect-buy-blocked-writers 16 --strict
python scripts/engineering/census_ci.py
```

Use `--expect-buy-blocked-writers` only when a branch intentionally wants to
fail closed on direct writer count drift.
