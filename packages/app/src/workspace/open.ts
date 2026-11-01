import type { CallToolResult, MCPClient } from "@ai-sdk/mcp";

import { callExecute } from "../mcp/tools.js";
import {
  isWorkspaceDomain,
  type WorkspaceDomain,
  workspaceCode,
} from "./domains.js";

export interface WorkspacePayload {
  readonly domain: WorkspaceDomain;
  readonly prefabVersion: string;
  readonly toolNames: readonly string[];
  readonly result: CallToolResult;
  readonly raw: Record<string, unknown>;
}

export class NotAPrefabPayloadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NotAPrefabPayloadError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readPrefabVersion(raw: Record<string, unknown>): string | undefined {
  const prefab = raw.$prefab;
  if (!isRecord(prefab)) return undefined;
  return typeof prefab.version === "string" ? prefab.version : undefined;
}

function readToolNames(raw: Record<string, unknown>): readonly string[] {
  const metadata = raw._meta;
  if (!isRecord(metadata)) return [];
  const fastmcp = metadata.fastmcp;
  if (!isRecord(fastmcp)) return [];
  const toolNames = fastmcp.toolNames;
  if (Array.isArray(toolNames)) {
    return toolNames.every((name) => typeof name === "string") ? toolNames : [];
  }
  if (!isRecord(toolNames)) return [];
  const names = Object.values(toolNames);
  return names.every((name) => typeof name === "string") ? names : [];
}

export function parsePrefabPayload(
  result: CallToolResult,
  context = "Execute",
): Pick<WorkspacePayload, "prefabVersion" | "toolNames" | "raw"> {
  const raw = result.structuredContent;
  if (result.isError || !isRecord(raw)) {
    throw new NotAPrefabPayloadError(`${context} did not return a Prefab payload`);
  }

  const prefabVersion = readPrefabVersion(raw);
  if (prefabVersion === undefined) {
    throw new NotAPrefabPayloadError(`${context} did not return a Prefab payload`);
  }

  return {
    prefabVersion,
    toolNames: readToolNames(raw),
    raw,
  };
}

export async function openWorkspace(
  client: MCPClient,
  domain: WorkspaceDomain,
): Promise<WorkspacePayload> {
  if (!isWorkspaceDomain(domain)) {
    throw new NotAPrefabPayloadError(`Unknown workspace domain: ${String(domain)}`);
  }

  const result = await callExecute(client, workspaceCode(domain));
  const parsed = parsePrefabPayload(result, `Workspace ${domain}`);

  return {
    domain,
    prefabVersion: parsed.prefabVersion,
    toolNames: parsed.toolNames,
    result,
    raw: parsed.raw,
  };
}
