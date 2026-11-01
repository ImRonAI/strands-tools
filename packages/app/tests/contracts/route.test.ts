import type { AddressInfo } from "node:net";

import type { MCPClient } from "@ai-sdk/mcp";
import express from "express";
import { expect, inject, test, vi } from "vitest";

import { createModel } from "../../src/agent/model.js";
import {
  createChatRouter,
  devConnectionFromEnv,
  type ChatRouteDeps,
} from "../../src/agent/route.js";
import {
  createOubliaiMcpClient,
  type Connection,
} from "../../src/mcp/client.js";
import {
  createExecuteModel,
  createFailingModel,
  createTextModel,
} from "../fixtures/route-model.js";

function configuredModel() {
  return createModel({
    OUBLIAI_MODEL_BASE_URL: "https://models.example.test/v1",
    OUBLIAI_MODEL_API_KEY: "test-key",
    OUBLIAI_MODEL_ID: "test-model",
  });
}

async function postChat(
  deps: ChatRouteDeps,
  body: unknown,
): Promise<{ readonly status: number; readonly body: string }> {
  const app = express();
  app.use(express.json());
  app.use(createChatRouter(deps));
  const server = app.listen(0);
  await new Promise<void>((resolve) => server.once("listening", resolve));
  const address = server.address() as AddressInfo;

  try {
    const response = await fetch(`http://127.0.0.1:${address.port}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return { status: response.status, body: await response.text() };
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => (error === undefined ? resolve() : reject(error)));
    });
  }
}

async function createTrackedClient(
  connection: Connection,
  onClose: () => void,
): Promise<MCPClient> {
  const client = await createOubliaiMcpClient(connection);
  return new Proxy<MCPClient>(client, {
    get(target, property, receiver) {
      if (property === "close") {
        return async () => {
          await target.close();
          onClose();
        };
      }
      return Reflect.get(target, property, receiver);
    },
  });
}

test("POST /api/chat returns every missing model variable when model configuration is absent", async () => {
  // Given
  const deps = { connectionFor: () => undefined };

  // When
  const response = await postChat(deps, { prompt: "List my phone numbers." });

  // Then
  expect(response.status).toBe(503);
  expect(response.body).toBe(
    JSON.stringify({
      error: "model_not_configured",
      missing: [
        "OUBLIAI_MODEL_BASE_URL",
        "OUBLIAI_MODEL_API_KEY",
        "OUBLIAI_MODEL_ID",
      ],
    }),
  );
});

test("POST /api/chat rejects a request without a trusted connection", async () => {
  // Given
  const deps = {
    createModel: configuredModel,
    connectionFor: () => undefined,
  };

  // When
  const response = await postChat(deps, { prompt: "List my phone numbers." });

  // Then
  expect(response.status).toBe(401);
  expect(response.body).toBe(JSON.stringify({ error: "no_connection" }));
});

test("POST /api/chat rejects a missing prompt", async () => {
  // Given
  const deps = {
    connectionFor: () => ({
      url: "https://mcp.example.test/mcp",
      token: "test-token",
    }),
  };

  // When
  const response = await postChat(deps, {});

  // Then
  expect(response.status).toBe(400);
});

test("POST /api/chat streams execute UI data and closes its MCP client", async () => {
  // Given
  const connection: Connection = {
    url: process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl"),
    token: process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken"),
  };
  const model = createExecuteModel();
  let closed = false;
  const deps = {
    createModel: () => model,
    connectionFor: () => connection,
    createMcpClient: (trustedConnection: Connection) =>
      createTrackedClient(trustedConnection, () => {
        closed = true;
      }),
  };

  // When
  const response = await postChat(deps, { prompt: "Open the numbers workspace." });

  // Then
  expect(response.status).toBe(200);
  expect(response.body).toContain('"toolName":"execute"');
  expect(response.body).toContain('"$prefab"');
  await vi.waitFor(() => expect(closed).toBe(true));
});

test("POST /api/chat closes the MCP client when model streaming fails", async () => {
  // Given
  const connection: Connection = {
    url: process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl"),
    token: process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken"),
  };
  let closeCount = 0;
  const deps = {
    createModel: createFailingModel,
    connectionFor: () => connection,
    createMcpClient: (trustedConnection: Connection) =>
      createTrackedClient(trustedConnection, () => {
        closeCount += 1;
      }),
  };

  // When
  const response = await postChat(deps, { prompt: "Fail after connecting." });

  // Then
  expect(response.status).toBe(200);
  expect(response.body).toContain('"type":"error"');
  expect(closeCount).toBe(1);
});

test("POST /api/chat creates and closes one MCP client per request", async () => {
  // Given
  const connection: Connection = {
    url: process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl"),
    token: process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken"),
  };
  let createCount = 0;
  let closeCount = 0;
  const deps = {
    createModel: createTextModel,
    connectionFor: () => connection,
    createMcpClient: (trustedConnection: Connection) => {
      createCount += 1;
      return createTrackedClient(trustedConnection, () => {
        closeCount += 1;
      });
    },
  };

  // When
  const first = await postChat(deps, { prompt: "First request." });
  const second = await postChat(deps, { prompt: "Second request." });

  // Then
  expect([first.status, second.status]).toEqual([200, 200]);
  expect(createCount).toBe(2);
  await vi.waitFor(() => expect(closeCount).toBe(2));
});

test("development connection requires explicit opt-in and complete credentials", () => {
  // Given
  const configuredEnvironment = {
    OUBLIAI_DEV_CONNECTION: "1",
    OUBLIAI_MCP_URL: "https://mcp.example.test/mcp",
    OUBLIAI_USER_TOKEN: "test-token",
  };

  // When / Then
  expect(
    devConnectionFromEnv({
      ...configuredEnvironment,
      OUBLIAI_DEV_CONNECTION: "0",
    }),
  ).toBeUndefined();
  expect(
    devConnectionFromEnv({
      OUBLIAI_DEV_CONNECTION: "1",
      OUBLIAI_MCP_URL: configuredEnvironment.OUBLIAI_MCP_URL,
    }),
  ).toBeUndefined();
  expect(devConnectionFromEnv(configuredEnvironment)).toEqual({
    url: configuredEnvironment.OUBLIAI_MCP_URL,
    token: configuredEnvironment.OUBLIAI_USER_TOKEN,
  });
});
