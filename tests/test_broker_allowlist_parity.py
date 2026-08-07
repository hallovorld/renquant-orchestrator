"""The probe must compare OBJECTS, and must never silently pass.

The defect this guards is not the allow-list drift itself — it is how that drift
was first mis-measured. I grepped each file for `alpaca[a-z_-]*`, counted string
literals, and reported that the two PINNED copies diverged 15 vs 3. Imported,
both are 15 and identical. `test_the_probe_never_reads_source_text` is the test
that keeps this probe from repeating that.
"""
from __future__ import annotations

import sys
import types

import pytest

from ops.renquant104 import broker_allowlist_parity_probe as P


def _mod(tags):
    m = types.SimpleNamespace()
    m.ALLOWED_BROKERS = tags
    return m


# ── the method is the point ────────────────────────────────────────────────

def test_the_probe_never_reads_source_text():
    """A text-based version would reproduce the error it exists to catch."""
    import pathlib
    src = pathlib.Path(P.__file__).read_text()
    body = src.split('"""', 2)[-1]          # skip the module docstring
    for forbidden in ("read_text(", "open(", "re.findall", "grep", "readlines"):
        assert forbidden not in body, (
            f"the probe must import and compare objects, never scan text: {forbidden!r}")


def test_identical_lists_are_clean(monkeypatch):
    tags = ("alpaca", "alpaca_shadow")
    monkeypatch.setattr(P, "_load_pinned", lambda: _mod(tags))
    monkeypatch.setattr(P, "_load_umbrella", lambda: _mod(tags))
    r = P.scan()
    assert r["identical"] and not r["missing_from_umbrella"]
    assert P.main([]) == P.EXIT_OK


def test_a_missing_tag_is_a_finding(monkeypatch):
    monkeypatch.setattr(P, "_load_pinned", lambda: _mod(("a", "b", "c")))
    monkeypatch.setattr(P, "_load_umbrella", lambda: _mod(("a", "b")))
    r = P.scan()
    assert r["missing_from_umbrella"] == ["c"]
    assert P.main([]) == P.EXIT_FINDING


def test_an_extra_umbrella_tag_alone_is_not_a_finding(monkeypatch):
    """A tag the umbrella accepts and pinned does not cannot break the default
    path. Reported so it is never invisible, but it must not page."""
    monkeypatch.setattr(P, "_load_pinned", lambda: _mod(("a",)))
    monkeypatch.setattr(P, "_load_umbrella", lambda: _mod(("a", "z")))
    r = P.scan()
    assert r["only_in_umbrella"] == ["z"]
    assert not r["missing_from_umbrella"]
    assert P.main([]) == P.EXIT_OK
    assert "informational" in P.render(r)


# ── refusal, never a silent pass ───────────────────────────────────────────

@pytest.mark.parametrize("which", ["_load_pinned", "_load_umbrella"])
def test_an_unimportable_copy_refuses(monkeypatch, which):
    monkeypatch.setattr(P, "_load_pinned", lambda: _mod(("a",)))
    monkeypatch.setattr(P, "_load_umbrella", lambda: _mod(("a",)))

    def boom(*a, **k):
        raise P.Unreadable("simulated")

    monkeypatch.setattr(P, which, boom)
    assert P.main([]) == P.EXIT_REFUSE, (
        "a copy that cannot be read must REFUSE — reporting it clean is the "
        "fail-open this repo keeps finding")


def test_a_module_without_the_attribute_refuses(monkeypatch):
    monkeypatch.setattr(P, "_load_pinned", lambda: types.SimpleNamespace())
    monkeypatch.setattr(P, "_load_umbrella", lambda: _mod(("a",)))
    assert P.main([]) == P.EXIT_REFUSE


def test_load_pinned_ignores_a_preloaded_sys_modules_entry(tmp_path, monkeypatch):
    """A stale `renquant_pipeline.state_paths` already sitting in `sys.modules`
    (e.g. from the test process or an earlier import) must not win over the
    pinned copy on disk — that is exactly how the probe would silently compare
    the wrong module and miss the fallback crash it exists to detect."""
    pkg_dir = tmp_path / "renquant_pipeline"
    pkg_dir.mkdir()
    (pkg_dir / "state_paths.py").write_text(
        "ALLOWED_BROKERS = frozenset({'real_tag'})\n"
    )

    fake = types.ModuleType("renquant_pipeline.state_paths")
    fake.ALLOWED_BROKERS = frozenset({"fake_tag"})
    fake.__file__ = "/tmp/not-the-pinned-copy/state_paths.py"
    monkeypatch.setitem(sys.modules, "renquant_pipeline.state_paths", fake)
    monkeypatch.setitem(sys.modules, "renquant_pipeline", types.ModuleType("renquant_pipeline"))

    top = P._load_pinned(src=tmp_path)
    assert top.ALLOWED_BROKERS == frozenset({"real_tag"}), (
        "the preloaded sys.modules entry must not win over the file at PINNED_SRC")


# ── the live machine ───────────────────────────────────────────────────────

def test_the_live_divergence_is_what_the_record_describes():
    """Pinned 15, umbrella 10, five missing including three live fleet lanes
    [VERIFIED — 2026-08-07]. If this changes the record must be re-derived."""
    try:
        r = P.scan()
    except P.Unreadable:
        pytest.skip("umbrella/pinned evidence absent — the unit tests still ran")
    assert set(r["missing_from_umbrella"]) >= {
        "alpaca_shadow_blend_mom_fast",
        "alpaca_shadow_blend_rb_fast",
        "alpaca_shadow_blend_rb_mom",
    }, r
    assert not r["only_in_umbrella"], r
