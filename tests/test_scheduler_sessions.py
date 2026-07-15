import asyncio
from unittest.mock import Mock

from app.core import scheduler
from app.routes import kcar as kcar_routes
from app.routes import lotte as lotte_routes


class StubSessionService:
    def __init__(self, result: bool) -> None:
        self.result = result

    def _ensure_session(self) -> bool:
        return self.result


def test_lotte_session_warmer_reports_false_refresh(monkeypatch) -> None:
    logger = Mock()
    monkeypatch.setattr(scheduler, "logger", logger)
    monkeypatch.setattr(
        lotte_routes,
        "get_lotte_service",
        lambda: StubSessionService(False),
    )
    monkeypatch.setattr(kcar_routes, "kcar_service", StubSessionService(True))

    asyncio.run(scheduler.warm_sessions())

    logger.warning.assert_any_call("Cache warmer: Lotte session refresh failed")
    assert not any(
        call.args == ("Cache warmer: Lotte session refreshed",)
        for call in logger.info.call_args_list
    )


def test_kcar_session_warmer_reports_false_refresh(monkeypatch) -> None:
    logger = Mock()
    monkeypatch.setattr(scheduler, "logger", logger)
    monkeypatch.setattr(
        lotte_routes,
        "get_lotte_service",
        lambda: StubSessionService(True),
    )
    monkeypatch.setattr(kcar_routes, "kcar_service", StubSessionService(False))

    asyncio.run(scheduler.warm_sessions())

    logger.warning.assert_any_call("Cache warmer: KCar session refresh failed")
    assert not any(
        call.args == ("Cache warmer: KCar session refreshed",)
        for call in logger.info.call_args_list
    )
