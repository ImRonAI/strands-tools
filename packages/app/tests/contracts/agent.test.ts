import { expect, inject, test } from "vitest";

import type { MCPClient } from "@ai-sdk/mcp";
import { MockLanguageModelV4 } from "ai/test";

import {
  createFacilitator,
  runFacilitator,
} from "../../src/agent/facilitator.js";
import {
  createModel,
  ModelNotConfiguredError,
} from "../../src/agent/model.js";
import { extractToolParts } from "../../src/agent/ui-parts.js";
import { createOubliaiMcpClient } from "../../src/mcp/client.js";

const PREFAB_CODE = `from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Heading, Text
with PrefabApp() as app:
    with Column():
        Heading("Agent contract")
        Text("The fixture executed successfully.")`;

const usage = {
  inputTokens: { total: 1, noCache: 1, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 1, text: 1, reasoning: 0 },
};

type FixtureContentPart =
  | {
      readonly type: "tool-call";
      readonly toolCallId: string;
      readonly toolName: string;
      readonly input: string;
    }
  | { readonly type: "text-start"; readonly id: string }
  | { readonly type: "text-delta"; readonly id: string; readonly delta: string }
  | { readonly type: "text-end"; readonly id: string };

type FixtureStreamPart =
  | FixtureContentPart
  | { readonly type: "stream-start"; readonly warnings: [] }
  | {
      readonly type: "finish";
      readonly finishReason: {
        readonly unified: "stop" | "tool-calls";
        readonly raw: "stop" | "tool-calls";
      };
      readonly usage: typeof usage;
    };

function fixtureStream(
  content: FixtureContentPart[],
  reason: "stop" | "tool-calls",
) {
  return {
    stream: new ReadableStream<FixtureStreamPart>({
      start(controller) {
        controller.enqueue({ type: "stream-start", warnings: [] });
        for (const part of content) controller.enqueue(part);
        controller.enqueue({
          type: "finish",
          finishReason: { unified: reason, raw: reason },
          usage,
        });
        controller.close();
      },
    }),
  };
}

async function withFixtureClient<T>(
  run: (client: MCPClient) => Promise<T>,
): Promise<T> {
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");
  const token = process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken");
  const client = await createOubliaiMcpClient({ url, token });

  try {
    return await run(client);
  } finally {
    await client.close();
  }
}

test("model configuration reports every missing environment variable", () => {
  expect(() => createModel({})).toThrowError(
    new ModelNotConfiguredError([
      "OUBLIAI_MODEL_BASE_URL",
      "OUBLIAI_MODEL_API_KEY",
      "OUBLIAI_MODEL_ID",
    ]),
  );

  expect(
    createModel({
      OUBLIAI_MODEL_BASE_URL: "https://models.example.test/v1",
      OUBLIAI_MODEL_API_KEY: "test-key",
      OUBLIAI_MODEL_ID: "test-model",
    }).modelId,
  ).toBe("test-model");
});

test("execute returns a UI tool part with raw Prefab structured content", async () => {
  await withFixtureClient(async (client) => {
    const model = new MockLanguageModelV4({
      doStream: [
        fixtureStream(
          [
            {
              type: "tool-call",
              toolCallId: "execute-prefab",
              toolName: "execute",
              input: JSON.stringify({
                code: "return await call_tool('google_workspace', {})",
              }),
            },
          ],
          "tool-calls",
        ),
        fixtureStream(
          [
            { type: "text-start", id: "final" },
            { type: "text-delta", id: "final", delta: "Done." },
            { type: "text-end", id: "final" },
          ],
          "stop",
        ),
      ],
    });
    const agent = await createFacilitator({ client, model });
    const message = await runFacilitator(agent, "Open the numbers workspace.");
    const part = message.parts.find(
      (candidate) =>
        "toolName" in candidate && candidate.toolName === "execute",
    );

    expect(part).toMatchObject({
      state: "output-available",
      output: { structuredContent: { $prefab: { version: "0.3" } } },
    });
  });
});

test("prefab generator exposes released app metadata", async () => {
  await withFixtureClient(async (client) => {
    const model = new MockLanguageModelV4({
      doStream: [
        fixtureStream(
          [
            {
              type: "tool-call",
              toolCallId: "generate-prefab",
              toolName: "generate_prefab_ui",
              input: JSON.stringify({ code: PREFAB_CODE }),
            },
          ],
          "tool-calls",
        ),
        fixtureStream(
          [
            { type: "text-start", id: "final" },
            { type: "text-delta", id: "final", delta: "Done." },
            { type: "text-end", id: "final" },
          ],
          "stop",
        ),
      ],
    });
    const agent = await createFacilitator({ client, model });
    const message = await runFacilitator(agent, "Render the exact fixture.");

    expect(extractToolParts(message)).toMatchObject([
      {
        toolName: "generate_prefab_ui",
        output: { structuredContent: { $prefab: { version: "0.3" } } },
        app: {
          resourceUri: "ui://prefab/generative.html",
          mimeType: "text/html;profile=mcp-app",
        },
      },
    ]);
    // FastMCP 4.1.0 (#5612) keeps the GenerativeUI CSP on the renderer resource only; the
    // host reads it from `resources/read` (`appResourcePromise`), not from tool metadata.
    expect(extractToolParts(message)[0]?.app).not.toHaveProperty("csp");
  });
});

test("legacy nested MCP app metadata is ignored", () => {
  expect(
    extractToolParts({
      id: "legacy-message",
      role: "assistant",
      parts: [
        {
          type: "dynamic-tool",
          toolName: "generate_prefab_ui",
          toolCallId: "legacy-call",
          state: "output-available",
          input: { code: PREFAB_CODE },
          output: {},
          toolMetadata: {
            mcp: {
              app: {
                resourceUri: "ui://legacy/app.html",
                mimeType: "text/html;profile=mcp-app",
              },
            },
          },
        },
      ],
    }),
  ).toEqual([]);
});
