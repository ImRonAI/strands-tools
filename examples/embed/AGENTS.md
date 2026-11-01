# Browser Host Guidelines

Work here; inherit root/app guidance. Use public AppBridge and the source-pinned official basic-host reference. Do not implement a new postMessage/JSON-RPC relay, renderer or sandbox protocol.

Read `docs/reference/mcp-apps/` source snapshots and `docs/reference/contracts/FAST_MCP_AND_UI.md`. Official host uses native resource metadata/MIME checks, `sendToolInput`, `sendToolInputPartial`, `sendToolResult`, initialization and teardown. The public manual-handler path supports `new AppBridge(null, hostInfo, capabilities)` with host-provided handlers. A Python Client is not a JavaScript constructor argument.

Retain declared resource script/style/connect/font domains; validate source/origin and trusted-host reconfiguration. Host/sandbox origins are separate. Do not patch the SDK or strip security to load Prefab assets. `text/html;profile=mcp-app` and `ui://` are actual contracts, not arbitrary conventions to replace.

Model/app visibility metadata is not backend authorization. Use the user's trusted backend connection and permitted tool/resource allowlist. A generated view is untrusted content. Preserve real raw structured result and UI metadata; do not send a fake completed result or call a mutating tool twice to recover metadata. Close bridge and observers using documented lifecycle. Root HTML plan pages are documentation, not an application host to reuse as product code.

## Assigned directory
Project target: `examples/embed`. Change into this directory before development. This copy is a planning template; the project scaffold is not installed until the worker applies it.
