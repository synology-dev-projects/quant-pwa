import pytest
import pandas as pd
from unittest.mock import patch
from app.routers.cockpit import get_cockpit_full_payload, _calculate_cockpit_metrics, _format_flow_records
from app.engine.service import StrikeDistributionResponse, StrikeDetail

def test_cockpit_payload_rejects_zero_or_null_strike_flow():
    """
    [RED Reproduction for Zero-Strike Cockpit Flow Bug]
    When database contains phantom footer rows with strike_price = 0.0 or None,
    the Cockpit API must filter them out from flow records and metrics.
    """
    mock_dist = StrikeDistributionResponse(
        ticker="POWL",
        spot_price=179.73,
        call_wall=190.0,
        put_wall=170.0,
        zero_gex_level=175.0,
        gamma_centroid=180.0,
        call_put_ratio=1.2,
        gamma_regime="Long Gamma",
        net_gex=1000000.0,
        net_dex=500000.0,
        expirations=["2026-09-18"],
        strikes=[
            StrikeDetail(strike=180.0, call_gex=800000.0, put_gex=-200000.0, call_dex=400000.0, put_dex=-100000.0, net_gex=600000.0, net_dex=300000.0),
        ],
        updated_at="2026-09-07T14:00:00Z"
    )

    # Simulated DataFrame containing 1 authentic print and 2 phantom footer rows with strike 0 / None
    mock_flow_df = pd.DataFrame([
        {
            "FLOW_ID": "valid_1",
            "TRADE_DATE": "2026-08-21",
            "SYMBOL": "POWL",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 240.0,
            "STRIKE_OTM_PCT": 21.0,
            "EXPIRATION_DATE": "2027-02-19",
            "OPEN_INTEREST": 1159,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 3300000.0,
            "NET_SCORE": 0.0
        },
        {
            "FLOW_ID": "footer_phantom_1",
            "TRADE_DATE": "2026-09-01",
            "SYMBOL": "POWL",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": 0.0,
            "STRIKE_OTM_PCT": None,
            "EXPIRATION_DATE": "2026-09-01",
            "OPEN_INTEREST": 0,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 11500000.0,
            "NET_SCORE": 0.0
        },
        {
            "FLOW_ID": "footer_phantom_2",
            "TRADE_DATE": "2026-08-30",
            "SYMBOL": "POWL",
            "ORDER_TYPE": "BUY_CALL",
            "STRIKE_PRICE": None,
            "STRIKE_OTM_PCT": None,
            "EXPIRATION_DATE": "2026-08-30",
            "OPEN_INTEREST": 0,
            "IS_UNUSUAL_OI": 0,
            "PREMIUM": 11000000.0,
            "NET_SCORE": 0.0
        }
    ])

    with patch("app.routers.cockpit.get_strike_distribution", return_value=mock_dist), \
         patch("app.routers.cockpit._fetch_postgres_flow_sync", return_value=mock_flow_df):
        import anyio
        async def _run():
            return await get_cockpit_full_payload("POWL", force_refresh=True)
        payload = anyio.run(_run)

        flow_records = payload["flow"]["records"]
        # Must only contain the valid strike (240.0), phantom strike 0 rows must be excluded
        assert len(flow_records) == 1, f"Expected 1 valid record, got {len(flow_records)}: {flow_records}"
        assert flow_records[0]["STRIKE_PRICE"] == 240.0
        assert flow_records[0]["PREMIUM"] == 3300000.0

        # Metrics must not double count the 11.5M and 11.0M footer duplicates
        metrics = payload["metrics"]
        assert metrics["total_30d_flow_volume"] == 3300000.0, f"Expected 3.3M, got {metrics['total_30d_flow_volume']}"
        assert metrics["whale_count"] == 1, f"Expected 1 whale print, got {metrics['whale_count']}"

def test_pipeline_transform_skips_zero_strike():
    """
    [RED Reproduction for Pipeline Ingestion]
    transform_flow_records must skip raw records where strike is <= 0 or missing.
    """
    try:
        from common_lib.flow.transform import transform_flow_records
    except ImportError:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "common-lib"))
        from common_lib.flow.transform import transform_flow_records

    raw_items = [
        {"symbol": "POWL", "strike": "240.00 (21 %)", "premium": "3.3M", "trade_date": "2026-08-21", "order_type": "Buy Call"},
        {"symbol": "POWL", "strike": "", "premium": "11.5M", "trade_date": "2026-09-01", "order_type": "Buy Call"},
        {"symbol": "POWL", "strike": "0", "premium": "11.0M", "trade_date": "2026-08-30", "order_type": "Buy Call"},
    ]
    df = transform_flow_records(raw_items)
    assert len(df) == 1, f"Expected 1 record, got {len(df)}"
    assert df.iloc[0]["strike_price"] == 240.0
