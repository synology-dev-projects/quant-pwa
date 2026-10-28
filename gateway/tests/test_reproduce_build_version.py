"""
Reproduction test for Quant PWA Version Registry Parity.
Asserts that all version registry files reflect the latest target release (v1.1.45).
Handles container environments where only /app (gateway) is mounted.
"""

import json
from pathlib import Path
import pytest

from app.config import settings

TARGET_VERSION = "v1.1.45"


def test_reproduce_version_registry_is_at_target_version():
    """
    Asserts FastAPI settings.APP_VERSION matches TARGET_VERSION.
    If version.json is present (host workspace), asserts it also matches.
    """
    assert settings.APP_VERSION == TARGET_VERSION, (
        f"FastAPI settings stale! Expected '{TARGET_VERSION}', but settings.APP_VERSION is '{settings.APP_VERSION}'."
    )

    # In host workspace, verify version.json as well
    gateway_dir = Path(__file__).resolve().parent.parent
    quant_pwa_dir = gateway_dir.parent
    version_json_path = quant_pwa_dir / "version.json"
    if version_json_path.exists():
        with open(version_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        actual_version = data.get("version", "").strip()
        assert actual_version == TARGET_VERSION, (
            f"Version registry stale! Expected '{TARGET_VERSION}', but version.json has '{actual_version}'."
        )
