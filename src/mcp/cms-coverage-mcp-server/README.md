# CMS Coverage MCP Server

OpenAPI-to-MCP server for the CMS (Centers for Medicare & Medicaid Services) Coverage API.

## Overview

This MCP server exposes the CMS Coverage API as MCP tools using the AWS Labs OpenAPI-to-MCP server.

## Configuration

**API Base URL**: https://api.cms.gov/mcd
**OpenAPI Spec**: coverageapi.json (266KB)

## Usage

### As Subprocess (stdio transport)

```python
from cms_coverage_client import CMSCoverageMCPClient

# Use as context manager
with CMSCoverageMCPClient() as client:
    tools = client.list_tools()
    
    # Call a tool
    result = client.call_tool("GetCoverageData", {
        "state": "CA"
    })
```

## Installation

```bash
# uvx is used to run the server (no local install needed)
# It will auto-install openapi-mcp-server when first run
```

## Files

- `coverageapi.json` - CMS Coverage API OpenAPI specification (266KB)
- `cms_coverage_client.py` - Python helper to spawn and use the server
- `requirements.txt` - Dependencies (fastmcp for reference)

## Notes

- Uses **stdio transport** (standard input/output)
- Designed to run as a subprocess, spawned on-demand
- Uses `uvx` to run the AWS Labs openapi-mcp-server package
