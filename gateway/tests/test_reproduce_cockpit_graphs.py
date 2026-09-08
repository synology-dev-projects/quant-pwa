import sys
import pytest

def test_reproduce_cockpit_graphs_stopped_working():
    """
    Reproduction test for:
    'The cockpit graphs have stopped working. Mark this as a bug'

    Root Cause:
    When matplotlib is not installed (e.g. inside the gateway container where it was
    purged to save 150MB RAM), importing `common_lib.connectors.tradingedge.dexgex`
    fails at module load time (`from matplotlib.figure import Figure`).
    As a consequence, `app.engine.service` catches the ImportError and sets
    `extract_raw_data = None` and `convert_raw_to_df = None`.
    Thus, `get_strike_distribution(ticker)` receives no raw options data and returns
    `strikes=[]` and `spot_price=0.0`.
    When the frontend Cockpit receives `strikes: []`, `renderExposureChart()` enters the
    empty state:
    'No Active Options Chain / Insufficient Gamma Liquidity for {ticker}'
    and no graphs can be rendered.
    """
    # 1. Simulate the gateway container environment where matplotlib is NOT installed
    orig_matplotlib = sys.modules.get("matplotlib")
    orig_figure = sys.modules.get("matplotlib.figure")
    orig_backend = sys.modules.get("matplotlib.backends.backend_agg")
    
    try:
        # In the gateway container, matplotlib is not installed
        sys.modules["matplotlib"] = None
        sys.modules["matplotlib.figure"] = None
        sys.modules["matplotlib.backends.backend_agg"] = None

        # Verify that importing common_lib.connectors.tradingedge.dexgex fails
        # before the fix, and succeeds after making matplotlib imports lazy/optional
        try:
            # Force reload or fresh import
            if "common_lib.connectors.tradingedge.dexgex" in sys.modules:
                del sys.modules["common_lib.connectors.tradingedge.dexgex"]
            import common_lib.connectors.tradingedge.dexgex as dexgex_mod
            import_ok = True
        except (ModuleNotFoundError, ImportError):
            import_ok = False

        # In RED state, this import fails because matplotlib is imported at top level
        assert import_ok, (
            "DEFECT REPRODUCED: common_lib.connectors.tradingedge.dexgex failed to import "
            "when matplotlib is not installed, causing get_strike_distribution() to have no "
            "extract_raw_data / convert_raw_to_df, returning 0 strikes and killing cockpit graphs!"
        )
        assert hasattr(dexgex_mod, "extract_raw_data") and dexgex_mod.extract_raw_data is not None
        assert hasattr(dexgex_mod, "convert_raw_to_df") and dexgex_mod.convert_raw_to_df is not None

    finally:
        # Restore sys.modules
        if orig_matplotlib is not None:
            sys.modules["matplotlib"] = orig_matplotlib
        elif "matplotlib" in sys.modules:
            del sys.modules["matplotlib"]
            
        if orig_figure is not None:
            sys.modules["matplotlib.figure"] = orig_figure
        elif "matplotlib.figure" in sys.modules:
            del sys.modules["matplotlib.figure"]

        if orig_backend is not None:
            sys.modules["matplotlib.backends.backend_agg"] = orig_backend
        elif "matplotlib.backends.backend_agg" in sys.modules:
            del sys.modules["matplotlib.backends.backend_agg"]
