import time
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.engine.circuit_breaker import CircuitBreaker, CircuitState
from app.engine.service import (
    GexDexService,
    gexdex_service,
    calculate_metrics_from_raw,
    render_gexdex_chart_image,
    get_strike_distribution,
    GexDexTickerMetrics
)


@pytest.mark.anyio
async def test_circuit_breaker_closed_state_normal_execution():
    """Verifies that in CLOSED state, successful function calls return results and maintain CLOSED state."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0

    async def sample_async_func(x, y):
        return x + y

    res = await cb.call(sample_async_func, 10, 20, fallback=-1)
    assert res == 30
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0

    def sample_sync_func(a, b):
        return a * b

    res_sync = await cb.call(sample_sync_func, 5, 6, fallback=-1)
    assert res_sync == 30
    assert cb.state == CircuitState.CLOSED


@pytest.mark.anyio
async def test_circuit_breaker_open_state_after_three_failures():
    """Verifies that circuit breaker transitions to OPEN after failure_threshold consecutive failures."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

    async def failing_func():
        raise RuntimeError("Simulated upstream failure")

    # 1st failure
    res1 = await cb.call(failing_func, fallback="fallback_1")
    assert res1 == "fallback_1"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    # 2nd failure
    res2 = await cb.call(failing_func, fallback="fallback_2")
    assert res2 == "fallback_2"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 2

    # 3rd failure -> Trips to OPEN
    res3 = await cb.call(failing_func, fallback="fallback_3")
    assert res3 == "fallback_3"
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 3


@pytest.mark.anyio
async def test_circuit_breaker_fast_0ms_fallback_when_tripped():
    """Verifies that when OPEN, calls bypass the target function and return fallback immediately (sub-5ms)."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    cb.state = CircuitState.OPEN
    cb.failure_count = 3
    cb.last_state_change = time.monotonic()

    called_flag = False

    async def slow_work():
        nonlocal called_flag
        called_flag = True
        await asyncio.sleep(2.0)
        return "slow_success"

    t0 = time.perf_counter()
    res = await cb.call(slow_work, fallback={"status": "circuit_open"})
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert called_flag is False
    assert res == {"status": "circuit_open"}
    assert elapsed_ms < 10.0  # Fast immediate bypass


@pytest.mark.anyio
async def test_circuit_breaker_recovery_in_half_open_state():
    """Verifies recovery timeout transition to HALF_OPEN, probe execution, and reset to CLOSED."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    cb.state = CircuitState.OPEN
    cb.failure_count = 3
    cb.last_state_change = time.monotonic() - 2.0  # Expire cooldown

    # Probe call succeeds
    async def healthy_probe():
        return "recovered"

    res = await cb.call(healthy_probe, fallback="error")
    assert res == "recovered"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.anyio
async def test_circuit_breaker_half_open_failure_reopens():
    """Verifies that if a probe fails during HALF_OPEN, the circuit re-opens immediately."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    cb.state = CircuitState.OPEN
    cb.failure_count = 3
    cb.last_state_change = time.monotonic() - 2.0  # Expire cooldown

    async def failing_probe():
        raise ConnectionError("Still failing")

    res = await cb.call(failing_probe, fallback="fallback_error")
    assert res == "fallback_error"
    assert cb.state == CircuitState.OPEN


@pytest.mark.anyio
async def test_gexdex_service_get_summary_in_process():
    """Verifies in-process get_summary execution on GexDexService."""
    service = GexDexService()

    mock_metrics = GexDexTickerMetrics(
        ticker="AAPL",
        spot_price=220.0,
        gamma_regime="Positive (Long Gamma / Volatility Dampening)",
        net_gex=500000000.0,
        net_dex=-200000000.0,
        zero_gex_level=215.0,
        call_wall=230.0,
        put_wall=210.0,
        gamma_centroid=222.0,
        call_gex=700000000.0,
        put_gex=200000000.0,
        call_put_ratio=3.5,
        key_gamma_strike=230.0,
        gex_above_spot=400000000.0,
        gex_below_spot=100000000.0,
        gex_above_pct=80.0,
        dex_above_spot=-150000000.0,
        dex_below_spot=-50000000.0,
        dex_above_pct=75.0,
        front_week_gex_pct=45.0,
        dominant_expiration="2026-08-28",
        expected_move_dollars=7.7,
        expected_move_pct=3.5,
        expected_range_low=212.3,
        expected_range_high=227.7,
        pin_risk_level="MODERATE",
        gamma_squeeze_risk="MODERATE",
        cascade_drop_risk="LOW",
        updated_at="2026-08-22T23:00:00Z"
    )

    with patch("app.engine.service.get_gexdex_data", return_value={"AAPL": mock_metrics}), \
         patch("app.engine.service.render_gexdex_chart_image", return_value=b"PNG_BYTES"):

        summary = await service.get_summary("AAPL", force_refresh=True)

        assert summary is not None
        assert summary.get("ticker") == "AAPL"
        assert summary.get("spot_price") == 220.0
        assert summary.get("call_wall") == 230.0
        assert summary.get("put_wall") == 210.0
        assert summary.get("zero_gex_level") == 215.0
        assert "Positive" in summary.get("gamma_regime")
        assert summary.get("count") == 1
        assert "AAPL" in summary.get("batch_data")


@pytest.mark.anyio
async def test_gexdex_service_get_chart_image_in_process():
    """Verifies in-process get_chart_image execution."""
    service = GexDexService()

    with patch("app.engine.service.render_gexdex_chart_image", return_value=b"\x89PNG\r\n\x1a\nfakeimage"):
        img_bytes = await service.get_chart_image("AAPL", format="png", force_refresh=True)
        assert img_bytes.startswith(b"\x89PNG")


@pytest.mark.anyio
async def test_calculate_metrics_from_raw():
    """Verifies mathematical calculation of GEX/DEX metrics from raw JSON payload."""
    raw_payload = {
        "spot_price": 100.0,
        "call_wall": 105.0,
        "put_wall": 95.0,
        "call_put_ratio": 2.0,
        "strikes": [
            {
                "strike": 105.0,
                "expirations": {
                    "2026-08-28": {"call_gex": 1000.0, "put_gex": 100.0, "call_dex": 500.0, "put_dex": 50.0}
                }
            },
            {
                "strike": 95.0,
                "expirations": {
                    "2026-08-28": {"call_gex": 200.0, "put_gex": 800.0, "call_dex": 100.0, "put_dex": 400.0}
                }
            }
        ]
    }

    metrics = calculate_metrics_from_raw("TEST", raw_payload)
    assert metrics is not None
    assert metrics.ticker == "TEST"
    assert metrics.spot_price == 100.0
    assert metrics.net_gex == (1200.0 - 900.0)
    assert metrics.call_gex == 1200.0
    assert metrics.put_gex == 900.0
    assert metrics.call_wall == 105.0
    assert metrics.put_wall == 95.0
