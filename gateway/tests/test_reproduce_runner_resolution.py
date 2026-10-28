import sys
from pathlib import Path
import pytest
from common_lib.orchestration.registry import resolve_runner


def test_reproduce_runner_resolution_after_gexdex():
    """
    Reproduction test proving that when gexdex_snapshot runs first and binds
    sys.modules['src'], subsequent resolution of market_confluence runner fails
    with ModuleNotFoundError / ImportError: No module named 'src.scripts.daily_incremental'.
    """
    # 1. Preload gexdex_snapshot's src into sys.modules (as happens during DAG execution)
    gexdex_path = Path(__file__).resolve().parent.parent.parent.parent / "gexdex-snapshot-pipeline"
    if str(gexdex_path) not in sys.path:
        sys.path.insert(0, str(gexdex_path))

    import src
    import src.scripts.daily_snapshot

    assert "src" in sys.modules
    assert "gexdex-snapshot-pipeline" in sys.modules["src"].__file__

    # 2. In unpatched code, resolving market_confluence will fail because Python searches
    # inside gexdex-snapshot-pipeline/src for scripts.daily_incremental
    confluence_runner = resolve_runner("market-confluence-pipeline.src.scripts.daily_incremental:run_pipeline")
    assert callable(confluence_runner), "Expected market_confluence runner to be callable"
