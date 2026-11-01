import { readMCPAppResource } from "@ai-sdk/mcp";
import type { MCPAppResource, MCPClient } from "@ai-sdk/mcp";

export const RENDERER_URI = "ui://prefab/generative.html";

export class RendererResourceError extends Error {
  readonly uri: string;

  constructor(uri: string, cause: unknown) {
    super(`Unable to read renderer resource: ${uri}`, { cause });
    this.name = RendererResourceError.name;
    this.uri = uri;
  }
}

export async function readRendererResource(
  client: Pick<MCPClient, "readResource">,
): Promise<MCPAppResource> {
  try {
    return await readMCPAppResource({ client, uri: RENDERER_URI });
  } catch (cause) {
    throw new RendererResourceError(RENDERER_URI, cause);
  }
}
