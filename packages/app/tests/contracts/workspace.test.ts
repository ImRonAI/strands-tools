import type { CallToolResult, MCPClient } from "@ai-sdk/mcp";
import { RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/app-bridge";
import {
  Client,
  type Resource,
  type Tool,
} from "@modelcontextprotocol/client";
import {
  afterAll,
  beforeAll,
  describe,
  expect,
  inject,
  test,
  vi,
} from "vitest";

import type { ServerInfo } from "../../src/host/implementation.js";
import { createOubliaiMcpClient } from "../../src/mcp/client.js";
import {
  isWorkspaceDomain,
  WORKSPACE_DOMAINS,
  workspaceCode,
  workspaceToolName,
} from "../../src/workspace/domains.js";
import {
  NotAPrefabPayloadError,
  openWorkspace,
} from "../../src/workspace/open.js";

let client: MCPClient | undefined;
let buildRenderPlan: typeof import("../../src/workspace/render-plan.js").buildRenderPlan;
const rendererUri = "ui://oubliai/prefab-renderer";

function createServerInfo(
  rendererMimeType: string,
  structuredContent: Record<string, unknown> = { $prefab: { version: "0.3" } },
): ServerInfo {
  const protocolClient = new Client({ name: "workspace-test", version: "1.0.0" });
  vi.spyOn(protocolClient, "callTool").mockResolvedValue({
    content: [{ type: "text", text: "workspace" }],
    structuredContent,
  });
  vi.spyOn(protocolClient, "readResource").mockResolvedValue({
    contents: [
      {
        uri: rendererUri,
        mimeType: rendererMimeType,
        text: "<!doctype html><title>Prefab</title>",
      },
    ],
  });
  const executeTool = {
    name: "execute",
    inputSchema: { type: "object" },
  } satisfies Tool;
  const renderer = {
    name: "Prefab renderer",
    uri: rendererUri,
    mimeType: rendererMimeType,
  } satisfies Resource;

  return {
    name: "workspace-test",
    client: protocolClient,
    tools: new Map([[executeTool.name, executeTool]]),
    resources: new Map([[renderer.uri, renderer]]),
    appHtmlCache: new Map(),
  };
}

beforeAll(async () => {
  vi.stubGlobal("window", {
    matchMedia: () => ({ matches: false, addEventListener: vi.fn() }),
  });
  vi.stubGlobal("document", {
    documentElement: { setAttribute: vi.fn(), style: {} },
  });
  vi.stubGlobal(
    "__OUBLIAI_SANDBOX_PROXY_BASE_URL__",
    "http://localhost:8081/sandbox.html",
  );
  ({ buildRenderPlan } = await import("../../src/workspace/render-plan.js"));
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");
  const token = process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken");
  client = await createOubliaiMcpClient({ url, token });
});

afterAll(async () => {
  await client?.close();
  vi.unstubAllGlobals();
});

test("workspace domain helpers preserve the server naming contract", () => {
  expect(WORKSPACE_DOMAINS).toEqual([
    "google",
    "fun_tools",
    "agent_tools",
    "pack",
    "youtube",
    "telegram",
    "zero",
    "utcp",
    "harness",
    "docs",
    "skills",
    "ccxt",
    "inspect",
    "ecosystem",
  ]);
  expect(WORKSPACE_DOMAINS.every(isWorkspaceDomain)).toBe(true);
  expect(workspaceToolName("google")).toBe("google_workspace");
  expect(workspaceCode("google")).toBe(
    "return await call_tool('google_workspace', {})",
  );
});

test("openWorkspace rejects an unknown runtime domain before execution", async () => {
  // Given
  if (!client) throw new Error("MCP fixture client was not initialized");

  // When
  const opening = Reflect.apply(openWorkspace, undefined, [client, "unknown"]);

  // Then
  await expect(opening).rejects.toMatchObject<NotAPrefabPayloadError>({
    name: "NotAPrefabPayloadError",
    message: "Unknown workspace domain: unknown",
  });
});

test("openWorkspace rejects execute output without a Prefab payload", async () => {
  // Given
  const nonPrefabClient = {
    callTool: async () =>
      ({ content: [], structuredContent: {} }) satisfies CallToolResult,
  };

  // When
  const opening = Reflect.apply(openWorkspace, undefined, [
    nonPrefabClient,
    "google",
  ]);

  // Then
  await expect(opening).rejects.toBeInstanceOf(NotAPrefabPayloadError);
});

describe.each(WORKSPACE_DOMAINS)("%s workspace", (domain) => {
  test("opens the real Prefab payload without replacing structured content", async () => {
    if (!client) throw new Error("MCP fixture client was not initialized");

    const payload = await openWorkspace(client, domain);

    expect(payload.domain).toBe(domain);
    expect(payload.prefabVersion).toBe("0.3");
    expect(payload.raw).toBe(payload.result.structuredContent);
    expect(payload.toolNames.length).toBeGreaterThan(0);
    for (const toolName of payload.toolNames) {
      expect(toolName).toMatch(/^[0-9a-f]{12}_/);
    }
  });
});

test("buildRenderPlan attaches the renderer to the execute result", async () => {
  // Given
  const serverInfo = createServerInfo(RESOURCE_MIME_TYPE);

  // When
  const plan = buildRenderPlan(serverInfo, "google", rendererUri);

  // Then
  expect(plan.input).toEqual({ code: workspaceCode("google") });
  await expect(plan.resultPromise).resolves.toMatchObject({
    structuredContent: { $prefab: { version: "0.3" } },
  });
  await expect(plan.appResourcePromise).resolves.toEqual({
    html: "<!doctype html><title>Prefab</title>",
    csp: undefined,
    permissions: undefined,
  });
});

test("buildRenderPlan rejects a renderer with the wrong MIME type", async () => {
  // Given
  const serverInfo = createServerInfo("text/html");

  // When
  const plan = buildRenderPlan(serverInfo, "google", rendererUri);

  // Then
  await expect(plan.appResourcePromise).rejects.toThrow(
    "Unsupported MIME type: text/html",
  );
});

test("buildRenderPlan rejects execute output without a Prefab payload", async () => {
  const serverInfo = createServerInfo(RESOURCE_MIME_TYPE, {});

  const plan = buildRenderPlan(serverInfo, "google", rendererUri);

  await expect(plan.resultPromise).rejects.toBeInstanceOf(NotAPrefabPayloadError);
});
