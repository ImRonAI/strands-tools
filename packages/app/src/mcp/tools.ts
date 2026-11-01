import { splitMCPAppTools } from "@ai-sdk/mcp";
import type {
  CallToolResult,
  ListToolsResult,
  MCPClient,
} from "@ai-sdk/mcp";

export const MODEL_VISIBLE_TOOLS = [
  "execute",
  "generate_prefab_ui",
  "get_schema",
  "search",
] as const;

const MODEL_VISIBLE_TOOL_NAMES: ReadonlySet<string> = new Set(
  MODEL_VISIBLE_TOOLS,
);

function modelVisibleDefinitions(definitions: ListToolsResult): ListToolsResult {
  const { modelVisible } = splitMCPAppTools(definitions);

  return {
    ...modelVisible,
    tools: modelVisible.tools.filter(({ name }) =>
      MODEL_VISIBLE_TOOL_NAMES.has(name),
    ),
  };
}

export function listModelVisibleToolNames(
  definitions: ListToolsResult,
): string[] {
  return modelVisibleDefinitions(definitions).tools
    .map(({ name }) => name)
    .sort();
}

export async function modelVisibleToolSet(client: MCPClient) {
  const definitions = await client.listTools();
  return client.toolsFromDefinitions(modelVisibleDefinitions(definitions));
}

export function callExecute(
  client: MCPClient,
  code: string,
): Promise<CallToolResult> {
  return client.callTool({
    name: "execute",
    arguments: { code },
  });
}
