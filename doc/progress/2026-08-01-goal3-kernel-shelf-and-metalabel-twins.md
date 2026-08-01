# Twin guard extended: the kernel evidence shelf and the meta_label pins (GOAL-3)

## What landed

Two new check classes in `scripts/check_twin_parity.py`, extending the C3-style guard
toward registry item A6 (orch#728's ask, on orch#734's measurements):

* **`kernel_shelf:*` (6 pairs, byte-identical class):** the umbrella kernel's
  statistical-evidence shelf (`metrics/block_bootstrap|hac_se|deflated_sharpe|pbo|
  perf_summary`, `risk_metrics`) vs the **pinned renquant-common copy**. Measured
  byte-identical 2026-08-01; the guard exists so the day they stop being identical is a
  reviewed retire-or-refresh decision instead of silent drift.
* **`metalabel_pin:*` (3 pairs, pinned-divergence class):** the meta_label twins whose
  divergence is exactly a 4-line import rewrite (orch#734). Both sides' sha256 are pinned
  in `data/twin_parity_manifest.json`; a change on EITHER side — a real edit, or a pin
  advance moving the serving copy — fails and forces a reviewed re-pin.
  `build_manifest` (`--write-manifest`) now generates this section, so the regenerate-
  and-review workflow covers it.

## The comparison object, chosen deliberately

Both new classes compare against the **`.subrepo_runtime` pinned copies** — the code that
actually deploys — not the sibling dev checkouts, which were measured 50+ commits stale
this session. Both sides live under the umbrella root, so the checks need no new repo
resolution and skip loudly only when the umbrella itself is absent.

## Live state at landing `[本次实测 2026-08-01]`

`twin-parity: 23 pass, 0 fail, 0 skip` (was 14) — all 6 shelf pairs identical, all 3
meta_label pairs matching their pinned divergence.

## Tests

7 hermetic tests (tmp trees): shelf identical/diverged (+A6 instruction in the FAIL
text), pins matching, either side moving fails with a re-pin instruction, missing
umbrella skips both, and an EMPTY pin section is a FAIL rather than a silent pass. The
synthetic all-pass fixture and the manifest roundtrip were extended to carry the nine
files, so `build_manifest → run_checks` stays a closed loop. Suite: 5373 passed.

## Not claimed

That the shelf copies are the right long-term home — that is A6's remediation question
(retire vs refresh), and this guard only makes the drift visible. That the meta_label
divergence is semantically safe beyond what orch#734 measured (4-line import rewrite,
single Task class on the serving path).
