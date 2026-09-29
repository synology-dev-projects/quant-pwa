import sys
import pytest

def test_dexgex_importable_without_matplotlib(monkeypatch):
    """Bug reproduction: dexgex connector must be importable even if matplotlib is not installed."""
    monkeypatch.setitem(sys.modules, 'matplotlib', None)
    monkeypatch.setitem(sys.modules, 'matplotlib.figure', None)
    monkeypatch.setitem(sys.modules, 'matplotlib.backends.backend_agg', None)
    monkeypatch.setitem(sys.modules, 'matplotlib.patches', None)
    monkeypatch.setitem(sys.modules, 'matplotlib.ticker', None)

    if 'common_lib.connectors.tradingedge.dexgex' in sys.modules:
        del sys.modules['common_lib.connectors.tradingedge.dexgex']

    import common_lib.connectors.tradingedge.dexgex as dexgex
    assert hasattr(dexgex, 'extract_raw_data')
    assert callable(dexgex.extract_raw_data)
