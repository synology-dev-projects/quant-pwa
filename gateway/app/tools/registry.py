import inspect
from typing import Callable, Dict, Any, List

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
