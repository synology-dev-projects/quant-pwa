#!/usr/bin/env python3
"""
Automated Version Registry & Synchronization Script for Quant PWA System.

Validates and updates version across:
1. version.json (Root registry)
2. gateway/app/config.py (FastAPI Gateway backend)
3. frontend/src/components/settings_modal.js (Client component version)
4. frontend/sw.js (Service Worker cache namespace)
5. frontend/index.html (HTML build labels and asset cache-busters)
"""

import sys
import os
import re
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

VERSION_JSON = ROOT_DIR / "version.json"
CONFIG_PY = ROOT_DIR / "gateway" / "app" / "config.py"
SETTINGS_MODAL_JS = ROOT_DIR / "frontend" / "src" / "components" / "settings_modal.js"
SW_JS = ROOT_DIR / "frontend" / "sw.js"
INDEX_HTML = ROOT_DIR / "frontend" / "index.html"


def get_version_json_version(content: str) -> str:
    data = json.loads(content)
    return data.get("version", "").strip()


def get_config_py_version(content: str) -> str:
    match = re.search(r'APP_VERSION:\s*str\s*=\s*os\.getenv\("APP_VERSION",\s*"([^"]+)"\)', content)
    return match.group(1).strip() if match else ""


def get_settings_modal_version(content: str) -> str:
    match = re.search(r"export\s+const\s+CLIENT_VERSION\s*=\s*['\"]([^'\"]+)['\"];?", content)
    return match.group(1).strip() if match else ""


def get_sw_version(content: str) -> str:
    match = re.search(r"const\s+CACHE_NAME\s*=\s*['\"]quant-ai-([^'\"]+)['\"];?", content)
    return match.group(1).strip() if match else ""


def get_index_html_version(content: str) -> str:
    match = re.search(r'id=["\']appBuildVersion["\']>\s*([^<\s\(]+)', content)
    return match.group(1).strip() if match else ""


def read_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required file does not exist: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def check_version_parity() -> int:
    files = {
        "version.json": (VERSION_JSON, get_version_json_version),
        "gateway/app/config.py": (CONFIG_PY, get_config_py_version),
        "frontend/src/components/settings_modal.js": (SETTINGS_MODAL_JS, get_settings_modal_version),
        "frontend/sw.js": (SW_JS, get_sw_version),
        "frontend/index.html": (INDEX_HTML, get_index_html_version),
    }

    versions = {}
    errors = []

    for name, (path, extractor) in files.items():
        try:
            content = read_file(path)
            ver = extractor(content)
            if not ver:
                errors.append(f"Could not extract version from {name}")
            versions[name] = ver
        except Exception as e:
            errors.append(f"Failed reading {name}: {e}")

    print("\n--- QUANT PWA VERSION PARITY STATUS ---")
    for name, ver in versions.items():
        print(f"  {name.ljust(45)}: {ver or 'ERROR'}")

    if errors:
        print("\n[FAILED] Extraction errors encountered:")
        for err in errors:
            print(f"  - {err}")
        return 1

    distinct_versions = set(versions.values())
    if len(distinct_versions) == 1 and "" not in distinct_versions:
        matched_ver = next(iter(distinct_versions))
        print(f"\n[PARITY OK] All 5 files strictly synchronized at version: {matched_ver}\n")
        return 0
    else:
        print(f"\n[PARITY DRIFT DETECTED] Found mismatched versions: {distinct_versions}\n")
        return 1


def increment_patch_version(current: str) -> str:
    match = re.match(r"^(v?)(\d+)\.(\d+)\.(\d+)$", current.strip())
    if not match:
        raise ValueError(f"Cannot auto-increment non-semver version: '{current}'")
    prefix, major, minor, patch = match.groups()
    return f"{prefix or 'v'}{major}.{minor}.{int(patch) + 1}"


def update_all_files(target_version: str) -> None:
    if not target_version.startswith("v") and re.match(r"^\d+\.\d+", target_version):
        target_version = f"v{target_version}"

    print(f"Bumping Quant PWA version to: {target_version}")

    # 1. version.json
    raw_json = read_file(VERSION_JSON)
    try:
        json_obj = json.loads(raw_json)
    except Exception:
        json_obj = {}
    json_obj["version"] = target_version
    json_obj["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_json_str = json.dumps(json_obj, indent=2) + "\n"

    # 2. gateway/app/config.py
    raw_config = read_file(CONFIG_PY)
    new_config = re.sub(
        r'(APP_VERSION:\s*str\s*=\s*os\.getenv\("APP_VERSION",\s*")[^"]+("\))',
        rf'\g<1>{target_version}\g<2>',
        raw_config,
    )

    # 3. frontend/src/components/settings_modal.js
    raw_settings = read_file(SETTINGS_MODAL_JS)
    new_settings = re.sub(
        r"(export\s+const\s+CLIENT_VERSION\s*=\s*['\"])[^'\"]+(['\"];?)",
        rf'\g<1>{target_version}\g<2>',
        raw_settings,
    )

    # 4. frontend/sw.js
    raw_sw = read_file(SW_JS)
    new_sw = re.sub(
        r"(const\s+CACHE_NAME\s*=\s*['\"]quant-ai-)[^'\"]+(['\"];?)",
        rf'\g<1>{target_version}\g<2>',
        raw_sw,
    )

    # 5. frontend/index.html
    raw_html = read_file(INDEX_HTML)
    new_html = re.sub(
        r'(href=["\']styles\.css\?v=)[^"\'\s>]+(["\'])',
        rf'\g<1>{target_version}\g<2>',
        raw_html,
    )
    new_html = re.sub(
        r'(src=["\']src/app\.js\?v=)[^"\'\s>]+(["\'])',
        rf'\g<1>{target_version}\g<2>',
        new_html,
    )
    new_html = re.sub(
        r'(id=["\']appBuildVersion["\']>)[^<\(]*\s*(\([^\)]+\)</span>)',
        rf'\g<1>{target_version} \g<2>',
        new_html,
    )
    new_html = re.sub(
        r'(id=["\']syncStatusText["\']>Synchronized \()[^\)]+(\)</span>)',
        rf'\g<1>{target_version}\g<2>',
        new_html,
    )
    new_html = re.sub(
        r'(id=["\']forceUpdateBtn["\'][^>]*>✓ App Up to Date \()[^\)]+(\)</button>)',
        rf'\g<1>{target_version}\g<2>',
        new_html,
    )

    # Atomic write-out
    write_file(VERSION_JSON, new_json_str)
    write_file(CONFIG_PY, new_config)
    write_file(SETTINGS_MODAL_JS, new_settings)
    write_file(SW_JS, new_sw)
    write_file(INDEX_HTML, new_html)

    print("Atomically updated all 5 files successfully.")


def main():
    parser = argparse.ArgumentParser(description="Manage Quant PWA Version Registry")
    parser.add_argument("--check", action="store_true", help="Check parity across all version files")
    parser.add_argument("--set", dest="set_version", type=str, help="Set explicit version string (e.g. v1.0.2)")

    args = parser.parse_args()

    if args.check:
        sys.exit(check_version_parity())

    if args.set_version:
        target_version = args.set_version.strip()
    else:
        # Default increment last patch digit
        current_content = read_file(VERSION_JSON)
        current_version = get_version_json_version(current_content)
        if not current_version:
            print("[ERROR] Could not read current version from version.json")
            sys.exit(1)
        target_version = increment_patch_version(current_version)

    update_all_files(target_version)
    sys.exit(check_version_parity())


if __name__ == "__main__":
    main()
