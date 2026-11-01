import type { CallToolResult, MCPClient } from "@ai-sdk/mcp";

import { callExecute } from "../mcp/tools.js";

export interface RoomTokenOptions {
  readonly tokenTtlSecs?: number;
  readonly refreshTokenTtlSecs?: number;
}

export interface RoomToken {
  readonly token: string;
  readonly expiresAt?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseText(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) return undefined;

  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return trimmed;
  }
}

function resultPayload(result: CallToolResult): unknown {
  if ("toolResult" in result) return result.toolResult;
  if (result.structuredContent !== undefined) return result.structuredContent;

  const text = result.content.find(
    (block): block is Extract<(typeof result.content)[number], { type: "text" }> =>
      block.type === "text",
  );
  return text ? parseText(text.text) : undefined;
}

function tokenFrom(value: unknown): string | undefined {
  if (typeof value === "string") {
    const token = value.trim();
    return token || undefined;
  }
  if (!isRecord(value)) return undefined;

  return tokenFrom(value.token) ?? tokenFrom(value.result) ?? tokenFrom(value.data);
}

function executeCode(tool: string, arguments_: Record<string, unknown>): string {
  return `return await call_tool('${tool}', ${JSON.stringify(arguments_)})`;
}

export async function mintVoiceToken(
  client: MCPClient,
  credentialId: string,
): Promise<string> {
  const result = await callExecute(
    client,
    executeCode("CreateTelephonyCredentialToken", { id: credentialId }),
  );
  const token = !result.isError ? tokenFrom(resultPayload(result)) : undefined;
  if (!token) throw new Error("Voice token response did not contain a token");
  return token;
}

export async function mintRoomToken(
  client: MCPClient,
  roomId: string,
  options: RoomTokenOptions = {},
): Promise<RoomToken> {
  const arguments_: Record<string, unknown> = { room_id: roomId };
  if (options.tokenTtlSecs !== undefined) {
    arguments_.token_ttl_secs = options.tokenTtlSecs;
  }
  if (options.refreshTokenTtlSecs !== undefined) {
    arguments_.refresh_token_ttl_secs = options.refreshTokenTtlSecs;
  }

  const result = await callExecute(
    client,
    executeCode("CreateRoomClientToken", arguments_),
  );
  const payload = !result.isError ? resultPayload(result) : undefined;
  const token = tokenFrom(payload);
  if (!token) throw new Error("Room token response did not contain a token");

  const data = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
  const expiresAt =
    isRecord(data) && typeof data.token_expires_at === "string"
      ? data.token_expires_at
      : undefined;
  return expiresAt ? { token, expiresAt } : { token };
}
