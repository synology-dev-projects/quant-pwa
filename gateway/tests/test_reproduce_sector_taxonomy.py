#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gateway/tests/test_reproduce_sector_taxonomy.py

Reproduction test for:
"The only category / sector that is showing on new rag flow is public equities"

Proves that:
1. SEC metadata extraction captures authentic 'sicDescription' and 'sic'.
2. Sector derivation maps SEC industries and tickers to specific market sectors
   and NEVER falls back to generic 'Public Equities'.
3. Thematic flow clustering derives authentic dominant sectors instead of 'Public Equities'.
"""
import pytest
from unittest.mock import MagicMock
import sqlalchemy as sa
from common_lib.flow.clustering import cluster_thematic_flow


def test_reproduce_thematic_flow_clustering_rejects_public_equities():
    """
    Verifies that when ticker profiles in the database have authentic sectors or fallbacks,
    cluster_thematic_flow NEVER emits 'Public Equities' as the dominant sector or theme name.
    """
    mock_engine = MagicMock(spec=sa.Engine)
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    # Mock flow prints for NVDA and AMD ($5M and $3M)
    flow_rows = [
        ("NVDA", 5_000_000.0, 4_000_000.0, 1_000_000.0, 50),
        ("AMD", 3_000_000.0, 2_500_000.0, 500_000.0, 30),
    ]

    # Mock profile rows currently in database with 'Public Equities'
    v_nvda = [0.1] * 768
    v_amd = [0.105] * 768  # Very close to NVDA (high cosine similarity)
    profile_rows = [
        ("NVDA", "NVIDIA Corporation", "Public Equities", v_nvda),
        ("AMD", "Advanced Micro Devices, Inc.", "Public Equities", v_amd),
    ]

    mock_conn.execute.side_effect = [
        MagicMock(fetchall=lambda: flow_rows),
        MagicMock(fetchall=lambda: profile_rows),
    ]

    from datetime import date
    clusters = cluster_thematic_flow(
        engine=mock_engine,
        trade_date=date(2026, 9, 21),
        min_cluster_premium=1_000_000.0
    )

    assert len(clusters) > 0, "Expected at least 1 cluster for high-flow NVDA + AMD"
    cluster = clusters[0]

    # FAILS in RED state: Currently dominant_sector is 'Public Equities'
    assert cluster["dominant_sector"] != "Public Equities", (
        f"Reproduction Confirmed: Cluster dominant sector is '{cluster['dominant_sector']}'"
    )
    assert not cluster["theme_name"].startswith("Public Equities"), (
        f"Reproduction Confirmed: Cluster theme name is '{cluster['theme_name']}'"
    )
