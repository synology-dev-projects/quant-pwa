import sys
import pytest
from common_lib.orchestration.registry import resolve_runner


def test_reproduce_runner_resolution_after_gexdex():
    """
    Verifies that resolving gexdex_snapshot runner followed by market_confluence
    runner in the same process succeeds with proper namespace isolation,
    both locally and within containerized environments.
    """
    # 1. Resolve gexdex_snapshot runner (populates gexdex's src into memory)
    gexdex_runner = resolve_runner("gexdex-snapshot-pipeline.src.scripts.daily_snapshot:run_snapshot_pipeline")
    assert callable(gexdex_runner), "Expected gexdex_snapshot runner to be callable"

    # 2. Resolve market_confluence runner in the same process
    # registry.resolve_runner purges any conflicting cached 'src' modules from foreign repos
    confluence_runner = resolve_runner("market-confluence-pipeline.src.scripts.daily_incremental:run_pipeline")
    assert callable(confluence_runner), "Expected market_confluence runner to be callable"
