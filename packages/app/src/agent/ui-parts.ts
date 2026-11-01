import type { MCPAppResourceCSP } from "@ai-sdk/mcp";
import type { UIMessage } from "ai";

type UIMessagePart = UIMessage["parts"][number];

export type AppToolMetadata = {
  readonly resourceUri: string;
  readonly mimeType: string;
  readonly csp?: MCPAppResourceCSP;
};

export type AppToolPart = UIMessagePart & {
  readonly app: AppToolMetadata;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function appMetadata(value: unknown): AppToolMetadata | undefined {
  if (!isRecord(value)) return undefined;

  const { resourceUri, mimeType, csp } = value;
  if (typeof resourceUri !== "string" || typeof mimeType !== "string") {
    return undefined;
  }

  return {
    resourceUri,
    mimeType,
    ...(isRecord(csp) ? { csp } : {}),
  };
}

export function extractToolParts(message: UIMessage): AppToolPart[] {
  const appParts: AppToolPart[] = [];

  for (const part of message.parts) {
    if (!("toolMetadata" in part) || !isRecord(part.toolMetadata)) continue;

    const app = appMetadata(part.toolMetadata.app);
    if (app !== undefined) appParts.push({ ...part, app });
  }

  return appParts;
}
