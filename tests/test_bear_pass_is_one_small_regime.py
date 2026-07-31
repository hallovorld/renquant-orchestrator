"""GOAL-6 — qualifying my own orch#677 claim that "the criterion IS satisfiable".

#677 established that `BEAR` clears the placebo leg on 11 of 11 artifacts and concluded
the regime sanity criterion is satisfiable — and that mis-specification is therefore
excluded. Re-measured 2026-07-31, the demonstration comes from the panel's smallest
regime:

    regime          n_dates   n_rows   mean_ic   hit_rate   placebo_ic
    BULL_CALM           444   127092    0.0220      0.508       0.0605
    BEAR                 55    15320    0.3346      0.982       0.0158
    BULL_VOLATILE        41     8716    0.1116      0.732       0.1468
    CHOPPY               41    11972    0.0129      0.707       0.0798

**55 dates are not evidence of generalisability** to the regimes that carry the panel,
so #677's exclusion of the mis-specification hypothesis does not stand.

WHAT THIS FILE DOES NOT ASSERT. An earlier version of this module was named
`test_bear_is_a_degenerate_pass.py` and its docstring said a 98.2% hit rate "is the
signature of a cross-section moving as one — not of ranking skill". That is a CAUSAL
claim and nothing here measures it; a genuinely predictive score produces the same
profile. It is withdrawn, and the module is renamed so the executable artifact does not
keep asserting a verdict the document has retracted.

The descriptive facts below stand on their own. Which hypothesis explains `BEAR` — a
beta/volatility-like exposure, or ranking skill concentrated in drawdowns — needs
per-name scores and returns that these artifacts do not carry; the progress doc names
the two diagnostics and why they are a preregistered study rather than a doc edit.
"""

from __future__ import annotations

import csv
import pathlib
import re

EVIDENCE = (pathlib.Path(__file__).resolve().parent.parent
            / "doc/research/evidence/2026-07-31-regime-statistics")
CSV = EVIDENCE / "regime_profile.csv"
DOC = (pathlib.Path(__file__).resolve().parent.parent
       / "doc/progress/2026-07-31-qualifying-the-satisfiable-claim.md")


def _by_name():
    with CSV.open() as fh:
        return {r["regime"]: r for r in csv.DictReader(fh)}


def test_the_only_passing_regime_is_the_smallest_by_dates():
    """THE qualification: the one example of satisfiability is the thinnest slice in
    the panel — 55 dates against BULL_CALM's 444."""
    rows = _by_name()
    assert int(rows["BEAR"]["n_passed"]) == 11
    assert int(rows["BEAR"]["median_n_dates"]) == 55
    assert int(rows["BEAR"]["median_n_dates"]) < int(rows["BULL_CALM"]["median_n_dates"]) / 8


def test_the_regime_carrying_the_panel_is_a_coin_flip_and_never_passes():
    """BULL_CALM: 444 dates, 127k rows, hit rate 0.508 — and 0 of 11."""
    bc = _by_name()["BULL_CALM"]
    assert int(bc["n_passed"]) == 0
    assert 0.50 < float(bc["median_hit_rate"]) < 0.52
    assert int(bc["median_n_rows"]) > 8 * int(_by_name()["BEAR"]["median_n_rows"])


def test_the_passing_regimes_statistics_are_unlike_every_other_regimes():
    """Descriptive, and deliberately not explained here: 15x the IC of the regime
    carrying 8x the rows, positive on 98.2% of its dates."""
    rows = _by_name()
    bear = float(rows["BEAR"]["median_mean_ic"])
    others = [float(r["median_mean_ic"]) for k, r in rows.items() if k != "BEAR"]
    assert bear / max(others) > 2.9
    assert bear / float(rows["BULL_CALM"]["median_mean_ic"]) > 15
    assert float(rows["BEAR"]["median_hit_rate"]) > 0.98


def test_the_qualification_does_not_overturn_the_placebo_finding():
    """CONTROL. #677's other claim — that BULL_CALM fails the PLACEBO leg with a
    positive mean_ic, not the skill floor — is untouched and still holds, whichever
    hypothesis explains BEAR."""
    bc = _by_name()["BULL_CALM"]
    assert float(bc["median_mean_ic"]) > 0
    assert float(bc["median_placebo_ic"]) > 2 * float(bc["median_mean_ic"])


