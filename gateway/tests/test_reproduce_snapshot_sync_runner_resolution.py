#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gateway/tests/test_reproduce_snapshot_sync_runner_resolution.py

Reproduction test for:
"Sync failed: Snapshot pipeline execution failed: Failed to resolve runner
'gexdex-snapshot-pipeline.src.scripts.daily_snapshot:run_snapshot_pipeline': No module named 'src'"

Proves that resolve_runner("gexdex_snapshot") dynamically discovers and imports
the runner from gexdex-snapshot-pipeline without raising 'No module named src'.
"""
import sys
from pathlib import Path
import pytest
from common_lib.orchestration.registry import PIPELINE_DAG, resolve_runner


def test_reproduce_gexdex_snapshot_runner_resolution():
    """
    Verifies that resolve_runner resolves PIPELINE_DAG['gexdex_snapshot']['runner']
    to an authentic callable function without failing on 'No module named src'.
    """
    runner_spec = PIPELINE_DAG["gexdex_snapshot"]["runner"]
    assert "gexdex-snapshot-pipeline" in runner_spec

    # This MUST resolve cleanly to a callable function
    runner = resolve_runner(runner_spec)
    assert callable(runner), f"Expected callable runner, got {type(runner)}"
    assert runner.__name__ in ("run_snapshot_pipeline", "run_pipeline")
