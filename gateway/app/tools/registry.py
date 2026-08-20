import inspect
from contextvars import ContextVar
from typing import Callable, Dict, Any, List, Optional

tool_ui_events_var: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar("tool_ui_events_var", default=None)


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