def test_the_document_does_not_present_a_MECHANISM_as_established():
    """The correction this round. The causal sentence may appear only inside the
    struck-through withdrawal, never as a live claim — the review-surface-outliving-
    the-correction defect, which this programme has now hit on four PRs."""
    text = DOC.read_text(encoding="utf-8")
    # The quote is wrapped across lines inside a blockquote, so match on the flattened
    # text and locate the strikethrough spans by offset rather than by line.
    flat = re.sub(r"\s*\n>?\s*", " ", text)
    struck = [m.span() for m in re.finditer(r"~~.+?~~", flat, re.S)]
    phrase = "cross-section moving as one"
    hits = [m.start() for m in re.finditer(re.escape(phrase), flat)]
    assert hits, "the withdrawal itself must stay on the record"
    assert struck, "no strikethrough span found — the withdrawal is not marked"
    for at in hits:
        assert any(a <= at < b for a, b in struck), \
            f"causal claim at offset {at} is outside every ~~withdrawal~~ span"
    assert "H1" in text and "H2" in text, "both hypotheses must be named as live"
    assert re.search(r"insufficient evidence of generalisab", text, re.I)


def test_the_conclusion_is_scoped_to_what_the_profile_can_support():
    """Anti-vacuity for the test above: withdrawing the mechanism is only half the
    correction. The document must still state the conclusion the numbers DO support —
    that #677's exclusion of mis-specification does not stand."""
    text = DOC.read_text(encoding="utf-8")
    assert "not excluded" in text
    assert "does not stand" in text
    assert "No claim is made" in text and "why" in text


# ---------------------------------------------------------------------------
# Codex on #680: the causal explanation is a hypothesis, not a finding.
# ---------------------------------------------------------------------------

def _phi(z):
    import math
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _profile():
    import csv
    p = (pathlib.Path(__file__).resolve().parent.parent
         / "doc/research/evidence/2026-07-31-regime-statistics/regime_profile.csv")
    return {r["regime"]: r for r in csv.DictReader(p.open())}


def test_the_hit_rate_is_implied_by_mean_over_sigma_not_independent_evidence():
    """The number I double-counted.

    If per-date ICs were i.i.d. Normal, a regime's hit rate is `Phi(mean/sigma)`. BEAR's
    54-of-55 is what its own mean/sigma = 2.51 implies, so "hit rate 0.982" carries no
    information beyond "mean IC is 2.5 sigma above zero". Citing both as separate
    symptoms of degeneracy counted one quantity twice.
    """
    r = _profile()["BEAR"]
    z = float(r["median_mean_ic"]) / float(r["median_std_ic"])
    assert abs(z - 2.514) < 0.01
    implied = _phi(z)
    observed = float(r["median_hit_rate"])
    assert abs(observed - implied) < 0.02, (observed, implied)


def test_the_placebo_evidence_points_AGAINST_the_leakage_hypothesis():
    """Reported because it cuts against the story I told.

    If leakage explained BEAR, its shuffled-label placebo would be the one most likely
    to be elevated. It is the LOWEST of the four. Not decisive -- a placebo tests label
    leakage, not a beta or volatility tilt, which survives a shuffle -- but omitting it
    while publishing the rest of the profile would have been selective.
    """
    prof = _profile()
    placebo = {k: float(v["median_placebo_ic"]) for k, v in prof.items()}
    assert min(placebo, key=placebo.get) == "BEAR", placebo
    assert placebo["BULL_VOLATILE"] > 4 * placebo["BEAR"]


def test_the_discriminating_measurement_is_named_AND_its_blocker_identified():
    """What this section adds that the withdrawal above does not.

    Deliberately NOT re-asserting the downgrade: two tests already enforce it (the
    strikethrough span and the scoped conclusion), and a third copy would drift.
    What is new is naming the measurement that would settle it -- per-date
    cross-sectional dispersion, plus IC after beta/volatility control -- and recording
    that it is blocked by the SAME re-scoring path GOAL-6 is already stuck behind.
    That link is the actionable part: two open questions resolve on one unblock.
    """
    d = " ".join(re.sub(r"(?m)^\s*>\s?", "",
                        DOC.read_text(encoding="utf-8")).split())
    assert "cross-sectional dispersion" in d
    assert "703 759 rows" in d
    assert "same blocked evaluation path" in d
    assert "cfdd6cb8e950da0f" in d
