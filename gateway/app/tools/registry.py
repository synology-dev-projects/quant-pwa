import inspect
import time
from contextvars import ContextVar
from typing import Callable, Dict, Any, List, Optional

tool_ui_events_var: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar("tool_ui_events_var", default=None)
tool_metrics_var: ContextVar[Optional[Dict[str, Any]]] = ContextVar("tool_metrics_var", default=None)


def emit_tool_ui_event(name: str, payload: Dict[str, Any]) -> None:
    """
    Emits a structured UI event from a tool into the current async request's SSE stream context.
    """
    events = tool_ui_events_var.get()
    if events is not None and isinstance(events, list):
        events.append({
            "type": "tool_ui",
            "name": name,
            "payload": payload
        })


def record_tool_metric(
    latency_ms: Optional[float] = None,
    cache_status: Optional[str] = None,
    retry_count: Optional[int] = None
) -> None:
    """
    Updates the current request's tool execution metrics.
    """
    metrics = tool_metrics_var.get()
    if metrics is not None:
        metrics["tools_called_count"] = metrics.get("tools_called_count", 0) + 1
        now = time.perf_counter()
        if latency_ms is not None:
            lat = float(latency_ms)
            metrics["tool_latency_ms"] = float(metrics.get("tool_latency_ms", 0.0)) + lat
            tool_start = now - (lat / 1000.0)
            if metrics.get("first_tool_start") is None:
                metrics["first_tool_start"] = tool_start
            metrics["last_tool_end"] = now
        elif metrics.get("first_tool_start") is None:
            metrics["first_tool_start"] = now
            metrics["last_tool_end"] = now
        if cache_status is not None:
            metrics["cache_status"] = str(cache_status)
        if retry_count is not None:
            metrics["retry_count"] = int(metrics.get("retry_count", 0)) + int(retry_count)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._declarations: List[Dict[str, Any]] = []

    def register(self, name: str, description: str, parameters: Dict[str, Any] = None):
        """
        Decorator to register an async Python function as an AI agent tool.
        """
        def decorator(func: Callable):
            self._tools[name] = func
            
            declaration = {
                "name": name,
                "description": description,
                "parameters": parameters or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            self._declarations.append(declaration)
            return func
        return decorator

    def get_tool(self, name: str) -> Callable:
        return self._tools.get(name)

    def get_all_declarations(self) -> List[Dict[str, Any]]:
        return self._declarations

    def get_callable_map(self) -> Dict[str, Callable]:
        return self._tools

registry = ToolRegistry()
register_tool = registry.register
