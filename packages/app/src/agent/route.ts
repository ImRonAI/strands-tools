import express from "express";
import {
  pipeUIMessageStreamToResponse,
  toUIMessageStream,
  type LanguageModel,
} from "ai";
import type { MCPClient } from "@ai-sdk/mcp";
import type { Request } from "express";
import { z } from "zod";

import { createFacilitator } from "./facilitator.js";
import { createModel, ModelNotConfiguredError } from "./model.js";
import {
  createOubliaiMcpClient,
  type Connection,
} from "../mcp/client.js";

const chatRequestSchema = z.object({ prompt: z.string().min(1) }).strict();

export type ChatRouteDeps = {
  readonly createModel?: () => LanguageModel;
  readonly connectionFor: (request: Request) => Connection | undefined;
  readonly createMcpClient?: (connection: Connection) => Promise<MCPClient>;
};

type DevConnectionEnv = {
  readonly NODE_ENV?: string;
  readonly OUBLIAI_DEV_CONNECTION?: string;
  readonly OUBLIAI_MCP_URL?: string;
  readonly OUBLIAI_USER_TOKEN?: string;
};

export function devConnectionFromEnv(
  env: DevConnectionEnv,
): Connection | undefined {
  if (
    env.NODE_ENV === "production" ||
    env.OUBLIAI_DEV_CONNECTION !== "1" ||
    !env.OUBLIAI_MCP_URL ||
    !env.OUBLIAI_USER_TOKEN
  ) {
    return undefined;
  }

  return { url: env.OUBLIAI_MCP_URL, token: env.OUBLIAI_USER_TOKEN };
}

export function createChatRouter(deps: ChatRouteDeps): express.Router {
  const router = express.Router();

  router.post("/api/chat", async (request, response) => {
    const parsed = chatRequestSchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: "invalid_request" });
      return;
    }

    let model: LanguageModel;
    try {
      model = (deps.createModel ?? (() => createModel(process.env)))();
    } catch (error) {
      if (error instanceof ModelNotConfiguredError) {
        response.status(503).json({
          error: "model_not_configured",
          missing: error.missing,
        });
        return;
      }
      throw error;
    }

    const connection = deps.connectionFor(request);
    if (connection === undefined) {
      response.status(401).json({ error: "no_connection" });
      return;
    }

    const client = await (deps.createMcpClient ?? createOubliaiMcpClient)(
      connection,
    );
    try {
      const facilitator = await createFacilitator({ client, model });
      const result = await facilitator.stream({ prompt: parsed.data.prompt });
      await pipeUIMessageStreamToResponse({
        response,
        stream: toUIMessageStream({ stream: result.stream }),
      });
    } finally {
      await client.close();
    }
  });

  return router;
}
