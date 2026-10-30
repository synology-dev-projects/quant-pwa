"""
Reproduction Test: Build Number & Version Increment Lifecycle (BUG-010).
Proves the defect:
1. build in version.json is stale (not matching current day) and lacks dynamic synchronization in config.py / settings_modal.js.
2. gateway Settings lacks APP_BUILD attribute.
3. settings_modal.js lacks CLIENT_BUILD export.
4. test_reproduce_build_version.py contains a frozen hardcoded TARGET_VERSION blocking incrementation.
Handles container environments where only /app (gateway) is mounted.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest

GATEWAY_DIR = Path(__file__).resolve().parent.parent
CONFIG_PY = GATEWAY_DIR / "app" / "config.py"
FROZEN_TEST_PY = GATEWAY_DIR / "tests" / "test_reproduce_build_version.py"


def test_reproduce_build_number_and_version_synchronization():
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Assert gateway Settings has APP_BUILD exposed and formatted with today's date
    from app.config import settings
    assert hasattr(settings, "APP_BUILD"), "FastAPI settings must expose APP_BUILD attribute."
    assert settings.APP_BUILD.startswith(today_prefix), (
        f"APP_BUILD is stale or invalid! Expected prefix '{today_prefix}', got '{getattr(settings, 'APP_BUILD', None)}'."
    )
    assert "APP_BUILD" in CONFIG_PY.read_text(encoding="utf-8"), (
        "config.py must declare APP_BUILD setting."
    )

    # 2. Assert test_reproduce_build_version.py is dynamic and not hardcoded to a frozen version
    assert FROZEN_TEST_PY.exists(), "test_reproduce_build_version.py must exist."
    frozen_test_content = FROZEN_TEST_PY.read_text(encoding="utf-8")
    assert 'TARGET_VERSION = "v1.1.45"' not in frozen_test_content, (
        "test_reproduce_build_version.py must not hardcode frozen TARGET_VERSION = 'v1.1.45'."
    )

    # 3. Locate version.json across candidate paths (supports local workspace and container mounts)
    candidates = [
        GATEWAY_DIR.parent / "version.json",
        GATEWAY_DIR / "version.json",
        Path("/app/version.json"),
        Path("version.json"),
        Path("/volume2/homes/rachardv/git-repos/develop2/quant-pwa/version.json"),
        Path("/volume2/homes/rachardv/git-repos/master/quant-pwa/version.json"),
    ]
    version_file = next((p for p in candidates if p.exists()), None)
    if version_file:
        data = json.loads(version_file.read_text(encoding="utf-8"))
        build_str = data.get("build", "")
        assert build_str.startswith(today_prefix), (
            f"Build number is stale! Expected prefix '{today_prefix}', but version.json has '{build_str}'."
        )
        assert settings.APP_BUILD == build_str, (
            f"APP_BUILD mismatch! settings has '{settings.APP_BUILD}', version.json has '{build_str}'."
        )

    # 4. If frontend source exists in environment, verify settings_modal.js exports CLIENT_BUILD
    settings_modal_js = GATEWAY_DIR.parent / "frontend" / "src" / "components" / "settings_modal.js"
    if settings_modal_js.exists():
        settings_js_content = settings_modal_js.read_text(encoding="utf-8")
        assert "export const CLIENT_BUILD" in settings_js_content, (
            "settings_modal.js must export CLIENT_BUILD."
        )

