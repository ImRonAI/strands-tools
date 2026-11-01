import { expect, inject, test } from "vitest";

import { createOubliaiMcpClient } from "../../src/mcp/client.js";
import {
  readRendererResource,
  RENDERER_URI,
  RendererResourceError,
} from "../../src/mcp/resources.js";

test("renderer resource preserves URI MIME HTML and CSP metadata", async () => {
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");
  const token = process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken");
  const client = await createOubliaiMcpClient({ url, token });

  try {
    const resource = await readRendererResource(client);

    expect(resource.uri).toBe(RENDERER_URI);
    expect(resource.mimeType).toBe("text/html;profile=mcp-app");
    expect(resource.html.length).toBeGreaterThan(0);
    expect(resource.meta?.csp?.connectDomains).toEqual([
      "https://cdn.jsdelivr.net",
      "https://pypi.org",
      "https://files.pythonhosted.org",
    ]);
    expect(resource.meta?.csp?.resourceDomains).toEqual([
      "https://cdn.jsdelivr.net",
    ]);
  } finally {
    await client.close();
  }
});

test("renderer resource failures retain the requested URI", async () => {
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");
  const token = process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken");
  const client = await createOubliaiMcpClient({ url, token });
  await client.close();

  await expect(readRendererResource(client)).rejects.toMatchObject({
    name: RendererResourceError.name,
    uri: RENDERER_URI,
  });
});
