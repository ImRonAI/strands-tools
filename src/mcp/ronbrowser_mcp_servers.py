"""
MCP Server registry endpoints.

Manages MCP server configurations with:
- name: Server identifier
- description: What the server does
- connection_command: How to connect (e.g., npx command, uvx command, etc.)
- configuration: Additional config (env vars, etc.)
"""

import json
import shlex
import logging
import ast
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Path as PathParam
from pydantic import BaseModel, Field

from agent.api.core.config import DISCOVERY_MANIFEST_PATH

router = APIRouter()
logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MCP_TOOLS_DIR = _PROJECT_ROOT / "agent" / "tools" / "src" / "strands_tools" / "mcp"
_OPENAPI_SPECS_DIR = _PROJECT_ROOT / "agent" / "tools" / "src" / "strands_tools" / "open-api-specs"
_STRANDS_TOOLS_SRC_DIR = _PROJECT_ROOT / "agent" / "tools" / "src" / "strands_tools"


# -----------------------------------------------------------------------------
# Pydantic Models
# -----------------------------------------------------------------------------

class MCPServerCreate(BaseModel):
    id: str = Field(..., description="Unique server identifier")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="What the server does")
    connection_command: str = Field(..., description="Command to start/connect to server")
    transport: str = Field(default="stdio", description="Transport type: stdio, sse, http")
    configuration: Optional[Dict[str, Any]] = Field(default=None, description="Additional config")
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables")


class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    connection_command: Optional[str] = None
    transport: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None
    env_vars: Optional[Dict[str, str]] = None


class MCPServer(BaseModel):
    id: str
    name: str
    description: str
    connection_command: str
    transport: str
    configuration: Optional[Dict[str, Any]]
    env_vars: Optional[Dict[str, str]]
    created_at: str
    updated_at: str


# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------

def _ensure_manifest_dir():
    """Ensure the manifest directory exists."""
    DISCOVERY_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)


def _default_gateway_server() -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    return {
        "id": "docker-mcp-gateway",
        "name": "Docker MCP Gateway",
        "description": "Docker MCP Gateway (stdio). Command: docker mcp gateway run",
        "connection_command": "docker mcp gateway run",
        "transport": "stdio",
        "configuration": {},
        "env_vars": {},
        "created_at": now,
        "updated_at": now,
    }


def _build_mcp_connection_command(server_dir: Path) -> str:
    """Best-effort stdio command for discoverability; users can override per server."""
    package_json = server_dir / "package.json"
    if package_json.exists():
        return f"npx -y {server_dir.name}"
    if (server_dir / "server.py").exists():
        return f"python {str((server_dir / 'server.py').resolve())}"
    return f"cd {str(server_dir.resolve())} && <configure-command>"


def _scan_mcp_servers() -> List[Dict[str, Any]]:
    if not _MCP_TOOLS_DIR.exists():
        return []

    now = datetime.utcnow().isoformat()
    servers: List[Dict[str, Any]] = []
    for child in sorted(_MCP_TOOLS_DIR.iterdir()):
        if not child.is_dir():
            continue
        server_id = child.name
        command = _build_mcp_connection_command(child)
        servers.append(
            {
                "id": server_id,
                "name": server_id.replace("-", " ").replace("_", " ").title(),
                "description": f"Auto-discovered MCP server from {child}",
                "connection_command": command,
                "connect_command": command,
                "transport": "stdio",
                "configuration": {},
                "env_vars": {},
                "path": str(child.resolve()),
                "created_at": now,
                "updated_at": now,
            }
        )
    return servers


def _scan_openapi_specs() -> List[Dict[str, Any]]:
    if not _OPENAPI_SPECS_DIR.exists():
        return []

    now = datetime.utcnow().isoformat()
    specs: List[Dict[str, Any]] = []
    seen_names: set[str] = set()
    for ext in ("*.json", "*.yaml", "*.yml"):
        for spec_path in sorted(_OPENAPI_SPECS_DIR.rglob(ext)):
            if not spec_path.is_file():
                continue
            rel = spec_path.relative_to(_OPENAPI_SPECS_DIR)
            stem = spec_path.stem
            name = stem if stem not in seen_names else str(rel.with_suffix("")).replace("/", "_").replace(" ", "_")
            seen_names.add(name)
            specs.append(
                {
                    "name": name,
                    "file": spec_path.name,
                    "path": str(spec_path.resolve()),
                    "description": f"Auto-discovered OpenAPI spec from {rel}",
                    "mcp_command": f"npx -y openapi-mcp-server {shlex.quote(str(spec_path.resolve()))}",
                    "created_at": now,
                    "updated_at": now,
                }
            )
    return specs


def _tool_category_from_path(path: Path) -> str:
    normalized_parts = [part.strip().lower().replace("-", "_").replace(" ", "_") for part in path.parts]
    normalized = "/".join(normalized_parts)

    if "strands_fun_tools" in normalized:
        return "strands_fun_tools"
    if "strands_google" in normalized:
        return "strands_google"
    if "/perplexity/" in normalized:
        return "perplexity"
    if "/pubmed/" in normalized or "/pubmed_/" in normalized:
        return "pubmed"
    if "/fda/" in normalized:
        return "fda"
    return "strands_tools"


