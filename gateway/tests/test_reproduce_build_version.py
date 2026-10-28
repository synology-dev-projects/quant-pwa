"""
Reproduction test for Quant PWA Version Registry Parity.
Asserts that all version registry files reflect the latest target release (v1.1.45).
"""

import json
import re
from pathlib import Path
import pytest


GATEWAY_DIR = Path(__file__).resolve().parent.parent
QUANT_PWA_DIR = GATEWAY_DIR.parent
TARGET_VERSION = "v1.1.45"


def test_reproduce_version_registry_is_at_target_version():
    """
    Fails if the version registry files are still stuck at older versions (e.g. v1.1.42).
    """
    version_json_path = QUANT_PWA_DIR / "version.json"
    assert version_json_path.exists(), f"Missing {version_json_path}"
    with open(version_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    actual_version = data.get("version", "").strip()

    assert actual_version == TARGET_VERSION, (
        f"Version registry stale! Expected '{TARGET_VERSION}', but version.json has '{actual_version}'."
    )

    from app.config import settings
    assert settings.APP_VERSION == TARGET_VERSION, (
        f"FastAPI settings stale! Expected '{TARGET_VERSION}', but settings.APP_VERSION is '{settings.APP_VERSION}'."
    )
