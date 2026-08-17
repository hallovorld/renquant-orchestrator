"""Smoke checks for the regime-detector research's REPRODUCIBLE CORE (PR #985).

Codex review 2026-08-17: the research must separate what a clean checkout can
regenerate from what depends on local, uncommitted corpora. These tests exercise
only COMMITTED inputs:

  1. The P3 prereg-plane counts (77 BEAR days / 9 episodes) regenerate exactly
     from the committed 2026-08-08 posterior snapshot — the memo's most
     decision-relevant number (the 5.4x plane mismatch's small side).
  2. The phase-A-dependent section of the posteriors-ic derivation script is
     GUARDED: on a checkout without the local corpus it must skip cleanly
     (writing `phase_a_ic.skipped`) instead of crashing — the split Codex asked
     for. Checked at source level so the test needs no heavy runtime deps.
  3. The Hurst white-noise null (P1) re-derives when the umbrella kernel is
     importable; skipped (not failed) on focused checkouts without it.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "doc" / "research" / "data"
POSTERIORS_CSV = DATA / "2026-08-08-regime-posteriors.csv"
DERIVATION_SCRIPT = DATA / "2026-08-17-regime-detector-posteriors-ic.py"


def test_prereg_plane_counts_regenerate_from_committed_snapshot():
    """P3's small side: argmax over the committed posterior snapshot = 77 BEAR
    days in 9 episodes. Pure stdlib; no local corpus, no market data."""
    with POSTERIORS_CSV.open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "committed posterior snapshot is empty"
    pcols = [c for c in rows[0] if c.startswith("regime_p_")]
    assert len(pcols) == 4, f"expected 4 posterior columns, got {pcols}"
    labels = [max(pcols, key=lambda c: float(r[c])) for r in rows]
    bear = [lab == "regime_p_bear" for lab in labels]
    bear_days = sum(bear)
    bear_episodes = sum(
        1 for i, b in enumerate(bear) if b and (i == 0 or not bear[i - 1])
    )
    assert bear_days == 77, f"prereg-plane BEAR days {bear_days} != 77"
    assert bear_episodes == 9, f"prereg-plane BEAR episodes {bear_episodes} != 9"


def test_phase_a_section_is_guarded_not_load_bearing():
    """The derivation script must skip the phase-A section cleanly when the
    local corpus is absent (the reproducible core still writes its output)."""
    src = DERIVATION_SCRIPT.read_text(encoding="utf-8")
    # The guard: existence check on the local corpus before any read of it...
    assert 'forward_returns.csv").exists()' in src, (
        "phase-A guard missing: the script would crash on a clean checkout"
    )
    # ...and the skip is recorded in the output rather than silently absent.
    assert '"skipped": True' in src
    # The guard must come BEFORE the first read of the local corpus.
    assert src.index('forward_returns.csv").exists()') < src.index(
        'pd.read_csv(PA / "forward_returns.csv")'
    ), "guard appears after the corpus read — fail-open ordering"


def test_hurst_white_noise_null_reproduces_when_kernel_available():
    """P1: the serving Hurst estimator on 63-day pure white noise exceeds the
    0.65 momentum threshold on the vast majority of draws. Deterministic seed;
    skips (not fails) when the umbrella kernel is not on this checkout."""
    np = pytest.importorskip("numpy")
    import sys

    kernel_root = REPO.parent / "RenQuant" / "backtesting" / "renquant_104"
    if not (kernel_root / "kernel" / "regime.py").exists():
        pytest.skip("umbrella kernel not present on this checkout")
    sys.path.insert(0, str(kernel_root))
    try:
        from kernel.regime import compute_hurst  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"kernel import failed on this checkout: {exc}")
    finally:
        sys.path.pop(0)

    rng = np.random.default_rng(42)  # the manifest's committed seed
    draws = [compute_hurst(rng.standard_normal(63)) for _ in range(200)]
    hs = np.array([h for h in draws if h is not None])
    assert len(hs) >= 150, "estimator returned too few values on noise"
    share_momentum = float((hs > 0.65).mean())
    # The committed measurements report 84.6% (n=500, seed 42) and an
    # independent 89.0% (n=300, fresh seed). Assert the qualitative finding
    # with head-room, not the exact decimal: a *majority* of pure-noise draws
    # clear the momentum threshold.
    assert share_momentum > 0.6, (
        f"white-noise H>0.65 share {share_momentum:.1%} — P1 finding did not "
        "reproduce"
    )