def _has_tool_decorator(decorator: ast.AST) -> bool:
    if isinstance(decorator, ast.Name):
        return decorator.id == "tool"
    if isinstance(decorator, ast.Attribute):
        return decorator.attr == "tool"
    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
        return decorator.func.id == "tool"
    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
        return decorator.func.attr == "tool"
    return False


def _scan_loadable_tools() -> List[Dict[str, Any]]:
    if not _STRANDS_TOOLS_SRC_DIR.exists():
        return []

    now = datetime.utcnow().isoformat()
    discovered: List[Dict[str, Any]] = []
    seen_names: set[str] = set()

    for py_file in sorted(_STRANDS_TOOLS_SRC_DIR.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        if py_file.name.startswith("test_") or py_file.name == "__init__.py":
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as exc:
            logger.debug("Skipping loadable tool scan for %s: %s", py_file, exc)
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(_has_tool_decorator(decorator) for decorator in node.decorator_list):
                continue

            tool_name = node.name
            if tool_name in seen_names:
                continue
            seen_names.add(tool_name)

            doc = ast.get_docstring(node) or ""
            first_line = next((line.strip() for line in doc.splitlines() if line.strip()), "")
            abs_path = str(py_file.resolve())
            category = _tool_category_from_path(py_file.relative_to(_STRANDS_TOOLS_SRC_DIR))
            discovered.append(
                {
                    "name": tool_name,
                    "description": first_line or f"Tool from {py_file.name}",
                    "path": abs_path,
                    "category": category,
                    "load_command": f"load_tool(path='{abs_path}', name='{tool_name}')",
                    "unload_command": f"unload_tool(name='{tool_name}')",
                    "last_updated": now,
                }
            )

    return discovered


def _ensure_manifest_structure(manifest: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(manifest, dict):
        manifest = {}
    manifest.setdefault("mcp_servers", [])
    manifest.setdefault("openapi_specs", [])
    manifest.setdefault("loadable_tools", [])

    servers = manifest.get("mcp_servers")
    if not isinstance(servers, list):
        servers = []
    server_map: Dict[str, Dict[str, Any]] = {}
    for server in servers:
        if isinstance(server, dict) and server.get("id"):
            server_map[str(server["id"])] = dict(server)

    for discovered in _scan_mcp_servers():
        server_id = str(discovered["id"])
        existing = server_map.get(server_id, {})
        server_map[server_id] = {**discovered, **existing}

    gateway_id = "docker-mcp-gateway"
    if gateway_id not in server_map:
        server_map[gateway_id] = _default_gateway_server()
    manifest["mcp_servers"] = list(server_map.values())

    specs = manifest.get("openapi_specs")
    if not isinstance(specs, list):
        specs = []
    spec_map: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        if isinstance(spec, dict) and spec.get("name"):
            spec_map[str(spec["name"])] = dict(spec)
    for discovered_spec in _scan_openapi_specs():
        spec_name = str(discovered_spec["name"])
        existing = spec_map.get(spec_name, {})
        spec_map[spec_name] = {**discovered_spec, **existing}
    manifest["openapi_specs"] = list(spec_map.values())

    loadable_tools = manifest.get("loadable_tools")
    if not isinstance(loadable_tools, list):
        loadable_tools = []
    loadable_tool_map: Dict[str, Dict[str, Any]] = {}
    for tool in loadable_tools:
        if isinstance(tool, dict) and tool.get("name"):
            loadable_tool_map[str(tool["name"])] = dict(tool)
    for discovered_tool in _scan_loadable_tools():
        tool_name = str(discovered_tool["name"])
        existing = loadable_tool_map.get(tool_name, {})
        loadable_tool_map[tool_name] = {**discovered_tool, **existing}
    manifest["loadable_tools"] = list(loadable_tool_map.values())

    return manifest


def _load_manifest() -> Dict[str, Any]:
    """Load the discovery manifest."""
    if not DISCOVERY_MANIFEST_PATH.exists():
        return _ensure_manifest_structure({})
    
    try:
        with open(DISCOVERY_MANIFEST_PATH, "r") as f:
            payload = json.load(f)
            return _ensure_manifest_structure(payload)
    except Exception as exc:
        logger.warning("Failed to read MCP discovery manifest %s: %s", DISCOVERY_MANIFEST_PATH, exc)
        return _ensure_manifest_structure({})


def _save_manifest(manifest: Dict[str, Any]):
    """Save the discovery manifest."""
    manifest = _ensure_manifest_structure(manifest)
    _ensure_manifest_dir()
    with open(DISCOVERY_MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def ensure_default_mcp_server_manifest() -> None:
    """Ensure the manifest exists and includes default MCP server entries."""
    manifest = _ensure_manifest_structure(_load_manifest())
    _save_manifest(manifest)


def _parse_stdio_command(command: str) -> tuple[str, List[str]]:
    parts = shlex.split(command or "")
    if not parts:
        raise ValueError("connection_command is required for stdio transport")
    return parts[0], parts[1:]


def _normalized_transport(raw_transport: str) -> str:
    normalized = (raw_transport or "stdio").strip().lower()
    if normalized == "http":
        return "streamable_http"
    return normalized


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.get("/", response_model=List[MCPServer])
async def list_mcp_servers():
    """List all registered MCP servers."""
    manifest = _load_manifest()
    servers = manifest.get("mcp_servers", [])
    return [MCPServer(**s) for s in servers]


@router.post("/", response_model=MCPServer, status_code=201)
async def create_mcp_server(server: MCPServerCreate):
    """Register a new MCP server."""
    manifest = _load_manifest()
    servers = manifest.get("mcp_servers", [])
    
    # Check for duplicate ID
    if any(s["id"] == server.id for s in servers):
        raise HTTPException(status_code=400, detail=f"Server with ID '{server.id}' already exists")
    
    now = datetime.utcnow().isoformat()
    server_data = {
        "id": server.id,
        "name": server.name,
        "description": server.description,
        "connection_command": server.connection_command,
        "transport": server.transport,
        "configuration": server.configuration or {},
        "env_vars": server.env_vars or {},
        "created_at": now,
        "updated_at": now
    }
    
    servers.append(server_data)
    manifest["mcp_servers"] = servers
    _save_manifest(manifest)
    
    return MCPServer(**server_data)


@router.get("/{server_id}", response_model=MCPServer)
async def get_mcp_server(server_id: str = PathParam(..., description="Server ID")):
    """Get a specific MCP server."""
    manifest = _load_manifest()
    servers = manifest.get("mcp_servers", [])
    
    for server in servers:
        if server["id"] == server_id:
            return MCPServer(**server)
    
    raise HTTPException(status_code=404, detail=f"MCP server not found: {server_id}")


@router.put("/{server_id}", response_model=MCPServer)
async def update_mcp_server(
    server_update: MCPServerUpdate,
    server_id: str = PathParam(..., description="Server ID")
):
    """Update an MCP server."""
    manifest = _load_manifest()
    servers = manifest.get("mcp_servers", [])
    
    for i, server in enumerate(servers):
        if server["id"] == server_id:
            # Update fields
            if server_update.name is not None:
                server["name"] = server_update.name
            if server_update.description is not None:
                server["description"] = server_update.description
            if server_update.connection_command is not None:
                server["connection_command"] = server_update.connection_command
            if server_update.transport is not None:
                server["transport"] = server_update.transport
            if server_update.configuration is not None:
                server["configuration"] = server_update.configuration
            if server_update.env_vars is not None:
                server["env_vars"] = server_update.env_vars
            
            server["updated_at"] = datetime.utcnow().isoformat()
            
            manifest["mcp_servers"] = servers
            _save_manifest(manifest)
            
            return MCPServer(**server)
    
    raise HTTPException(status_code=404, detail=f"MCP server not found: {server_id}")


@router.delete("/{server_id}")
async def delete_mcp_server(server_id: str = PathParam(..., description="Server ID")):
    """Delete an MCP server."""
    manifest = _load_manifest()
    servers = manifest.get("mcp_servers", [])
    
    for i, server in enumerate(servers):
        if server["id"] == server_id:
            del servers[i]
            manifest["mcp_servers"] = servers
            _save_manifest(manifest)
            return {"status": "deleted", "server_id": server_id}
    
    raise HTTPException(status_code=404, detail=f"MCP server not found: {server_id}")


@router.post("/{server_id}/test")
async def test_mcp_server(server_id: str = PathParam(..., description="Server ID")):
    """
    Test connection to an MCP server.
    
    Returns connection status and available tools.
    """
    manifest = _load_manifest()
    servers = manifest.get("mcp_servers", [])
    
    server = None
    for s in servers:
        if s["id"] == server_id:
            server = s
            break
    
    if not server:
        raise HTTPException(status_code=404, detail=f"MCP server not found: {server_id}")
    
    # Attempt to connect and list tools
    try:
        from strands_tools.mcp_client import mcp_client

        transport = _normalized_transport(server.get("transport", "stdio"))
        connect_kwargs: Dict[str, Any] = {
            "action": "connect",
            "connection_id": server_id,
            "transport": transport,
        }

        if transport == "stdio":
            command, args = _parse_stdio_command(server.get("connection_command", ""))
            connect_kwargs["command"] = command
            connect_kwargs["args"] = args
            env_vars = server.get("env_vars")
            if isinstance(env_vars, dict) and env_vars:
                connect_kwargs["env"] = env_vars
        else:
            connect_kwargs["server_url"] = server.get("connection_command", "")

        connect_result = mcp_client(**connect_kwargs)
        list_result = mcp_client(action="list_tools", connection_id=server_id)
        mcp_client(action="disconnect", connection_id=server_id)

        return {
            "server_id": server_id,
            "status": "connected",
            "connect_result": connect_result,
            "list_tools_result": list_result,
        }
    except Exception as e:
        return {
            "server_id": server_id,
            "status": "failed",
            "error": str(e)
        }
