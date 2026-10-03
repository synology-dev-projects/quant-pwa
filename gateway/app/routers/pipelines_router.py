"""
Quant Pipelines & DAG Dependency Management Router.

Exposes endpoints for querying the pipeline DAG topology, inspecting
execution statuses for any trade session, and triggering or restarting pipeline jobs
with asynchronous background execution.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from pydantic import BaseModel, Field

from common_lib.config.main_config import load_config
from common_lib.connectors.postgres import get_postgres_engine
from common_lib.orchestration import (
    PIPELINE_DAG,
    get_registered_dag,
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
    async_exec: bool = True


@router.get("/dag")
def get_pipeline_dag() -> Dict[str, Any]:
    """Returns the registered pipeline DAG topology, batch grouping, and metadata."""
    try:
        dag = get_registered_dag(force_refresh=True)
        order = get_topological_order(dag)
        batches = get_topological_batches(dag)
        return {
            "status": "ok",
            "topological_order": order,
            "batches": batches,
            "dag": dag,
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
        dag = get_registered_dag()
        order = get_topological_order(dag)

        # Build full status map including unstarted pipelines and metadata
        full_status_map = {}
        for p_name in order:
            meta = dag.get(p_name, {})
            display_name = meta.get("display_name") or p_name.replace("_", " ").title()
            
            if p_name in statuses:
                item = dict(statuses[p_name])
                item["display_name"] = display_name
                item["description"] = meta.get("description", "")
                item["upstream"] = meta.get("upstream", [])
                full_status_map[p_name] = item
            else:
                full_status_map[p_name] = {
                    "pipeline_name": p_name,
                    "display_name": display_name,
                    "description": meta.get("description", ""),
                    "upstream": meta.get("upstream", []),
                    "session_date": str(target_date),
                    "status": "NOT_STARTED",
                    "rows_affected": 0,
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None,
                    "metadata": {},
                }
            full_status_map[p_name]["is_active"] = p_name in ("quant_levels", "unusual_options_flow", "unusual_option_flow")

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


def _execute_background_cycle(engine, target_date, from_pipeline, only_pipeline, force_all):
    """Background task worker function executing the cycle safely."""
    try:
        logger.info(f"🚀 Starting background pipeline cycle for {target_date} (target={only_pipeline or from_pipeline or 'ALL'})...")
        res = run_dag_cycle(
            engine=engine,
            session_date=target_date,
            from_pipeline=from_pipeline,
            only_pipeline=only_pipeline,
            force_all=force_all,
            dry_run=False,
        )
        logger.info(f"✅ Background pipeline cycle completed in {res.get('cycle_duration_sec', 0)}s.")
    except Exception as e:
        logger.error(f"❌ Background pipeline cycle failed: {e}", exc_info=True)


@router.post("/run")
def trigger_pipeline_run(
    req: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Triggers an on-demand pipeline execution, restart, or cascade.
    Supports asynchronous non-blocking background dispatch.
    """
    try:
        if req.pipeline_name in ("gexdex_snapshot", "market_confluence") and not req.dry_run:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pipeline '{req.pipeline_name}' is currently INACTIVE. Only Quant Levels and Options Flow are active.",
            )

        config = load_config()
        engine = get_postgres_engine(config)
        ensure_pipeline_runs_table(engine)

        if req.session_date:
            target_date = datetime.strptime(req.session_date, "%Y-%m-%d").date()
        else:
            _, _, last_market_day = get_market_calendar_context()
            target_date = last_market_day

        dag = get_registered_dag()
        target_name = req.pipeline_name or req.from_pipeline
        if target_name and target_name not in dag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pipeline '{target_name}' not registered in DAG."
            )

        # Dry Run is always synchronous
        if req.dry_run:
            plan = run_dag_cycle(
                engine=engine,
                session_date=target_date,
                from_pipeline=req.from_pipeline,
                only_pipeline=req.pipeline_name,
                force_all=req.force_all,
                dry_run=True,
                dag=dag,
            )
            return {
                "status": "ok",
                "session_date": str(target_date),
                "execution": plan,
                "plan": plan,
            }

        # Asynchronous Background Dispatch
        if req.async_exec:
            background_tasks.add_task(
                _execute_background_cycle,
                engine=engine,
                target_date=target_date,
                from_pipeline=req.from_pipeline,
                only_pipeline=req.pipeline_name,
                force_all=req.force_all,
            )
            return {
                "status": "ok",
                "dispatched": True,
                "session_date": str(target_date),
                "message": f"Pipeline run successfully dispatched for {target_date}.",
                "target": req.pipeline_name or req.from_pipeline or "FULL_DAG",
            }

        # Synchronous execution fallback (for unit tests / scripting)
        result = run_dag_cycle(
            engine=engine,
            session_date=target_date,
            from_pipeline=req.from_pipeline,
            only_pipeline=req.pipeline_name,
            force_all=req.force_all,
            dry_run=False,
            dag=dag,
        )

        return {
            "status": "ok",
            "dispatched": False,
            "session_date": str(target_date),
            "execution": result,
        }
    except HTTPException:
        raise
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        logger.error(f"Pipeline trigger failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline trigger execution failed: {str(e)}",
        )
