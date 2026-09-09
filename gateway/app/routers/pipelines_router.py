"""
Quant Pipelines & DAG Dependency Management Router.

Exposes endpoints for querying the pipeline DAG topology, inspecting
execution statuses for any trade session, and triggering or restarting pipeline jobs.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from common_lib.config.main_config import load_config
from common_lib.connectors.postgres import get_postgres_engine
from common_lib.orchestration import (
    PIPELINE_DAG,
    get_topological_order,
    get_topological_batches,
    get_downstream_dependencies,
    get_all_pipeline_statuses,
    get_pipeline_status,
    run_dag_cycle,
    ensure_pipeline_runs_table,
)
from app.core.auth import get_current_user
from app.routers.snapshot_status import get_market_calendar_context

logger = logging.getLogger("quant.gateway.pipelines_router")

router = APIRouter(tags=["Pipeline Orchestration & Dependency Manager"])


class PipelineRunRequest(BaseModel):
    session_date: Optional[str] = None
    pipeline_name: Optional[str] = None
    from_pipeline: Optional[str] = None
    force_all: bool = False
    dry_run: bool = False


@router.get("/dag")
def get_pipeline_dag() -> Dict[str, Any]:
    """Returns the registered pipeline DAG topology and metadata."""
    try:
        order = get_topological_order()
        batches = get_topological_batches()
        return {
            "status": "ok",
            "topological_order": order,
            "batches": batches,
            "dag": PIPELINE_DAG,
        }
    except Exception as e:
        logger.error(f"Failed to resolve pipeline DAG: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve pipeline DAG: {str(e)}",
        )


@router.get("/status")
def get_pipelines_status(
    date_str: Optional[str] = Query(None, alias="date", description="Target session date (YYYY-MM-DD)")
) -> Dict[str, Any]:
    """
    Returns the execution status of all registered pipelines for the target session date.
    Defaults to the latest completed market session.
    """
    try:
        config = load_config()
        engine = get_postgres_engine(config)
        ensure_pipeline_runs_table(engine)

        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            _, _, last_market_day = get_market_calendar_context()
            target_date = last_market_day

        statuses = get_all_pipeline_statuses(engine, target_date)
        order = get_topological_order()

        # Build full status map including unstarted pipelines
        full_status_map = {}
        for p_name in order:
            if p_name in statuses:
                full_status_map[p_name] = statuses[p_name]
            else:
                full_status_map[p_name] = {
                    "pipeline_name": p_name,
                    "session_date": str(target_date),
                    "status": "NOT_STARTED",
                    "rows_affected": 0,
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None,
                }

        all_success = all(
            full_status_map[p]["status"] == "SUCCESS" for p in order
        )

        return {
            "status": "ok",
            "session_date": str(target_date),
            "all_success": all_success,
            "topological_order": order,
            "pipelines": full_status_map,
        }
    except Exception as e:
        logger.error(f"Failed to fetch pipeline statuses: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query pipeline statuses: {str(e)}",
        )


@router.post("/run")
def trigger_pipeline_run(
    req: PipelineRunRequest,
    current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Triggers an on-demand pipeline execution or restart.
    Requires authenticated bearer token.
    """
    try:
        config = load_config()
        engine = get_postgres_engine(config)
        ensure_pipeline_runs_table(engine)

        if req.session_date:
            target_date = datetime.strptime(req.session_date, "%Y-%m-%d").date()
        else:
            _, _, last_market_day = get_market_calendar_context()
            target_date = last_market_day

        result = run_dag_cycle(
            engine=engine,
            session_date=target_date,
            from_pipeline=req.from_pipeline,
            only_pipeline=req.pipeline_name,
            force_all=req.force_all,
            dry_run=req.dry_run,
        )

        return {
            "status": "ok",
            "session_date": str(target_date),
            "execution": result,
        }
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        logger.error(f"Pipeline trigger failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline trigger execution failed: {str(e)}",
        )
