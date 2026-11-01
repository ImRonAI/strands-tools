# Python Client Guidelines

Work in this package or assigned child; inherit root rules. Own the full native `fastmcp.Client` integration. Do not turn this package into an agent runtime, browser renderer, second MCP protocol implementation or duplicate Telnyx SDK.

Read version-matched snapshots under `docs/reference/fastmcp/client/` and `docs/reference/contracts/FAST_MCP_AND_UI.md`. Official https://gofastmcp.com/clients/tools documents `list_tools()`, `call_tool()`, `.data`, `.content`, `.structured_content`, `.is_error` and raw `call_tool_mcp()`. Preserve the selected release's result metadata and resource MIME/CSP fields; never flatten everything into a string.

Use native connection/context-manager lifecycle, OAuth/bearer configuration, resources/templates/prompts/completion, handlers for supported progress/log/input/sampling/roots, task lifecycle, notifications, caches and optional ClientGroup. Protocol negotiation is a contract; do not assume every client/server mode supports the same features. All request handlers and caches must remain user-scoped.

The application's AI SDK MCP adapter intentionally lacks some full-client functionality and must not replace this package. Sources: official FastMCP Client docs; VERIFIED_DECISIONS. Expose normal configuration/documented hooks, not a custom transport/queue. Examples must demonstrate actual package APIs after they exist; research fixture scripts are not product examples or proof of live telecom behavior.

## Assigned directory
Project target: `examples/python`. Change into this directory before development. This copy is a planning template; the project scaffold is not installed until the worker applies it.
