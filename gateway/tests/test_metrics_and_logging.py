import json
import logging
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    CACHE_HITS,
    CACHE_MISSES,
    ACTIVE_SSE_CONNECTIONS,
    ACTIVE_ALERTS_COUNT,
    SCRAPE_DURATION,
    get_metrics_payload,
    CONTENT_TYPE_LATEST,
)
from app.core.logging_config import JSONLogFormatter, configure_gateway_logging
from app.core.quote_feed import get_batch_quotes, clear_quote_cache

client = TestClient(app)


def test_metrics_endpoint_unauthenticated():
    """
    Verifies that /metrics is unauthenticated and returns standard Prometheus formatted text.
    """
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    content = resp.text
    assert "quant_http_requests_total" in content
    assert "quant_http_request_duration_seconds" in content
    assert "quant_cache_hits_total" in content
    assert "quant_cache_misses_total" in content

    # Test /api/metrics alias
    resp_api = client.get("/api/metrics")
    assert resp_api.status_code == 200
    assert "quant_http_requests_total" in resp_api.text


def test_http_request_metrics_middleware_increments():
    """
    Verifies that HTTP requests through the gateway increment the REQUEST_COUNT counter
    and record duration in REQUEST_LATENCY histogram.
    """
    # Issue request to an existing endpoint
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    text = metrics_resp.text

    # Assert request was recorded for /api/auth/status
    assert 'quant_http_requests_total{endpoint="/api/auth/status",method="GET",status_code="200"}' in text


@pytest.mark.anyio
async def test_cache_metrics_instrumentation():
    """
    Verifies that cache hits and misses increment the Prometheus counters.
    """
    clear_quote_cache()

    hit_before = CACHE_HITS.labels(cache_name="quote_feed")._value.get()
    miss_before = CACHE_MISSES.labels(cache_name="quote_feed")._value.get()

    with patch("app.core.quote_feed.fetch_single_quote", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {"ticker": "SPY", "price": 500.0, "updated_at": "2026-09-21T00:00:00Z"}

        # First fetch: cache miss
        quotes1 = await get_batch_quotes(["SPY"])
        assert "SPY" in quotes1
        assert CACHE_MISSES.labels(cache_name="quote_feed")._value.get() == miss_before + 1

        # Second fetch: cache hit
        quotes2 = await get_batch_quotes(["SPY"])
        assert "SPY" in quotes2
        assert CACHE_HITS.labels(cache_name="quote_feed")._value.get() == hit_before + 1


def test_json_log_formatter_structure():
    """
    Verifies that JSONLogFormatter outputs single-line valid JSON with standard fields.
    """
    formatter = JSONLogFormatter()
    record = logging.LogRecord(
        name="quant.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Test log message with value %d",
        args=(123,),
        exc_info=None,
    )
    record.trace_id = "tr-abc1234"

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "quant.test"
    assert data["message"] == "Test log message with value 123"
    assert data["trace_id"] == "tr-abc1234"
    assert "timestamp" in data


def test_json_log_formatter_exception_trace():
    """
    Verifies that exceptions are formatted into the JSON log output when exc_info is present.
    """
    formatter = JSONLogFormatter()
    try:
        raise ValueError("Simulated database failure")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="quant.error",
        level=logging.ERROR,
        pathname="test.py",
        lineno=99,
        msg="Critical failure encountered",
        args=(),
        exc_info=exc_info,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "ERROR"
    assert data["message"] == "Critical failure encountered"
    assert "exception" in data
    assert "ValueError: Simulated database failure" in data["exception"]
