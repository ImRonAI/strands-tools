import { expect, inject, test } from "vitest";

import { createOubliaiMcpClient } from "../../src/mcp/client.js";
import {
  mintRoomToken,
  mintVoiceToken,
} from "../../src/media/credentials.js";

async function withClient<T>(run: (client: Awaited<ReturnType<typeof createOubliaiMcpClient>>) => Promise<T>): Promise<T> {
  const url = process.env.OUBLIAI_TEST_MCP_URL ?? inject("mcpUrl");
  const token = process.env.OUBLIAI_TEST_TOKEN ?? inject("e2eToken");
  const client = await createOubliaiMcpClient({ url, token });

  try {
    return await run(client);
  } finally {
    await client.close();
  }
}

test("mints a voice login token through execute", async () => {
  await withClient(async (client) => {
    await expect(
      mintVoiceToken(client, "credential-fixture-001"),
    ).resolves.toBe("voice-token-fixture");
  });
});

test("mints a room client token and preserves its expiry", async () => {
  await withClient(async (client) => {
    await expect(
      mintRoomToken(client, "room-fixture-001", {
        tokenTtlSecs: 600,
        refreshTokenTtlSecs: 3_600,
      }),
    ).resolves.toEqual({
      token: "room-token-fixture",
      expiresAt: "2026-10-07T23:30:00Z",
    });
  });
});

test("rejects credential responses without a usable token", async () => {
  await withClient(async (client) => {
    await expect(
      mintVoiceToken(client, "credential-malformed"),
    ).rejects.toThrow("Voice token response did not contain a token");
    await expect(
      mintRoomToken(client, "room-malformed"),
    ).rejects.toThrow("Room token response did not contain a token");
  });
});
