"""
Backward-compatible adapter for GEX/DEX snapshot pipeline runner.
Delegates dynamically to the registered PIPELINE_DAG runner in gexdex-snapshot-pipeline.
"""
import logging
from typing import Any, Tuple, Optional
from common_lib.config.main_config import load_config
from common_lib.orchestration.registry import PIPELINE_DAG, resolve_runner

logger = logging.getLogger("quant.gateway.engine.snapshot_pipeline")


def run_snapshot_pipeline(
    target_date: Optional[Any] = None,
    force_refresh: bool = False,
    config: Optional[Any] = None
) -> Tuple[int, Any, str]:
    """
    Executes the complete GEX/DEX snapshot pipeline by delegating to the registered
    runner in PIPELINE_DAG['gexdex_snapshot'].
    Returns (rows_upserted, target_date, status_message).
    """
    if config is None:
        config = load_config()

    runner = resolve_runner(PIPELINE_DAG["gexdex_snapshot"]["runner"])
    return runner(target_date=target_date, force_refresh=force_refresh, config=config)
