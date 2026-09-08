import sys
from pathlib import Path
import pytest

DATA_MODELER_DIR = Path(r"C:\Coding\VSCode\Quant System\archive\data-modeler-engine")
if not DATA_MODELER_DIR.exists():
    pytest.skip("archive/data-modeler-engine not mounted in container environment", allow_module_level=True)

if str(DATA_MODELER_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_MODELER_DIR))

from src.models import TableSpec, ColumnSpec, HypertableConfig
from src.temporal_engine import TemporalEngine
from src.ddl_generator import DDLGenerator
from src.synthetic_harness import SyntheticHarness


def test_reproduce_ts_pk_01_hypertable_composite_primary_key():
    """
    [RED Reproduction for TS-PK-01]
    TimescaleDB hypertables require that primary keys include the partition time column ('snapshot_time').
    When augment_table_spec_scd2 augments a hypertable, the resulting TableSpec primary_keys
    must be composite ['surrogate_key', 'snapshot_time'], not purely ['surrogate_key'].
    """
    table = TableSpec(
        schema_name="quant",
        table_name="options_chain_snapshot",
        columns=[
            ColumnSpec(name="symbol", data_type="VARCHAR(16)", nullable=False, is_business_key=True),
            ColumnSpec(name="snapshot_time", data_type="TIMESTAMPTZ", nullable=False),
        ],
        hypertable_config=HypertableConfig(time_column="snapshot_time", chunk_time_interval="7 days"),
        primary_keys=["symbol", "snapshot_time"]
    )

    temporal_engine = TemporalEngine()
    augmented = temporal_engine.augment_table_spec_scd2(table)

    # In TimescaleDB, unique/PK constraints on hypertables MUST include the partition column 'snapshot_time'
    assert "snapshot_time" in augmented.primary_keys, "TS-PK-01: Hypertable SCD2 primary_keys must include partition time_column"
    assert augmented.primary_keys == ["surrogate_key", "snapshot_time"]

    # The generated DDL must contain composite primary key
    ddl = DDLGenerator().generate_table_ddl(augmented)
    assert 'PRIMARY KEY ("surrogate_key", "snapshot_time")' in ddl, "TS-PK-01: DDL must declare composite primary key"


def test_reproduce_mem_str_02_memory_bounded_streaming():
    """
    [RED Reproduction for MEM-STR-02]
    SyntheticHarness must implement generate_records_stream() yielding batched chunks
    to avoid OOM on Synology NAS when generating 100k+ records.
    """
    harness = SyntheticHarness(seed=42)
    assert hasattr(harness, "generate_records_stream"), "MEM-STR-02: SyntheticHarness must implement generate_records_stream()"

    table = TableSpec(
        schema_name="quant",
        table_name="test_stream",
        columns=[
            ColumnSpec(name="symbol", data_type="VARCHAR(16)", nullable=False, is_business_key=True),
            ColumnSpec(name="created_at", data_type="TIMESTAMPTZ", nullable=False),
        ]
    )

    batches = list(harness.generate_records_stream(table, count=25000, batch_size=10000))
    assert len(batches) == 3
    assert len(batches[0]) == 10000
    assert len(batches[1]) == 10000
    assert len(batches[2]) == 5000
