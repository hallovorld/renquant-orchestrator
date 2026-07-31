"""The checker must be able to FAIL, to ABSTAIN, and to stay QUIET. (GOAL-5, #652)

Three properties, in the order they can go wrong:

1. **It flags a stale body.** The case that actually happened on 2026-07-30.
2. **It does NOT flag an acknowledged one.** Without this control a checker that
   returns "stale" unconditionally passes (1) — the anti-vacuity test is
   `test_correcting_commit_with_body_acknowledgement_is_not_a_finding`.
3. **It never reports clean about a PR it did not read.** The first version
   `continue`d past a failed detail fetch, so a partial GitHub outage would print
   a clean line while silently omitting exactly the PRs under review. Unreadable
   PRs are preserved as UNMEASURABLE rows, counted in the denominator, and make
   the command exit nonzero.

No test here touches the network: `_gh` is replaced in every test, and the
autouse fixture makes an unstubbed call raise rather than shell out to `gh`.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"
_SPEC = importlib.util.spec_from_file_location(
    "pr_body_correction_check", OPS / "pr_body_correction_check.py")
chk = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(chk)

ME = "hallovorld"

FIRST = "feat(goal5): the shadow scorer must fail closed"
CORRECTING = "fix(goal5): withdraw the unattributed ARM 'decided' claim"
ACK_BODY = "## Result\n\nThe earlier §12 figure is **withdrawn** — see below."
STALE_BODY = "## Result\n\nThe §12 Stage-1 result stands at t=2.92."


def _pr(number: int, *, commits: list[str], body: str = STALE_BODY,
        author: str | None = ME, title: str = "a pull request") -> dict:
    return {"number": number, "title": title, "body": body,
            "author": None if author is None else {"login": author},
            "_commits": commits}


def _install_gh(monkeypatch, prs: list[dict], *, unreadable: dict | None = None,
                raw_detail: dict | None = None) -> list[list[str]]:
    """Replace `_gh` with an in-memory GitHub. Returns the recorded call log.

    `unreadable` maps PR number -> exception to raise for its detail fetch (a 502,
    a timeout, whatever); `raw_detail` maps PR number -> the literal JSON object
    the detail fetch should return, for malformed-payload cases.
    """
    unreadable, raw_detail = unreadable or {}, raw_detail or {}
    calls: list[list[str]] = []

    def fake_gh(args: list[str]) -> str:
        calls.append(list(args))
        if args[:2] == ["pr", "list"]:
            return json.dumps([{k: pr[k] for k in ("number", "title", "body",
                                                   "author")} for pr in prs])
        assert args[:2] == ["pr", "view"], args
        number = int(args[2])
        if number in unreadable:
            raise unreadable[number]
        if number in raw_detail:
            return json.dumps(raw_detail[number])
        pr = next(p for p in prs if p["number"] == number)
        return json.dumps({"commits": [{"messageHeadline": s}
                                       for s in pr["_commits"]]})

    monkeypatch.setattr(chk, "_gh", fake_gh)
    return calls


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any test that forgets to stub `gh` fails loudly instead of hitting GitHub."""
    def boom(args):
        raise AssertionError(f"test attempted a real gh call: {args}")
    monkeypatch.setattr(chk, "_gh", boom)


# --- the pattern is narrow on purpose ----------------------------------------

def test_bare_fix_is_not_a_correction():
    """A bare `fix(...)` is deliberately NOT a correction: fixing a bug is the
    normal business of a PR and says nothing about the body."""
    assert not chk.CORRECTION_IN_COMMIT.search("fix(ops): off-by-one in the loop")
    assert not chk.CORRECTION_IN_COMMIT.search("fix: handle empty input")
    assert not chk.CORRECTION_IN_COMMIT.search("feat(goal5): add the sentinel")


def test_retraction_language_is_a_correction():
    for subject in ("fix(model): withdraw the t(0.975,7) claim",
                    "docs: correct the block-count table",
                    "chore: the 20-day figure is no longer supported",
                    "fix(g1): retract the operator-confirmation claim",
                    "fix(ops): the guard was overbroad"):
        assert chk.CORRECTION_IN_COMMIT.search(subject), subject


# --- selection ---------------------------------------------------------------

def test_first_commit_is_excluded_from_corrections():
    """A PR whose OPENING commit says 'withdraw' is not correcting anything it
    previously claimed — there was no previous claim."""
    assert chk.correcting_commits([CORRECTING]) == []
    assert chk.correcting_commits([FIRST, CORRECTING]) == [CORRECTING]


