import { RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/app-bridge";
import { Client, type Resource, type Tool } from "@modelcontextprotocol/client";
import { afterAll, beforeAll, expect, test, vi } from "vitest";

import type { ServerInfo } from "../../src/host/implementation.js";

/**
 * UI host policy denial at the vendored official host layer: `callTool` from
 * `src/host/implementation.ts` attaches `getUiResource`, which rejects any
 * renderer whose `mimeType` is not `text/html;profile=mcp-app`.
 */

let callTool: typeof import("../../src/host/implementation.js").callTool;

beforeAll(async () => {
  vi.stubGlobal("window", {
    matchMedia: () => ({ matches: false, addEventListener: vi.fn() }),
  });
  vi.stubGlobal("document", {
    documentElement: { setAttribute: vi.fn(), style: {} },
  });
  vi.stubGlobal("__OUBLIAI_SANDBOX_PROXY_BASE_URL__", "");
  ({ callTool } = await import("../../src/host/implementation.js"));
});

afterAll(() => {
  vi.unstubAllGlobals();
});

const rendererUri = "ui://prefab/generative.html";

function createServerInfo(mimeType: string): ServerInfo {
  const client = new Client({ name: "host-policy-test", version: "1.0.0" });
  vi.spyOn(client, "callTool").mockResolvedValue({
    content: [{ type: "text", text: "ok" }],
    structuredContent: { $prefab: { version: "0.3" } },
  });
  vi.spyOn(client, "readResource").mockResolvedValue({
    contents: [{ uri: rendererUri, mimeType, text: "<!doctype html>" }],
  });
  const tool = {
    name: "generate_prefab_ui",
    inputSchema: { type: "object" },
    _meta: { ui: { resourceUri: rendererUri } },
  } satisfies Tool;
  const renderer = {
    name: "Prefab renderer",
    uri: rendererUri,
    mimeType,
  } satisfies Resource;
  return {
    name: "host-policy-test",
    client,
    tools: new Map([[tool.name, tool]]),
    resources: new Map([[rendererUri, renderer]]),
    appHtmlCache: new Map(),
  };
}

test("official host callTool rejects a renderer resource with the wrong MIME type", async () => {
  const plan = callTool(createServerInfo("text/html"), "generate_prefab_ui", {});

  expect(plan.appResourcePromise).toBeDefined();
  await expect(plan.appResourcePromise).rejects.toThrow(
    "Unsupported MIME type: text/html",
  );
});

test("official host callTool accepts the MCP App MIME type", async () => {
  const plan = callTool(
    createServerInfo(RESOURCE_MIME_TYPE),
    "generate_prefab_ui",
    {},
  );

  await expect(plan.appResourcePromise).resolves.toMatchObject({
    html: "<!doctype html>",
  });
});
