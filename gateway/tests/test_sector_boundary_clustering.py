"""
Test Hard Macro Sector Boundary Guard in Thematic Options Flow Clustering.
Guarantees that Enterprise Software (PLTR, CRWD, MSFT) and Semiconductors (NVDA, AMD, MU)
never cluster together in the same thematic rotation.
"""

import pytest
from datetime import date
from unittest.mock import MagicMock
import sqlalchemy as sa
from fastapi.testclient import TestClient

from common_lib.flow.clustering import (
    resolve_macro_sector_family,
    cluster_thematic_flow,
)
from app.main import app

client = TestClient(app)


def test_resolve_macro_sector_family_strict_partitions():
    """Validates that key tickers are mapped to distinct, non-overlapping macro families."""
    # Hardware & Semiconductors
    for semi_ticker in ["NVDA", "AMD", "MU", "AVGO", "INTC", "MRVL", "SNDK"]:
        assert resolve_macro_sector_family(None, semi_ticker) == "SEMICONDUCTORS & HARDWARE"

    # Enterprise Software & Cloud
    for soft_ticker in ["PLTR", "CRWD", "MSFT"]:
        assert resolve_macro_sector_family(None, soft_ticker) == "ENTERPRISE SOFTWARE & CLOUD"

    # Consumer Tech & Platforms
    for tech_ticker in ["AAPL", "META", "GOOG", "GOOGL", "AMZN"]:
        assert resolve_macro_sector_family(None, tech_ticker) == "MEGA-CAP PLATFORMS & CONSUMER TECH"

    # Fintech
    for fin_ticker in ["SOFI", "AFRM", "UPST", "COIN"]:
        assert resolve_macro_sector_family(None, fin_ticker) == "FINANCIAL TECHNOLOGY & CRYPTO"


def test_sector_boundary_clustering_prevents_pltr_semi_merger():
    """
    Simulates high text semantic similarity across PLTR, CRWD, NVDA, and AMD.
    Proves that the sector boundary guard forces separation into 2 distinct clusters.
    """
    mock_engine = MagicMock(spec=sa.Engine)
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    flow_rows = [
        ("NVDA", 6000000.0, 5000000.0, 1000000.0, 150),
        ("AMD",  4000000.0, 3000000.0, 1000000.0, 100),
        ("PLTR", 5000000.0, 4500000.0, 500000.0,  120),
        ("CRWD", 3000000.0, 2500000.0, 500000.0,   75),
    ]

    # Shared vector creates 0.0 distance across all pairs
    v_shared = [1.0] + [0.0] * 767

    profile_rows = [
        ("NVDA", "NVIDIA Corp", "Semiconductors & AI Compute", v_shared),
        ("AMD",  "Advanced Micro Devices", "Semiconductors & AI Accelerators", v_shared),
        ("PLTR", "Palantir Technologies", "Enterprise Software & AI Data Infrastructure", v_shared),
        ("CRWD", "CrowdStrike Holdings", "Cybersecurity & Cloud Protection", v_shared),
    ]

    mock_conn.execute.side_effect = [
        MagicMock(fetchall=lambda: flow_rows),
        MagicMock(fetchall=lambda: profile_rows),
    ]

    clusters = cluster_thematic_flow(
        engine=mock_engine,
        trade_date=date(2026, 9, 21),
        min_cluster_premium=1000000.0,
        max_distance=0.35
    )

    assert len(clusters) == 2, f"Expected 2 clusters, got {len(clusters)}"

    clusters_by_family = {c["macro_sector_family"]: c for c in clusters}
    assert "SEMICONDUCTORS & HARDWARE" in clusters_by_family
    assert "ENTERPRISE SOFTWARE & CLOUD" in clusters_by_family

    semi_tickers = {t["ticker"] for t in clusters_by_family["SEMICONDUCTORS & HARDWARE"]["tickers"]}
    soft_tickers = {t["ticker"] for t in clusters_by_family["ENTERPRISE SOFTWARE & CLOUD"]["tickers"]}

    assert semi_tickers == {"NVDA", "AMD"}
    assert soft_tickers == {"PLTR", "CRWD"}
    # Guaranteed disjoint
    assert semi_tickers.isdisjoint(soft_tickers)


def test_api_thematic_clusters_endpoint_includes_macro_family():
    """Verifies that the /api/flow/thematic-clusters response includes macro_sector_family."""
    response = client.get("/api/flow/thematic-clusters?min_premium=500000&max_distance=0.35")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    clusters = data.get("clusters", [])

    for c in clusters:
        assert "macro_sector_family" in c
        assert "dominant_sector" in c
        tickers = {t["ticker"] for t in c["tickers"]}
        # Verify no cluster contains both PLTR and NVDA
        if "PLTR" in tickers:
            assert "NVDA" not in tickers, "PLTR and NVDA must not be in the same cluster"
            assert "AMD" not in tickers, "PLTR and AMD must not be in the same cluster"
            assert c["macro_sector_family"] == "ENTERPRISE SOFTWARE & CLOUD"
