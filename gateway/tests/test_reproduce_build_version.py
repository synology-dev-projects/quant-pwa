"""
Reproduction test for Quant PWA Version Registry Parity.
Asserts that all version registry files reflect the latest target release dynamically.
Handles container environments where only /app (gateway) is mounted.
"""

import json
from pathlib import Path
import pytest

from app.config import settings


def test_reproduce_version_registry_is_at_target_version():
    """
    Asserts FastAPI settings.APP_VERSION and APP_BUILD match version.json dynamically.
    """
    gateway_dir = Path(__file__).resolve().parent.parent
    quant_pwa_dir = gateway_dir.parent
    version_json_path = quant_pwa_dir / "version.json"
    if not version_json_path.exists():
        version_json_path = Path("/app/version.json")

    if version_json_path.exists():
        with open(version_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        expected_version = data.get("version", "").strip()
        expected_build = data.get("build", "").strip()

        assert settings.APP_VERSION == expected_version, (
            f"FastAPI settings stale! Expected '{expected_version}', but settings.APP_VERSION is '{settings.APP_VERSION}'."
        )
        if hasattr(settings, "APP_BUILD") and expected_build:
            assert settings.APP_BUILD == expected_build, (
                f"FastAPI APP_BUILD stale! Expected '{expected_build}', but settings.APP_BUILD is '{settings.APP_BUILD}'."
            )
    else:
        assert bool(settings.APP_VERSION), "settings.APP_VERSION must not be empty"
