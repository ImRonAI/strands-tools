"""Tool loading logic for strands-tools-mcp.

Uses the Strands SDK's built-in loader to resolve tool strings into ``AgentTool``
instances, handling both ``@tool``-decorated functions (``DecoratedFunctionTool``)
and ``TOOL_SPEC`` module-based tools (``PythonAgentTool``) transparently.

Paths that look like URLs (``http://`` / ``https://``) are downloaded to a
temporary file first, so you can point directly at a raw GitHub link or any
other hosted ``.py`` file.
"""

import logging
import os
import tempfile

import httpx
from strands.tools.loader import load_tools_from_file_path, load_tools_from_module_path
from strands.types.tools import AgentTool

logger = logging.getLogger(__name__)


def _is_url(path: str) -> bool:
    """Return ``True`` if *path* looks like an HTTP(S) URL."""
    return path.startswith("http://") or path.startswith("https://")


def _download_to_tempfile(url: str) -> str:
    """Download *url* to a temporary ``.py`` file and return its path.

    Uses ``httpx`` which bundles its own CA certificates (via ``certifi``),
    avoiding the macOS ``SSL: CERTIFICATE_VERIFY_FAILED`` issue that affects
    ``urllib.request`` on Python.org installs.

    The file is written to the system temp directory and will be cleaned up
    on reboot at the latest.

    Raises:
        httpx.HTTPStatusError: If the server returns a 4xx/5xx response.
        httpx.ConnectError: On network/DNS errors.
    """
    # Derive a sensible module name from the URL's basename
    basename = os.path.basename(url.split("?")[0].split("#")[0])
    if not basename.endswith(".py"):
        basename = f"{basename}.py"

    tmp_dir = tempfile.gettempdir()
    dest = os.path.join(tmp_dir, f"strands_mcp_{basename}")

    logger.info("Downloading tool from %s -> %s", url, dest)

    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()

    with open(dest, "wb") as f:
        f.write(response.content)

    return dest


def load_tools_from_names(names: list[str]) -> list[AgentTool]:
    """Load Strands tools by module name from the ``strands-agents-tools`` package.

    Each *name* is resolved as ``strands_tools.<name>`` through the SDK's
    ``load_tools_from_module_path``, which discovers both ``@tool``-decorated
    functions and ``TOOL_SPEC`` module-based tools.

    Tools that fail to load (e.g. missing dependencies) are skipped with a
    warning rather than crashing the server.

    Args:
        names: Tool module names (e.g. ``["current_time", "file_read"]``).

    Returns:
        A list of successfully loaded :class:`AgentTool` instances.
    """
    tools: list[AgentTool] = []
    for name in names:
        module_path = f"strands_tools.{name}"
        try:
            loaded = load_tools_from_module_path(module_path)
        except Exception:
            logger.exception("Failed to load tool '%s' — skipping. Is a dependency missing?", module_path)
            continue
        for t in loaded:
            logger.info("Loaded tool '%s' from %s (%s)", t.tool_name, module_path, type(t).__name__)
        tools.extend(loaded)
    return tools


def load_tools_from_paths(paths: list[str]) -> list[AgentTool]:
    """Load Strands tools from local file paths **or** URLs.

    Each entry in *paths* can be:

    * A local file path (absolute or relative) — loaded directly.
    * An ``http://`` or ``https://`` URL — downloaded to a temp file first,
      then loaded.  This lets you point at raw GitHub links, gists, etc.

    Tools that fail to load (e.g. missing dependencies in the file) are
    skipped with a warning rather than crashing the server.

    Uses the SDK's ``load_tools_from_file_path`` which handles both
    ``@tool``-decorated and ``TOOL_SPEC`` module-based tools.

    Args:
        paths: File paths or URLs to ``.py`` tool files.

    Returns:
        A list of successfully loaded :class:`AgentTool` instances.
    """
    tools: list[AgentTool] = []
    for entry in paths:
        try:
            if _is_url(entry):
                filepath = _download_to_tempfile(entry)
            else:
                filepath = entry

            loaded = load_tools_from_file_path(filepath)
        except Exception:
            logger.exception("Failed to load tool from '%s' — skipping. Is a dependency missing?", entry)
            continue

        for t in loaded:
            logger.info("Loaded tool '%s' from %s (%s)", t.tool_name, entry, type(t).__name__)
        tools.extend(loaded)
    return tools
