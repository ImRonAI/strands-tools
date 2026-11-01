import {
  createMCPClient,
  mcpAppClientCapabilities,
} from "@ai-sdk/mcp";
import type { MCPClient } from "@ai-sdk/mcp";

export type OubliaiMcpClientOptions = {
  readonly url: string;
  readonly token: string;
};

export type Connection = OubliaiMcpClientOptions;

export function createOubliaiMcpClient({
  url,
  token,
}: OubliaiMcpClientOptions): Promise<MCPClient> {
  return createMCPClient({
    transport: {
      type: "http",
      url,
      headers: { Authorization: `Bearer ${token}` },
      fetch: globalThis.fetch.bind(globalThis),
    },
    capabilities: mcpAppClientCapabilities,
  });
}

export type { MCPClient } from "@ai-sdk/mcp";
