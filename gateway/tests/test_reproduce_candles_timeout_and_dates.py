import sys
from pathlib import Path
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app

# Ensure quant-pwa root is on sys.path to import scripts.smoke_test
_quant_pwa_root = Path(__file__).resolve().parent.parent.parent
if str(_quant_pwa_root) not in sys.path:
    sys.path.insert(0, str(_quant_pwa_root))

import scripts.smoke_test as smoke_test

client = TestClient(app)


def test_reproduce_dates_uppercase_column_keyerror():
    """
    Reproduces KeyError: 'd' when postgres.sql returns DataFrame with uppercase columns ('D').
    In postgres.sql: df.columns = df.columns.str.upper().
    Expected: dates list is successfully parsed from the DataFrame.
    """
    df_uppercase = pd.DataFrame({"D": [pd.Timestamp("2026-10-21 00:00:00")]})
    with patch("common_lib.connectors.postgres.sql", return_value=df_uppercase):
        response = client.get("/api/quant-levels/dates?ticker=SPX")
        assert response.status_code == 200
        # If the bug is present, row["d"] fails and returns []
        data = response.json()
        assert len(data) > 0, "Failed to parse dates due to uppercase column 'D'"
        assert data[0] == "2026-10-21"


def test_reproduce_smoke_test_default_timeout_failure():
    """
    Reproduces smoke test default timeout failing on an external probe taking > 5.0 seconds.
    The default timeout in scripts/smoke_test.py is 5.0, which causes cold-start probes
    exceeding 5.0s to fail and trigger deployment rollback.
    """
    assert smoke_test.probe_endpoint.__defaults__[1] >= 15.0, (
        f"Default smoke test timeout is {smoke_test.probe_endpoint.__defaults__[1]}s, "
        "must be at least 15.0s to tolerate cold-start external queries."
    )
