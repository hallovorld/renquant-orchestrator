# Four-system as-built documentation + INDEX normalization

Date: 2026-07-04
Campaign: Phase 3 (compliance fix campaign doc normalization)
Status: DELIVERED

## What

Documented the four RenQuant systems (104/105/106/107) as they actually exist
today, not as originally designed. Each as-built doc covers: purpose, architecture,
key modules by repo, models/gates/contracts, current status, known issues, and
cross-references to the other three.

Also normalized `doc/INDEX.md` from an agent-centric grep target into a structured
system documentation index with sections: as-built architecture, active governance,
active design notes, superseded/historical, and agent rules.

## Deliverables

1. `doc/design/renquant-104-as-built.md` — production daily batch decisioning
2. `doc/design/renquant-105-as-built.md` — intraday session decisioning (Stage-1/2)
3. `doc/design/renquant-106-as-built.md` — signal evolution (expkit + M-SIG)
4. `doc/design/renquant-107-as-built.md` — governance (attribution + risk + S-REL)
5. `doc/INDEX.md` — normalized documentation index
