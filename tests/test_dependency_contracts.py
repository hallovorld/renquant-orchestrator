from pathlib import Path


def test_common_dependency_includes_live_bundle_contract() -> None:
    pyproject = Path("pyproject.toml").read_text()

    # Floor 0.10.0: renquant_common.notify (canonical ntfy sender, campaign B6).
    assert '"renquant-common>=0.10.0"' in pyproject
    assert '"renquant-common>=0.1.0"' not in pyproject
    assert '"renquant-common>=0.8.0"' not in pyproject
