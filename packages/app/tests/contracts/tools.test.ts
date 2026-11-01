import { expect, inject, test } from "vitest";

import { createOubliaiMcpClient } from "../../src/mcp/client.js";
import {
  callExecute,
  MODEL_VISIBLE_TOOLS,
  modelVisibleToolSet,
} from "../../src/mcp/tools.js";

test("model tool set contains only the four public tools", async () => {
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");
  const token = process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken");
  const client = await createOubliaiMcpClient({ url, token });

  try {
    const tools = await modelVisibleToolSet(client);

    expect(Object.keys(tools).sort()).toEqual([...MODEL_VISIBLE_TOOLS]);
  } finally {
    await client.close();
  }
});

test("execute preserves the raw Prefab structured content", async () => {
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");
  const token = process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken");
  const client = await createOubliaiMcpClient({ url, token });

  try {
    const result = await callExecute(
      client,
      "return await call_tool('google_workspace', {})",
    );

    expect(result.structuredContent).toMatchObject({
      $prefab: { version: "0.3" },
    });
  } finally {
    await client.close();
  }
});

test("connection rejects an invalid bearer token", async () => {
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");

  await expect(
    createOubliaiMcpClient({ url, token: "invalid-token" }),
  ).rejects.toThrow();
});
