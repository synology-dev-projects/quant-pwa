import pytest
from unittest.mock import patch, MagicMock
import requests
from common_lib.config.main_config import MainConfig
import common_lib.connectors.tradingedge.dexgex as dexgex


def test_reproduce_reauth_cooldown():
    """
    REPRODUCTION TEST (DEFECT-gexdex-snapshot-failure):
    Rapid calls to get_authenticated_session(force_refresh=True) must respect a cooldown
    period (e.g. 30s) and not spam TradingEdge /gate, which triggers HTTP 429.
    """
    # Reset cached session
    dexgex._cached_session = None
    if hasattr(dexgex, "_last_auth_time"):
        dexgex._last_auth_time = 0.0

    mock_config = MagicMock()
    mock_config.te_login_gate = "https://tools.tradingedge.club/gate"
    mock_config.te_user_agent = "Mozilla/5.0"
    mock_config.te_pass.get_secret_value.return_value = "secret"

    with patch("requests.Session") as mock_session_cls:
        session_instance = MagicMock()
        mock_session_cls.return_value = session_instance

        # Mock successful GET for CSRF token
        mock_get_resp = MagicMock(status_code=200, text='<input name="_token" value="csrf123">')
        # Mock successful POST for auth
        mock_post_resp = MagicMock(status_code=200, text='<title>Toolbox - Trading Edge</title>')
        session_instance.get.return_value = mock_get_resp
        session_instance.post.return_value = mock_post_resp

        # First call: performs authentication
        s1 = dexgex.get_authenticated_session(mock_config, force_refresh=True)
        assert s1 is not None
        assert session_instance.post.call_count == 1

        # Second call immediately after: force_refresh=True within cooldown must reuse cached session
        # and NOT hit post again!
        s2 = dexgex.get_authenticated_session(mock_config, force_refresh=True)
        assert s2 is s1
        assert session_instance.post.call_count == 1, (
            f"Expected 1 POST call due to cooldown, got {session_instance.post.call_count}"
        )


def test_reproduce_login_gate_429_backoff_retry():
    """
    REPRODUCTION TEST (DEFECT-gexdex-snapshot-failure):
    When TradingEdge /gate returns HTTP 429 Too Many Requests,
    get_authenticated_session must backoff and retry once instead of instantly failing.
    """
    dexgex._cached_session = None
    if hasattr(dexgex, "_last_auth_time"):
        dexgex._last_auth_time = 0.0

    mock_config = MagicMock()
    mock_config.te_login_gate = "https://tools.tradingedge.club/gate"
    mock_config.te_user_agent = "Mozilla/5.0"
    mock_config.te_pass.get_secret_value.return_value = "secret"

    with patch("requests.Session") as mock_session_cls, patch("time.sleep") as mock_sleep:
        session_instance = MagicMock()
        mock_session_cls.return_value = session_instance

        mock_get_resp = MagicMock(status_code=200, text='<input name="_token" value="csrf123">')
        # First POST returns 429 with Retry-After header, second POST returns 200
        mock_post_429 = MagicMock(status_code=429, headers={"Retry-After": "1"}, text="Too Many Requests")
        mock_post_200 = MagicMock(status_code=200, text='<title>Toolbox - Trading Edge</title>')
        session_instance.get.return_value = mock_get_resp
        session_instance.post.side_effect = [mock_post_429, mock_post_200]

        session = dexgex.get_authenticated_session(mock_config, force_refresh=True)
        assert session is not None, "Session should succeed after backing off and retrying on 429"
        assert session_instance.post.call_count == 2
        assert mock_sleep.called


def test_reproduce_extract_raw_data_no_reauth_on_server_error():
    """
    REPRODUCTION TEST (DEFECT-gexdex-snapshot-failure):
    extract_raw_data should not trigger re-authentication on server errors (HTTP 500)
    or network exceptions, only on actual auth expiration (401/403/redirect).
    """
    mock_config = MagicMock()
    mock_config.te_dex_gex_url = "https://tools.tradingedge.club/api/dex-gex"

    mock_session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock(status_code=500, text="Internal Server Error", history=[])
    mock_session.get.return_value = mock_resp

    with patch("common_lib.connectors.tradingedge.dexgex.get_authenticated_session") as mock_reauth:
        res = dexgex.extract_raw_data(mock_config, mock_session, "AAPL")
        assert res is None
        assert not mock_reauth.called, "extract_raw_data must not trigger re-authentication on HTTP 500 server error"
