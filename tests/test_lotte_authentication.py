from unittest.mock import Mock

from app.core.config import settings
from app.services.lotte_service import LotteService


def test_missing_lotte_credentials_fail_before_network(monkeypatch) -> None:
    service = object.__new__(LotteService)
    service.session = None
    service._init_session = Mock(
        side_effect=AssertionError("missing credentials must not reach the network")
    )
    monkeypatch.setattr(settings, "lotte_username", None)
    monkeypatch.setattr(settings, "lotte_password", None)

    assert service._do_authenticate() is False
    service._init_session.assert_not_called()
