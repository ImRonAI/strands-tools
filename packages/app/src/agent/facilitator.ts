import {
  isStepCount,
  readUIMessageStream,
  ToolLoopAgent,
  type LanguageModel,
  type UIMessage,
} from "ai";
import type { MCPClient } from "@ai-sdk/mcp";

import { modelVisibleToolSet } from "../mcp/tools.js";

const DEFAULT_MAX_STEPS = 8;

type FacilitatorTools = Awaited<ReturnType<typeof modelVisibleToolSet>>;

export type Facilitator = ToolLoopAgent<never, FacilitatorTools>;

export type CreateFacilitatorOptions = {
  readonly client: MCPClient;
  readonly model: LanguageModel;
  readonly maxSteps?: number;
  readonly instructions?: string;
};

export async function createFacilitator({
  client,
  model,
  maxSteps = DEFAULT_MAX_STEPS,
  instructions,
}: CreateFacilitatorOptions): Promise<Facilitator> {
  const tools = await modelVisibleToolSet(client);

  return new ToolLoopAgent({
    model,
    tools,
    instructions,
    stopWhen: isStepCount(maxSteps),
  });
}

export async function runFacilitator(
  facilitator: Facilitator,
  prompt: string,
): Promise<UIMessage> {
  const result = await facilitator.stream({ prompt });
  let finalMessage: UIMessage | undefined;

  for await (const message of readUIMessageStream({
    stream: result.toUIMessageStream(),
  })) {
    finalMessage = message;
  }

  if (finalMessage === undefined) {
    throw new Error("The facilitator completed without producing a UI message.");
  }

  return finalMessage;
}
