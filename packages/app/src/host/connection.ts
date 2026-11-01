import {
  RESOURCE_MIME_TYPE,
  type McpUiResourceCsp,
  type McpUiResourcePermissions,
} from "@modelcontextprotocol/ext-apps/app-bridge";
import {
  Client,
  SSEClientTransport,
  StreamableHTTPClientTransport,
  type Resource,
  type Tool,
} from "@modelcontextprotocol/client";
import { log, type ServerInfo } from "./implementation.js";

/**
 * MCP connection and UI-resource reading for the browser host.
 *
 * These are the `connectToServer` / `getUiResource` helpers of the official
 * `implementation.ts`, re-expressed only so the user's bearer header reaches
 * the transport. Nothing about the MIME contract, the metadata precedence, or
 * the transport ladder changes.
 */

const IMPLEMENTATION = { name: "Oubliai Host", version: "1.0.0" };

export interface ConnectionDescriptor {
  url: string;
  headers: Record<string, string>;
}

export interface UiResourceData {
  html: string;
  csp?: McpUiResourceCsp;
  permissions?: McpUiResourcePermissions;
}

/**
 * The official transport ladder: Streamable HTTP first, then SSE. The bearer
 * header travels in `requestInit.headers`, the documented request
 * customization hook on both `StreamableHTTPClientTransportOptions` and
 * `SSEClientTransportOptions`.
 */
async function connectWithFallback(
  serverUrl: URL,
  headers: Record<string, string>,
): Promise<Client> {
  const requestInit: RequestInit = { headers };
  try {
    const client = new Client(IMPLEMENTATION);
    await client.connect(
      new StreamableHTTPClientTransport(serverUrl, { requestInit }),
    );
    log.info("Connected via Streamable HTTP transport");
    return client;
  } catch (streamableError) {
    log.info("Streamable HTTP failed:", streamableError);
  }

  try {
    const client = new Client(IMPLEMENTATION);
    await client.connect(new SSEClientTransport(serverUrl, { requestInit }));
    log.info("Connected via SSE transport");
    return client;
  } catch (sseError) {
    throw new Error(
      `Could not connect with any transport. SSE error: ${sseError}`,
    );
  }
}

/** `connectToServer` from `implementation.ts`, with the user's bearer header. */
export async function connectToServer(
  serverUrl: URL,
  headers: Record<string, string>,
): Promise<ServerInfo> {
  log.info("Connecting to server:", serverUrl.href);
  const client = await connectWithFallback(serverUrl, headers);
  const name = client.getServerVersion()?.name ?? serverUrl.href;

  const toolsList = await client.listTools();
  const tools = new Map<string, Tool>(
    toolsList.tools.map((tool) => [tool.name, tool]),
  );
  log.info("Server tools:", Array.from(tools.keys()));

  const resourcesList = await client.listResources();
  const resources = new Map<string, Resource>(
    resourcesList.resources.map((resource) => [resource.uri, resource]),
  );
  log.info("Server resources:", Array.from(resources.keys()));

  return { name, client, tools, resources, appHtmlCache: new Map() };
}

/** Narrow a `_meta` value to the UI metadata container the spec defines. */
function readUiMeta(meta: unknown): UiResourceData | undefined {
  if (typeof meta !== "object" || meta === null) return undefined;
  const ui = (meta as Record<string, unknown>)["ui"];
  if (typeof ui !== "object" || ui === null) return undefined;
  return ui as UiResourceData;
}

/**
 * `getUiResource` from `implementation.ts`: read the resource, enforce the
 * `text/html;profile=mcp-app` MIME contract, and take CSP/permissions from
 * content-level `_meta.ui` (with the Python SDK's `meta` quirk), falling back
 * to listing-level `_meta.ui` per the spec.
 */
export async function readUiResource(
  serverInfo: ServerInfo,
  uri: string,
): Promise<UiResourceData> {
  log.info("Reading UI resource:", uri);
  const resource = await serverInfo.client.readResource({ uri });
  if (resource.contents.length !== 1) {
    throw new Error(`Unexpected contents count: ${resource.contents.length}`);
  }
  const content = resource.contents[0];
  if (!content) {
    throw new Error(`Resource not found: ${uri}`);
  }
  if (content.mimeType !== RESOURCE_MIME_TYPE) {
    throw new Error(`Unsupported MIME type: ${content.mimeType}`);
  }

  const html = "blob" in content ? atob(content.blob) : content.text;

  const record = content as unknown as Record<string, unknown>;
  const contentMeta = readUiMeta(record["_meta"] ?? record["meta"]);
  const listingResource = serverInfo.resources.get(uri) as
    | (Resource & { _meta?: unknown })
    | undefined;
  const uiMeta = contentMeta ?? readUiMeta(listingResource?._meta);

  return { html, csp: uiMeta?.csp, permissions: uiMeta?.permissions };
}
