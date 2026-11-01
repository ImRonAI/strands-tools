import { MockLanguageModelV4 } from "ai/test";

const usage = {
  inputTokens: { total: 1, noCache: 1, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 1, text: 1, reasoning: 0 },
};

type FixtureContentPart =
  | {
      readonly type: "tool-call";
      readonly toolCallId: string;
      readonly toolName: string;
      readonly input: string;
    }
  | { readonly type: "text-start"; readonly id: string }
  | { readonly type: "text-delta"; readonly id: string; readonly delta: string }
  | { readonly type: "text-end"; readonly id: string };

type FixtureStreamPart =
  | FixtureContentPart
  | { readonly type: "stream-start"; readonly warnings: [] }
  | {
      readonly type: "finish";
      readonly finishReason: {
        readonly unified: "stop" | "tool-calls";
        readonly raw: "stop" | "tool-calls";
      };
      readonly usage: typeof usage;
    };

function fixtureStream(
  content: FixtureContentPart[],
  reason: "stop" | "tool-calls",
) {
  return {
    stream: new ReadableStream<FixtureStreamPart>({
      start(controller) {
        controller.enqueue({ type: "stream-start", warnings: [] });
        for (const part of content) controller.enqueue(part);
        controller.enqueue({
          type: "finish",
          finishReason: { unified: reason, raw: reason },
          usage,
        });
        controller.close();
      },
    }),
  };
}

export function createExecuteModel(): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doStream: [
      fixtureStream(
        [
          {
            type: "tool-call",
            toolCallId: "execute-prefab",
            toolName: "execute",
            input: JSON.stringify({
              code: "return await call_tool('google_workspace', {})",
            }),
          },
        ],
        "tool-calls",
      ),
      fixtureStream(
        [
          { type: "text-start", id: "final" },
          { type: "text-delta", id: "final", delta: "Done." },
          { type: "text-end", id: "final" },
        ],
        "stop",
      ),
    ],
  });
}

export function createTextModel(): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doStream: fixtureStream(
      [
        { type: "text-start", id: "final" },
        { type: "text-delta", id: "final", delta: "Done." },
        { type: "text-end", id: "final" },
      ],
      "stop",
    ),
  });
}

export function createFailingModel(): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doStream: async () => {
      throw new Error("fixture stream failure");
    },
  });
}
