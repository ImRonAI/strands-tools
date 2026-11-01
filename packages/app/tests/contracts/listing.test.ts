// RED contract: model-visible default listing is exactly the four workspace tools.
//
// The mcp module under test does not exist yet; this failure is the contract the
// mcp worker implements against. The fixture server URL + token arrive through
// the vitest global setup (process.env plus ProvidedContext).

import { test, expect, inject } from "vitest";

import {
  createMCPClient,
  mcpAppClientCapabilities,
  splitMCPAppTools,
} from "@ai-sdk/mcp";

// eslint-disable-next-line @typescript-eslint/consistent-type-imports
import { listModelVisibleToolNames } from "../../src/mcp/tools.js";

test("default listing exposes only the four model-visible tools", async () => {
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");
  const token = process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken");

  const client = await createMCPClient({
    transport: {
      type: "http",
      url,
      headers: { Authorization: `Bearer ${token}` },
    },
    capabilities: mcpAppClientCapabilities,
  });

  try {
    const listed = await client.listTools();
    // splitMCPAppTools is part of the adapter contract; the helper under test
    // must agree with its model-visible bucket and the expected four names.
    const split = splitMCPAppTools(listed);
    expect(split.modelVisible.tools.length).toBeGreaterThanOrEqual(4);
    expect(listModelVisibleToolNames(listed)).toEqual([
      "execute",
      "generate_prefab_ui",
      "get_schema",
      "search",
    ]);
  } finally {
    await client.close();
  }
});