def test_pr_whose_only_correction_is_its_first_commit_is_clean(monkeypatch):
    _install_gh(monkeypatch, [_pr(1, commits=[CORRECTING], body=STALE_BODY)])
    res = chk.scan("o/r", ME)
    assert res["body_stale"] == 0
    assert res["rows"][0]["status"] == chk.STATUS_NO_CORRECTIONS


def test_other_authors_prs_are_not_selected(monkeypatch):
    _install_gh(monkeypatch, [
        _pr(1, commits=[FIRST, CORRECTING], body=STALE_BODY, author="someone-else"),
        _pr(2, commits=[FIRST, CORRECTING], body=STALE_BODY, author=ME)])
    res = chk.scan("o/r", ME)
    assert res["selected"] == 1
    assert [r["number"] for r in res["rows"]] == [2]
    assert res["body_stale"] == 1


def test_author_none_selects_every_pr(monkeypatch):
    _install_gh(monkeypatch, [
        _pr(1, commits=[FIRST, CORRECTING], author="someone-else"),
        _pr(2, commits=[FIRST, CORRECTING], author=ME)])
    res = chk.scan("o/r", None)
    assert res["selected"] == 2
    assert res["body_stale"] == 2


# --- the finding, and the control that keeps it honest -----------------------

def test_correcting_commit_without_body_acknowledgement_is_a_finding(monkeypatch):
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, CORRECTING],
                                  body=STALE_BODY)])
    res = chk.scan("o/r", ME)
    assert res["body_stale"] == 1
    assert res["findings"][0]["number"] == 11
    assert res["findings"][0]["correcting_commits"] == [CORRECTING]
    assert res["rows"][0]["status"] == chk.STATUS_STALE_BODY
    assert res["rows"][0]["body_acknowledges"] is False


def test_correcting_commit_with_body_acknowledgement_is_not_a_finding(monkeypatch):
    """ANTI-VACUITY CONTROL. Identical to the test above except for the body. A
    checker that flags every PR with a later correcting commit passes that test
    and fails this one."""
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, CORRECTING], body=ACK_BODY)])
    res = chk.scan("o/r", ME)
    assert res["body_stale"] == 0
    assert res["findings"] == []
    assert res["prs_with_corrections"] == 1  # still counted, just not stale
    assert res["rows"][0]["status"] == chk.STATUS_ACKNOWLEDGED
    assert res["rows"][0]["body_acknowledges"] is True


def test_empty_body_is_not_an_acknowledgement(monkeypatch):
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, CORRECTING], body="")])
    assert chk.scan("o/r", ME)["body_stale"] == 1


# --- the partial-read failure path -------------------------------------------

def test_unreadable_pr_is_unmeasurable_and_stays_in_the_denominator(monkeypatch):
    """The fail-open this replaces: PR #12's detail fetch dies, and the old code
    `continue`d, so the run reported 1/1 clean instead of 1 of 2 read."""
    _install_gh(monkeypatch,
                [_pr(11, commits=[FIRST, "chore: tidy"], body=STALE_BODY),
                 _pr(12, commits=[FIRST, CORRECTING], body=STALE_BODY)],
                unreadable={12: RuntimeError("gh pr view failed: HTTP 502")})
    res = chk.scan("o/r", ME)
    assert res["selected"] == 2          # denominator is the SELECTED set
    assert res["measured"] == 1          # ... not the measured set
    assert len(res["unmeasurable"]) == 1
    row = res["unmeasurable"][0]
    assert row["number"] == 12
    assert row["status"] == chk.STATUS_UNMEASURABLE
    assert "502" in row["reason"]
    assert [r["number"] for r in res["rows"]] == [11, 12]  # row preserved


def test_unreadable_pr_makes_the_command_nonzero(monkeypatch, capsys):
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, "chore: tidy"])],
                unreadable={11: RuntimeError("gh pr view failed: HTTP 502")})
    rc = chk.main(["--repo", "o/r", "--author", ME])
    assert rc == chk.EXIT_UNMEASURABLE
    assert rc != chk.EXIT_OK
    out = capsys.readouterr()
    assert "UNMEASURABLE" in out.out and "#11" in out.out
    assert "measured 0/1" in out.out
    assert "INCOMPLETE" in out.err


