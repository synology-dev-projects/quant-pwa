#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gateway/tests/test_reproduce_flow_pipeline_auth.py

Reproduction test for:
TradingEdge Flow pipeline authentication failure and silent redirect loop.

Bug:
1. common_lib.flow.extract.get_authenticated_flow_session sends config.te_pass ("4354GoGo!!")
   instead of the TradingEdge Flow passcode ("GoWithTheFlow").
2. It fails silently when the login gate does not issue the .EDGE cookie,
   returning an unauthenticated session that redirects to Login.aspx and returns 0 records.
"""
from unittest.mock import MagicMock, patch
import pytest
from pydantic import SecretStr


def test_reproduce_flow_auth_passcode_and_gate_verification():
    """
    Verifies that get_authenticated_flow_session:
    1. Sends the dedicated flow passcode ("GoWithTheFlow" or config.te_flow_passcode),
       NOT config.te_pass ("4354GoGo!!").
    2. Strictly verifies that the '.EDGE' cookie was issued by TradingEdge.
    3. Raises RuntimeError if the .EDGE cookie is absent.
    """
    from common_lib.flow.extract import get_authenticated_flow_session

    mock_config = MagicMock()
    mock_config.te_pass = SecretStr("4354GoGo!!")
    mock_config.te_flow_passcode = SecretStr("GoWithTheFlow")
    mock_config.te_user_agent = "TestAgent"
    mock_config.te_option_login_gate = "https://flow.tradingedge.club/Login.aspx?ReturnUrl=%2fdefault.aspx"

    # Case 1: When login gate fails to set .EDGE cookie, it MUST raise RuntimeError
    mock_get_resp = MagicMock()
    mock_get_resp.text = '<html><input id="__VIEWSTATE" value="vs"/><input id="__VIEWSTATEGENERATOR" value="vsg"/><input id="__EVENTVALIDATION" value="ev"/></html>'
    mock_get_resp.url = "https://flow.tradingedge.club/Login.aspx?ReturnUrl=%2fdefault.aspx"

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.url = "https://flow.tradingedge.club/Login.aspx?ReturnUrl=%2fdefault.aspx"

    with patch("requests.Session") as mock_session_cls:
        session_instance = MagicMock()
        mock_session_cls.return_value = session_instance
        session_instance.get.return_value = mock_get_resp
        session_instance.post.return_value = mock_post_resp
        session_instance.cookies.get_dict.return_value = {}  # No .EDGE cookie issued

        # In buggy implementation, this does NOT raise RuntimeError
        with pytest.raises(RuntimeError, match="\\.EDGE"):
            get_authenticated_flow_session(mock_config)


def test_reproduce_flow_auth_uses_gowiththeflow_payload():
    """
    Verifies that get_authenticated_flow_session submits 'GoWithTheFlow'
    in the form payload rather than config.te_pass ('4354GoGo!!').
    """
    from common_lib.flow.extract import get_authenticated_flow_session

    mock_config = MagicMock()
    mock_config.te_pass = SecretStr("4354GoGo!!")
    mock_config.te_flow_passcode = SecretStr("GoWithTheFlow")
    mock_config.te_user_agent = "TestAgent"
    mock_config.te_option_login_gate = "https://flow.tradingedge.club/Login.aspx?ReturnUrl=%2fdefault.aspx"

    mock_get_resp = MagicMock()
    mock_get_resp.text = '<html><input id="__VIEWSTATE" value="vs"/><input id="__VIEWSTATEGENERATOR" value="vsg"/><input id="__EVENTVALIDATION" value="ev"/></html>'
    mock_get_resp.url = "https://flow.tradingedge.club/Login.aspx?ReturnUrl=%2fdefault.aspx"

    with patch("requests.Session") as mock_session_cls:
        session_instance = MagicMock()
        mock_session_cls.return_value = session_instance
        session_instance.get.return_value = mock_get_resp
        session_instance.cookies.get_dict.return_value = {".EDGE": "valid_token"}

        try:
            get_authenticated_flow_session(mock_config)
        except RuntimeError:
            pass

        assert session_instance.post.called, "session.post was not called"
        posted_data = session_instance.post.call_args[1].get("data", {})
        # Bug check: prior to fix, posted_data['m_userName'] is '4354GoGo!!'
        assert posted_data.get("m_userName") == "GoWithTheFlow", (
            f"Expected 'GoWithTheFlow', got '{posted_data.get('m_userName')}'"
        )
