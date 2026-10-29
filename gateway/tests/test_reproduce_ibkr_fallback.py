import sys
import pytest
from unittest.mock import patch
import pandas as pd

def test_reproduce_ibkr_fallback_without_optional_dependencies():
    """
    REPRODUCTION TEST: Cockpit IBKR Strike Distribution in Production Gateway
    Production Invariant: The Gateway environment does NOT have pipeline socket dependencies
    (`ib_async`) or scientific libraries (`scipy`) installed in requirements.txt / Dockerfile.
    Calculators and CBOE strike distributions must execute purely on Python/NumPy.

    Expected: recompute_dynamic_bsm_gexdex and get_ibkr_strike_distribution execute without
              ib_async or scipy, returning authentic CBOE strike distributions.
    Actual:   Importing fails with ModuleNotFoundError ('ib_async' or 'scipy'),
              causing get_ibkr_strike_distribution to fall back to synthetic mock data.
    """
    # 1. Simulate the production Docker environment where ib_async and scipy are not installed
    # Purge any cached common_lib modules so imports re-evaluate with blocked modules
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("common_lib") or "ib_async" in mod_name or "scipy" in mod_name:
            del sys.modules[mod_name]

    sys.modules["ib_async"] = None
    sys.modules["scipy"] = None
    sys.modules["scipy.stats"] = None

    # Step 1: Importing recompute_dynamic_bsm_gexdex must succeed without ib_async or scipy
    from common_lib.calculators.gexdex import recompute_dynamic_bsm_gexdex

    # Step 2: Running calculation on sample contracts must work without scipy
    df = pd.DataFrame([
        {"strike": 570.0, "expiration": "20261120", "option_type": "C", "open_interest": 100.0, "iv": 0.20},
        {"strike": 580.0, "expiration": "20261120", "option_type": "C", "open_interest": 200.0, "iv": 0.18},
        {"strike": 570.0, "expiration": "20261120", "option_type": "P", "open_interest": 150.0, "iv": 0.22},
        {"strike": 580.0, "expiration": "20261120", "option_type": "P", "open_interest": 250.0, "iv": 0.19},
    ])
    calc_res = recompute_dynamic_bsm_gexdex(df, spot_live=580.0, spot_close=580.0)
    assert not calc_res.empty
    assert "gex_live" in calc_res.columns
    assert "dex_live" in calc_res.columns

    # Step 3: Verify get_ibkr_strike_distribution uses real CBOE data instead of fallback
    from app.engine.service import get_ibkr_strike_distribution, _IBKR_STRIKE_CACHE
    _IBKR_STRIKE_CACHE.clear()

    mock_cboe = {
        ("20261120", 570.0, "C"): {"open_interest": 100.0, "iv": 0.20, "und_price": 580.0},
        ("20261120", 580.0, "C"): {"open_interest": 200.0, "iv": 0.18, "und_price": 580.0},
        ("20261120", 570.0, "P"): {"open_interest": 150.0, "iv": 0.22, "und_price": 580.0},
        ("20261120", 580.0, "P"): {"open_interest": 250.0, "iv": 0.19, "und_price": 580.0},
    }
    with patch("common_lib.connectors.cboe_oi.fetch_cboe_delayed_data", return_value=mock_cboe):
        dist = get_ibkr_strike_distribution("SPY", force_refresh=True, spot_hint=580.0)
        strike_vals = [s.strike for s in dist.strikes]
        assert 570.0 in strike_vals and 580.0 in strike_vals
        assert len(strike_vals) == 2, f"Expected 2 strikes from mock CBOE data, got {len(strike_vals)} (fallback invoked)"
