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
    assert "get_unusual_flow" in tool_names


def test_mcp_tools_call_unusual_flow():
    """Verifies that MCP tools/call executes get_unusual_flow."""
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "get_unusual_flow",
            "arguments": {"date": "2026-08-21"}
        }
    }
    with patch("app.mcp.server.get_unusual_flow", return_value="| **NVDA** | BUY CALL | $130.00 | +2.0% | 2026-09-18 | 15,000 ⚠️ | $25.00M |"):
        response = client.post("/mcp/messages", json=req)
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["isError"] is False
        assert "NVDA" in data["result"]["content"][0]["text"]


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


@pytest.mark.anyio
async def test_mcp_sse_get():
    """Verifies GET /mcp/sse initiates SSE stream with endpoint announcement."""
    from fastapi import Request
    from app.mcp.server import mcp_sse_endpoint
    scope = {"type": "http", "method": "GET", "path": "/mcp/sse", "headers": []}
    req = Request(scope)
    resp = await mcp_sse_endpoint(req)
    assert resp.status_code == 200
    assert resp.media_type == "text/event-stream"
    gen = resp.body_iterator
    first_chunk = await anext(gen)
    assert "event: endpoint" in first_chunk
    assert "/mcp/messages?session_id=" in first_chunk
    await gen.aclose()


def test_mcp_sse_post():
    """Verifies POST /mcp/sse handles direct JSON-RPC payload."""
    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "ping",
        "params": {}
    }
    response = client.post("/mcp/sse", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 10
    assert data["result"] == {}


def test_mcp_messages_get():
    """Verifies GET /mcp/messages returns status metadata JSON."""
    response = client.get("/mcp/messages")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "quant-ai-mcp"
    assert data["protocolVersion"] == "2024-11-05"
    assert data["status"] == "active"
    assert "MCP JSON-RPC 2.0" in data["message"]


def test_mcp_messages_post():
    """Verifies POST /mcp/messages handles standard JSON-RPC payload."""
    req = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "ping",
        "params": {}
    }
    response = client.post("/mcp/messages", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 11
    assert data["result"] == {}


def test_mcp_root_get():
    """Verifies GET /mcp returns server discovery JSON."""
    response = client.get("/mcp")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "quant-ai-gateway"
    assert data["protocolVersion"] == "2024-11-05"
    assert data["endpoints"]["sse"] == "/mcp/sse"
    assert data["endpoints"]["messages"] == "/mcp/messages"


def test_mcp_root_post():
    """Verifies POST /mcp executes direct JSON-RPC request."""
    req = {
        "jsonrpc": "2.0",
        "id": 20,
        "method": "tools/list",
        "params": {}
    }
    response = client.post("/mcp", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 20
    assert "tools" in data["result"]


@pytest.mark.anyio
async def test_root_sse_get():
    """Verifies GET /sse root alias initiates SSE stream."""
    from fastapi import Request
    from app.mcp.server import mcp_sse_endpoint
    scope = {"type": "http", "method": "GET", "path": "/sse", "headers": []}
    req = Request(scope)
    resp = await mcp_sse_endpoint(req)
    assert resp.status_code == 200
    assert resp.media_type == "text/event-stream"
    gen = resp.body_iterator
    first_chunk = await anext(gen)
    assert "event: endpoint" in first_chunk
    assert "/mcp/messages?session_id=" in first_chunk
    await gen.aclose()


def test_root_sse_post():
    """Verifies POST /sse root alias executes JSON-RPC request."""
    req = {
        "jsonrpc": "2.0",
        "id": 30,
        "method": "ping",
        "params": {}
    }
    response = client.post("/sse", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 30
    assert data["result"] == {}


def test_root_messages_post():
    """Verifies POST /messages root alias executes JSON-RPC request."""
    req = {
        "jsonrpc": "2.0",
        "id": 40,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-root", "version": "1.0"}
        }
    }
    response = client.post("/messages", json=req)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 40
    assert data["result"]["serverInfo"]["name"] == "quant-ai-gateway"
