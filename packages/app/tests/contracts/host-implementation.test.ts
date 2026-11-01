import type { AppBridge } from "@modelcontextprotocol/ext-apps/app-bridge";
import type { CallToolResult, Tool } from "@modelcontextprotocol/client";
import { afterAll, beforeAll, expect, test, vi } from "vitest";

import type {
  ServerInfo,
  ToolCallInfo,
} from "../../src/host/implementation.js";

let initializeApp: typeof import("../../src/host/implementation.js").initializeApp;
let log: typeof import("../../src/host/implementation.js").log;

beforeAll(async () => {
  vi.stubGlobal("window", {
    matchMedia: () => ({ matches: false, addEventListener: vi.fn() }),
  });
  vi.stubGlobal("document", {
    documentElement: { setAttribute: vi.fn(), style: {} },
  });
  vi.stubGlobal("__OUBLIAI_SANDBOX_PROXY_BASE_URL__", "");
  ({ initializeApp, log } = await import("../../src/host/implementation.js"));
});

afterAll(() => {
  vi.unstubAllGlobals();
});

test("initializeApp forwards tool results without logging their payload", async () => {
  const result = {
    content: [{ type: "text", text: "secret-result" }],
    structuredContent: { token: "secret-token" },
  } satisfies CallToolResult;
  const sendToolResult = vi.fn();
  const bridgeStub = {
    oninitialized: undefined as AppBridge["oninitialized"],
    connect: vi.fn(async () => {
      bridgeStub.oninitialized?.({} as never);
    }),
    sendSandboxResourceReady: vi.fn(async () => undefined),
    sendToolInput: vi.fn(),
    sendToolResult,
    sendToolCancelled: vi.fn(),
  };
  const infoSpy = vi.spyOn(log, "info");
  const tool = {
    name: "execute",
    inputSchema: { type: "object" },
  } satisfies Tool;
  const plan = {
    serverInfo: {} as ServerInfo,
    tool,
    input: {},
    resultPromise: Promise.resolve(result),
    appResourcePromise: Promise.resolve({ html: "<!doctype html>" }),
  } satisfies Required<ToolCallInfo>;

  await initializeApp(
    { contentWindow: {} } as unknown as HTMLIFrameElement,
    bridgeStub as unknown as AppBridge,
    plan,
  );
  await vi.waitFor(() => expect(sendToolResult).toHaveBeenCalledWith(result));

  expect(JSON.stringify(infoSpy.mock.calls)).not.toContain("secret-token");
});
