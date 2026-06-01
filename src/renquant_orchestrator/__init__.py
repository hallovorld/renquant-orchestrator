"""RenQuant pinned-subrepo orchestration package."""

__all__ = ["DailyRunContext", "DailyRunPipeline", "run_contract_fixture"]


def __getattr__(name: str):
    if name == "run_contract_fixture":
        from .contract_fixture import run_contract_fixture

        return run_contract_fixture
    if name in {"DailyRunContext", "DailyRunPipeline"}:
        from .daily import DailyRunContext, DailyRunPipeline

        return {"DailyRunContext": DailyRunContext, "DailyRunPipeline": DailyRunPipeline}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
