#!/usr/bin/env python3
"""MCP server entrypoint for strands-diffusers.

Exposes use_diffusers (HuggingFace diffusers — text→image, image→video,
world-foundation models, Cosmos action policies) via the Model Context
Protocol, so it can be used from Claude Code, Claude Desktop, Kiro, Cursor,
or any MCP-compatible client.

Built on strands-mcp-server (https://github.com/cagataycali/strands-mcp-server).

Usage:
    # stdio mode (Claude Code / Claude Desktop) — default
    strands-diffusers-mcp

    # HTTP mode (multi-client, background-capable)
    strands-diffusers-mcp --http --port 8020

Claude Code:
    claude mcp add diffusers -- strands-diffusers-mcp

Claude Desktop config:
    {
      "mcpServers": {
        "diffusers": {
          "command": "strands-diffusers-mcp"
        }
      }
    }
"""
from __future__ import annotations

import argparse
import logging
import sys

# MCP stdio servers MUST log to stderr — stdout is the protocol channel.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("strands_diffusers.mcp")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="strands-diffusers MCP server — diffusion pipelines over MCP",
    )
    parser.add_argument("--http", action="store_true",
                        help="Run HTTP transport instead of stdio (default: stdio)")
    parser.add_argument("--port", type=int, default=8020, help="HTTP port (default: 8020)")
    parser.add_argument("--stateless", action="store_true",
                        help="Stateless HTTP mode (multi-node scalable)")
    parser.add_argument("--agent-invocation", action="store_true",
                        help="Also expose invoke_agent for full conversations (default: off)")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        from strands import Agent
        from strands_mcp_server.mcp_server import mcp_server
        from strands_diffusers import use_diffusers
    except ImportError as e:
        logger.error(
            f"Missing dependency: {e}\n"
            "Install with: pip install strands-mcp-server strands-diffusers"
        )
        sys.exit(1)

    logger.info("🎨 strands-diffusers MCP server: use_diffusers ready")

    agent = Agent(
        name="strands-diffusers-mcp",
        tools=[use_diffusers, mcp_server],  # mcp_server must be registered to invoke it
        load_tools_from_directory=False,
        system_prompt="strands-diffusers tool server: HuggingFace diffusers — text-to-image, image-to-video, world-foundation models, Cosmos action policies.",
        callback_handler=None,
    )

    transport = "http" if args.http else "stdio"
    logger.info(f"Starting MCP server (transport={transport})")
    # Call the raw tool function directly (NOT agent.tool.mcp_server) —
    # agent.tool.* marks the agent as mid-invocation, and since stdio mode
    # blocks forever, all nested tool calls would then be rejected by the SDK.
    _fn = getattr(mcp_server, "_tool_func", None) or getattr(mcp_server, "original_function", None) or mcp_server
    _fn(
        action="start",
        transport=transport,
        port=args.port,
        stateless=args.stateless,
        expose_agent=args.agent_invocation,
        agent=agent,
    )

    if args.http:
        # HTTP runs in background thread — keep process alive
        import time
        logger.info(f"HTTP MCP server live at http://localhost:{args.port}/mcp (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Shutting down")


if __name__ == "__main__":
    main()
