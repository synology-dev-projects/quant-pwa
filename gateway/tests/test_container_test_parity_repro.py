from pathlib import Path
import pytest

def test_reproduce_protocol_graph_has_container_guard():
    pg_test = (Path(__file__).parent / 'test_protocol_graph.py').read_text(encoding='utf-8')
    assert 'allow_module_level=True' in pg_test, (
        'test_protocol_graph.py must guard when scripts/protocol_graph.py is not mounted in container'
    )

def test_reproduce_version_parity_fallback_supports_current_major():
    gw_test = (Path(__file__).parent / 'test_gateway.py').read_text(encoding='utf-8')
    assert 'v1.0.' not in gw_test, (
        'test_gateway.py must not hardcode obsolete v1.0. fallback in test_version_parity_with_version_json'
    )
