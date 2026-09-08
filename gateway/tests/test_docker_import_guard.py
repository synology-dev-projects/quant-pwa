from pathlib import Path
import pytest

def test_reproduce_flags_has_container_guard():
    repro_file = (Path(__file__).parent / 'test_reproduce_architect_flags.py').read_text(encoding='utf-8')
    assert 'DATA_MODELER_DIR.exists()' in repro_file, (
        'test_reproduce_architect_flags.py must verify DATA_MODELER_DIR.exists() before importing'
    )
    assert 'allow_module_level=True' in repro_file, (
        'test_reproduce_architect_flags.py must invoke pytest.skip(allow_module_level=True) when run in Docker containers'
    )
