"""
Helper module to spawn and communicate with CMS Coverage MCP Server.

Usage:
    from cms_coverage_client import CMSCoverageMCPClient
    
    with CMSCoverageMCPClient() as client:
        tools = client.list_tools()
        print(f"Available tools: {len(tools)}")
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class CMSCoverageMCPClient:
    def __init__(self, spec_path: Optional[str] = None):
        self.process = None
        self.server_dir = Path(__file__).parent
        self.spec_path = spec_path or str(self.server_dir / "coverageapi.json")
        
    def start(self):
        if self.process:
            raise RuntimeError("Server already running")
            
        cmd = [
            "uvx", "--from", "openapi-mcp-server", "openapi_mcp_server",
            "--openapi-spec-path", self.spec_path,
            "--api-base-url", "https://api.cms.gov/mcd"
        ]
        
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(self.server_dir)
        )
        
    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
            
    def send_request(self, method: str, params: Optional[Dict] = None) -> Dict:
        if not self.process:
            raise RuntimeError("Server not running. Call start() first.")
            
        request = {"jsonrpc": "2.0", "method": method, "id": 1}
        if params:
            request["params"] = params
            
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        
        response_line = self.process.stdout.readline()
        return json.loads(response_line)
        
    def list_tools(self) -> List[Dict[str, Any]]:
        response = self.send_request("tools/list")
        return response.get("result", {}).get("tools", [])
        
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        response = self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        return response.get("result")
        
    def __enter__(self):
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
