"""
Reproduction Test: Build Number & Version Increment Lifecycle (BUG-010).
Proves the defect:
1. build in version.json is stale (not matching current day) and lacks dynamic synchronization in config.py / settings_modal.js.
2. gateway Settings lacks APP_BUILD attribute.
3. settings_modal.js lacks CLIENT_BUILD export.
4. test_reproduce_build_version.py contains a frozen hardcoded TARGET_VERSION blocking incrementation.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest

GATEWAY_DIR = Path(__file__).resolve().parent.parent
QUANT_PWA_DIR = GATEWAY_DIR.parent
VERSION_JSON = QUANT_PWA_DIR / "version.json"
CONFIG_PY = GATEWAY_DIR / "app" / "config.py"
SETTINGS_MODAL_JS = QUANT_PWA_DIR / "frontend" / "src" / "components" / "settings_modal.js"
FROZEN_TEST_PY = GATEWAY_DIR / "tests" / "test_reproduce_build_version.py"


def test_reproduce_build_number_and_version_synchronization():
    # 1. Assert version.json has today's build date
    assert VERSION_JSON.exists(), "version.json must exist"
    data = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    build_str = data.get("build", "")
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Failing assertion: build_str is currently stuck at '2026-10-28-01'
    assert build_str.startswith(today_prefix), (
        f"Build number is stale! Expected prefix '{today_prefix}', but version.json has '{build_str}'."
    )

    # 2. Assert gateway Settings has APP_BUILD exposed
    from app.config import settings
    assert hasattr(settings, "APP_BUILD"), "FastAPI settings must expose APP_BUILD attribute."
    assert settings.APP_BUILD == build_str, (
        f"APP_BUILD mismatch! settings has '{getattr(settings, 'APP_BUILD', None)}', version.json has '{build_str}'."
    )

    # 3. Assert settings_modal.js exports CLIENT_BUILD matching build_str
    settings_js_content = SETTINGS_MODAL_JS.read_text(encoding="utf-8")
    assert "export const CLIENT_BUILD" in settings_js_content, (
        "settings_modal.js must export CLIENT_BUILD."
    )

    # 4. Assert test_reproduce_build_version.py is dynamic and not hardcoded to a frozen version
    frozen_test_content = FROZEN_TEST_PY.read_text(encoding="utf-8")
    assert 'TARGET_VERSION = "v1.1.45"' not in frozen_test_content, (
        "test_reproduce_build_version.py must not hardcode frozen TARGET_VERSION = 'v1.1.45'."
    )
