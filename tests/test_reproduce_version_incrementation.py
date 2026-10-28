import sys
from pathlib import Path
from datetime import datetime, timezone

# Add quant-pwa to sys.path so we can import scripts.bump_version
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from scripts.bump_version import increment_patch_version

def test_rollover_when_patch_reaches_ten():
    # 2.1.9 -> patch becomes 10, so rolls over to 2.2.0
    assert increment_patch_version("2.1.9") == "v2.2.0"

def test_rollover_when_patch_is_already_ten():
    # User requirement: "ie 2.1.10 should be 2.2.0"
    assert increment_patch_version("2.1.10") == "v2.2.0"

def test_cascading_rollover():
    # 1.9.9 -> patch 10 -> min 10 -> 2.0.0
    assert increment_patch_version("1.9.9") == "v2.0.0"

def test_build_number_incrementation():
    # Test build number generation and incrementation helper
    import scripts.bump_version as bv
    assert hasattr(bv, "get_next_build_number"), "get_next_build_number not implemented in bump_version.py"
    fixed_time = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
    # First build of new date
    assert bv.get_next_build_number("2026-10-27-01", now_dt=fixed_time) == "2026-10-28-01"
    # Sequential build on same date
    assert bv.get_next_build_number("2026-10-28-01", now_dt=fixed_time) == "2026-10-28-02"

if __name__ == "__main__":
    test_rollover_when_patch_reaches_ten()
    test_rollover_when_patch_is_already_ten()
    test_cascading_rollover()
    test_build_number_incrementation()
    print("All tests passed.")