def test_unmeasurable_takes_precedence_over_findings(monkeypatch):
    """A run that found something AND could not read everything reports incomplete:
    the findings are real but they are not the whole answer."""
    _install_gh(monkeypatch,
                [_pr(11, commits=[FIRST, CORRECTING], body=STALE_BODY),
                 _pr(12, commits=[FIRST], body=STALE_BODY)],
                unreadable={12: TimeoutError("timed out")})
    rc = chk.main(["--repo", "o/r", "--author", ME])
    assert rc == chk.EXIT_UNMEASURABLE != chk.EXIT_FINDINGS


def test_unanticipated_failure_mode_still_lands_on_unmeasurable(monkeypatch):
    """Nothing enumerates the ways a read can fail. An exception type this module
    has never heard of must not fall through to OK."""
    class NeverSeenBefore(Exception):
        pass

    _install_gh(monkeypatch, [_pr(11, commits=[FIRST])],
                unreadable={11: NeverSeenBefore("who knows")})
    res = chk.scan("o/r", ME)
    assert res["measured"] == 0 and len(res["unmeasurable"]) == 1


def test_empty_commits_payload_is_unmeasurable_not_clean(monkeypatch):
    """Every PR has at least one commit, so an empty list means the read did not
    happen; treating it as 'no commits' would launder that into 'no corrections'."""
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, CORRECTING])],
                raw_detail={11: {"commits": []}})
    res = chk.scan("o/r", ME)
    assert res["rows"][0]["status"] == chk.STATUS_UNMEASURABLE
    assert res["measured"] == 0


def test_missing_commits_key_is_unmeasurable_not_clean(monkeypatch):
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, CORRECTING])],
                raw_detail={11: {}})
    assert chk.scan("o/r", ME)["rows"][0]["status"] == chk.STATUS_UNMEASURABLE


def test_absent_author_is_unmeasurable_not_silently_dropped(monkeypatch):
    """Scope undecidable -> the PR stays in the denominator as unread. It must not
    be dropped as 'someone else's' just because the field failed to populate."""
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, CORRECTING], author=None)])
    res = chk.scan("o/r", ME)
    assert res["selected"] == 1 and res["measured"] == 0
    assert "scope undecidable" in res["unmeasurable"][0]["reason"]


# --- exit-code contract ------------------------------------------------------

def test_clean_repo_exits_zero(monkeypatch):
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, "chore: tidy"])])
    assert chk.main(["--repo", "o/r", "--author", ME]) == chk.EXIT_OK


def test_stale_body_exits_findings(monkeypatch):
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST, CORRECTING],
                                  body=STALE_BODY)])
    assert chk.main(["--repo", "o/r", "--author", ME]) == chk.EXIT_FINDINGS


def test_list_query_failure_exits_error(monkeypatch, capsys):
    """If even the LIST fails, the selected set itself is unknown."""
    def fake_gh(args):
        raise RuntimeError("gh pr list failed: HTTP 500")
    monkeypatch.setattr(chk, "_gh", fake_gh)
    assert chk.main(["--repo", "o/r"]) == chk.EXIT_ERROR
    assert "UNUSABLE" in capsys.readouterr().err


def test_all_four_exit_codes_are_distinct():
    codes = {chk.EXIT_OK, chk.EXIT_FINDINGS, chk.EXIT_ERROR, chk.EXIT_UNMEASURABLE}
    assert len(codes) == 4


# --- the query split that made this necessary --------------------------------

def test_list_query_never_asks_for_commits(monkeypatch):
    """`gh pr list --json commits` across 100 PRs trips the GraphQL 500,000-node
    limit; commits are fetched one PR at a time. Author IS asked for in the list,
    so selection does not depend on the fetch that can fail."""
    calls = _install_gh(monkeypatch, [_pr(11, commits=[FIRST])])
    chk.scan("o/r", ME)
    list_call = next(c for c in calls if c[:2] == ["pr", "list"])
    fields = list_call[list_call.index("--json") + 1]
    assert "commits" not in fields
    assert "author" in fields
    assert sum(1 for c in calls if c[:2] == ["pr", "view"]) == 1


def test_json_output_carries_the_unmeasurable_rows(monkeypatch, capsys):
    _install_gh(monkeypatch, [_pr(11, commits=[FIRST])],
                unreadable={11: RuntimeError("boom")})
    chk.main(["--repo", "o/r", "--author", ME, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["selected"] == 1 and payload[0]["measured"] == 0
    assert payload[0]["unmeasurable"][0]["number"] == 11
