"""Tool registry assembly.

Each submodule exposes `build_handlers(deps) -> dict[name, ToolSpec]`. The
registry is built once at register_routes() time so all tools share the same
dependency closure (db, upload_to_storage, firestore module, etc.).

ToolSpec shape:
    {
        "description": str,
        "inputSchema": dict (JSON Schema),
        "handler": Callable[[dict], list[ContentBlock] | dict],
    }
"""

from . import studio_tools, asset_tools, seedance_tools


def build_registry(deps: dict) -> dict:
    registry = {}
    for module in (studio_tools, asset_tools, seedance_tools):
        registry.update(module.build_handlers(deps))
    return registry
