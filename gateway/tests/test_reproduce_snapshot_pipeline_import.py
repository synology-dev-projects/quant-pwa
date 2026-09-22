#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gateway/tests/test_reproduce_snapshot_pipeline_import.py

Reproduction test for:
"ModuleNotFoundError: No module named 'app.engine.snapshot_pipeline'"
when executing the GEX/DEX snapshot pipeline via the gateway engine facade
or the daily scheduled pipeline runner (scripts/run_daily_quant_pipelines.sh).
"""
import pytest


def test_reproduce_snapshot_pipeline_facade_import():
    """
    Verifies that 'app.engine.snapshot_pipeline' exists and exports 'run_snapshot_pipeline',
    which can be invoked with force_refresh=True without raising ModuleNotFoundError.
    """
    try:
        from app.engine.snapshot_pipeline import run_snapshot_pipeline
    except ModuleNotFoundError as e:
        pytest.fail(f"Reproduction Confirmed: {e}")

    assert callable(run_snapshot_pipeline), f"Expected callable, got {type(run_snapshot_pipeline)}"
