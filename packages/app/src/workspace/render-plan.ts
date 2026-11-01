import { readUiResource } from "../host/connection.js";
import {
  callTool,
  hasAppHtml,
  type ServerInfo,
  type ToolCallInfo,
} from "../host/implementation.js";
import { type WorkspaceDomain, workspaceCode } from "./domains.js";
import { parsePrefabPayload } from "./open.js";

export function buildRenderPlan(
  serverInfo: ServerInfo,
  domain: WorkspaceDomain,
  rendererUri: string,
): Required<ToolCallInfo> {
  const toolCallInfo = callTool(serverInfo, "execute", {
    code: workspaceCode(domain),
  });
  toolCallInfo.resultPromise = toolCallInfo.resultPromise.then((result) => {
    parsePrefabPayload(result);
    return result;
  });
  toolCallInfo.appResourcePromise = readUiResource(serverInfo, rendererUri);
  if (!hasAppHtml(toolCallInfo)) {
    throw new Error("Renderer resource was not attached to the tool call");
  }
  return toolCallInfo;
}
