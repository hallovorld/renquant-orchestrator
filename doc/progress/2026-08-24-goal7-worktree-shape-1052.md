# goal7 producer test: repo identity by git toplevel, not basename (orch#1052)

STATUS: closes the 6th and last clean-main red catalogued in orch#1052.

WHAT: `test_the_orchestrator_revision_comes_from_THIS_repo_not_the_cwd`
asserted `ORCH_REPO.name == "renquant-orchestrator"` — the DIRECTORY
basename. Every `git worktree` (whose directory carries a scratch name)
failed the repo's own test for being itself: the directory-name-is-not-an-
identity lesson, applied to the test. The producer itself was always
correct (`ORCH_REPO = Path(__file__).resolve().parent.parent` — anchored
to the module, cwd-independent); only the test's identity check was wrong.

FIX: identity asserted by CONTENT + GIT — the producer module must live
inside `ORCH_REPO`, and `git -C ORCH_REPO rev-parse --show-toplevel` must
equal `ORCH_REPO` (so the revision it reports describes THIS repo, not an
enclosing checkout). Both properties hold in the primary checkout AND in
any worktree; neither can be satisfied by standing in the wrong cwd.

§4(b): file suite **28 passed** with the full CI dep set in a worktree
[VERIFIED — 2026-08-24]; the single target test also passes in the primary
checkout. Before the fix the test failed in every worktree
(`'ledger-2b' == 'renquant-orchestrator'` assertion error).
