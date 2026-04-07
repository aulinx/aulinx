"""REST API for the Aulinx web dashboard — settings, audit, tools, workflows."""


from aulinx.audit import AuditLog
from aulinx.config import CONFIG_FILE, load_config
from aulinx.history import HistoryManager
from aulinx.long_memory import LongMemory
from aulinx.tools.registry import ToolRegistry
from aulinx.workflows import workflow_list


async def handle_api_request(path: str, method: str = "GET", body: dict | None = None) -> dict:
    """Route API requests from the WebSocket server.

    The web dashboard sends {"type": "api", "path": "/api/tools", "method": "GET"}
    and receives {"type": "api_response", "data": {...}}.
    """
    if path == "/api/tools":
        return _api_tools()
    elif path == "/api/audit":
        return _api_audit()
    elif path == "/api/history":
        return _api_history()
    elif path == "/api/config":
        if method == "GET":
            return _api_config_get()
        # POST for updating config is future work
    elif path == "/api/workflows":
        return _api_workflows()
    elif path == "/api/memory":
        return _api_memory()
    elif path == "/api/stats":
        return _api_stats()

    return {"error": f"Unknown API path: {path}"}


def _api_tools() -> dict:
    """List all registered tools with their details."""
    registry = ToolRegistry()
    tools = []
    for name in sorted(registry._tools):
        tool = registry._tools[name]
        tier_names = ["observe", "low_risk", "mutate", "destructive", "irreversible"]
        tools.append({
            "name": name,
            "description": tool.description,
            "parameters": tool.parameters,
            "tier": tier_names[tool.tier],
            "module": tool.fn.__module__.split(".")[-1] if hasattr(tool.fn, "__module__") else "unknown",
        })
    return {"tools": tools, "count": len(tools)}


def _api_audit() -> dict:
    """Get recent audit log entries."""
    log = AuditLog()
    entries = log.recent(50)
    return {"entries": entries, "count": len(entries)}


def _api_history() -> dict:
    """List conversation sessions."""
    mgr = HistoryManager()
    sessions = mgr.list_sessions(20)
    return {"sessions": sessions}


def _api_config_get() -> dict:
    """Get current configuration."""
    config = load_config()
    return {
        "model": config.llm.model,
        "base_url": config.llm.base_url,
        "temperature": config.llm.temperature,
        "router_model": config.llm.router_model,
        "max_history": config.context.max_history,
        "config_file": str(CONFIG_FILE),
    }


def _api_workflows() -> dict:
    """List workflows."""
    import asyncio
    workflows = asyncio.get_event_loop().run_until_complete(workflow_list())
    return {"workflows": workflows}


def _api_memory() -> dict:
    """Get memory stats and recent entries."""
    mem = LongMemory()
    return {
        "count": mem.count(),
        "recent": mem.recall_recent(10),
    }


def _api_stats() -> dict:
    """Get overall system stats."""
    registry = ToolRegistry()
    log = AuditLog()
    mem = LongMemory()
    mgr = HistoryManager()

    return {
        "tools": len(registry),
        "audit_entries": len(log.recent(1000)),
        "sessions": len(mgr.list_sessions(100)),
        "memories": mem.count(),
    }
