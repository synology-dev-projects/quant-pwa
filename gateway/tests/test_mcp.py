import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_mcp_initialize():
    """Verifies standard MCP protocol handshake and capability negotiation."""
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    }
    response = client.post("/mcp/messages", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in data["result"]["capabilities"]
    assert data["result"]["serverInfo"]["name"] == "quant-ai-gateway"


def test_mcp_tools_list():
    """Verifies that MCP tools/list returns standard schemas for all quant tools."""
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    response = client.post("/mcp/messages", json=req)
    assert response.status_code == 200
    data = response.json()
    tools = data["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "get_gexdex" in tool_names
    assert "get_strike_distribution" in tool_names
    assert "get_market_status" in tool_names


def test_mcp_tools_call_market_status():
    """Verifies that MCP tools/call executes get_market_status."""
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "get_market_status",
            "arguments": {}
        }
    }
    response = client.post("/mcp/messages", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["isError"] is False
    content = data["result"]["content"][0]
    assert content["type"] == "text"
    assert "is_live_trading" in content["text"]


@patch("app.mcp.server.get_gexdex", new_callable=AsyncMock)
def test_mcp_tools_call_gexdex(mock_gexdex):
    """Verifies that MCP tools/call executes get_gexdex with arguments."""
    mock_gexdex.return_value = {
        "SPY": {
            "spot_price": 580.0,
            "gamma_regime": "Positive Gamma",
            "call_wall": 590.0,
            "put_wall": 570.0
        }
    }
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "get_gexdex",
            "arguments": {"ticker": "SPY", "strike_range": 20}
        }
    }
    response = client.post("/mcp/messages", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["isError"] is False
    assert "SPY" in data["result"]["content"][0]["text"]
    mock_gexdex.assert_called_once_with(ticker="SPY", strike_range=20, max_dte=50)


def test_mcp_resources_and_prompts():
    """Verifies MCP resources/list and prompts/list endpoints."""
    # Resources List
    res_list = client.post("/mcp/messages", json={"jsonrpc": "2.0", "id": 5, "method": "resources/list"})
    assert res_list.status_code == 200
    assert len(res_list.json()["result"]["resources"]) >= 2

    # Prompts List
    prompt_list = client.post("/mcp/messages", json={"jsonrpc": "2.0", "id": 6, "method": "prompts/list"})
    assert prompt_list.status_code == 200
    assert len(prompt_list.json()["result"]["prompts"]) >= 1
