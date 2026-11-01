import {
  getToolUiResourceUri,
  type AppBridge,
} from "@modelcontextprotocol/ext-apps/app-bridge";
import {
  initializeApp,
  loadSandboxProxy,
  log,
  newAppBridge,
  type ServerInfo,
} from "./implementation.js";
import {
  connectToServer,
  type ConnectionDescriptor,
} from "./connection.js";
import { mintVoiceToken } from "../media/credentials.js";
import { mountMediaPanel } from "../media/panel.js";
import { createVoiceSession } from "../media/voice.js";
import { createOubliaiMcpClient } from "../mcp/client.js";
import {
  isWorkspaceDomain,
  WORKSPACE_DOMAINS,
  type WorkspaceDomain,
} from "../workspace/domains.js";
import { buildRenderPlan } from "../workspace/render-plan.js";
import { HOST_STYLE_VARIABLES } from "./host-styles.js";
import { getTheme, toggleTheme } from "./theme.js";

const RENDERER_TOOL_NAME = "generate_prefab_ui";

interface HostDebugState {
  state: "idle" | "connected" | "rendered" | "error";
  lastError?: string;
  bridgeInitialized: boolean;
}

declare global {
  interface Window {
    __oubliaiHost: HostDebugState;
  }
}

const hostState: HostDebugState = { state: "idle", bridgeInitialized: false };
window.__oubliaiHost = hostState;
for (const [name, value] of Object.entries(HOST_STYLE_VARIABLES)) {
  document.documentElement.style.setProperty(name, String(value));
}

function fail(message: string, banner: HTMLElement): void {
  hostState.state = "error";
  hostState.lastError = message;
  banner.textContent = message;
  banner.hidden = false;
}

interface MountedView {
  bridge: AppBridge;
  iframe: HTMLIFrameElement;
  initialized: boolean;
}

let mounted: MountedView | undefined;

/**
 * Documented teardown: request graceful shutdown, close, then unmount.
 *
 * `teardownResource` is awaited so the view can finish, but per the AppBridge
 * documentation's teardown example the host still unmounts when the request
 * fails (e.g. a view that registers no `ui/resource-teardown` handler answers
 * "Method not found").
 */
async function unmount(view: MountedView): Promise<void> {
  if (view.initialized) {
    try {
      await view.bridge.teardownResource({});
    } catch (error) {
      log.warn("Teardown failed:", error);
    }
  }
  await view.bridge.close();
  view.iframe.remove();
}

async function renderWorkspace(
  serverInfo: ServerInfo,
  rendererUri: string,
  domain: WorkspaceDomain,
  container: HTMLElement,
): Promise<void> {
  if (mounted) {
    const previous = mounted;
    mounted = undefined;
    hostState.bridgeInitialized = false;
    await unmount(previous);
  }

  const iframe = document.createElement("iframe");
  iframe.id = "app-frame";
  iframe.style.cssText = "width:100%;height:640px;border:0";
  container.appendChild(iframe);

  // The real workspace tool result (structuredContent `$prefab`) is what the
  // view receives; the renderer resource supplies its HTML.
  const toolCallInfo = buildRenderPlan(serverInfo, domain, rendererUri);

  const { csp, permissions } = await toolCallInfo.appResourcePromise;
  const bridge = newAppBridge(serverInfo, iframe);
  const view: MountedView = { bridge, iframe, initialized: false };
  const previousOnInitialized = bridge.oninitialized;
  bridge.oninitialized = (params) => {
    view.initialized = true;
    hostState.bridgeInitialized = true;
    hostState.state = "rendered";
    previousOnInitialized?.(params);
  };
  mounted = view;

  await loadSandboxProxy(iframe, csp, permissions);
  await initializeApp(iframe, bridge, toolCallInfo);
}

interface HostControls {
  banner: HTMLElement;
  mediaContainer: HTMLElement;
  select: HTMLSelectElement;
  viewContainer: HTMLElement;
}

function buildControls(app: HTMLElement): HostControls {
  const banner = document.createElement("p");
  banner.id = "host-banner";
  banner.hidden = true;

  const select = document.createElement("select");
  select.id = "workspace-select";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select a workspace…";
  select.appendChild(placeholder);
  for (const domain of WORKSPACE_DOMAINS) {
    const option = document.createElement("option");
    option.value = domain;
    option.textContent = domain;
    select.appendChild(option);
  }

  const themeButton = document.createElement("button");
  themeButton.id = "theme-toggle";
  themeButton.type = "button";
  themeButton.textContent = `Theme: ${getTheme()}`;
  themeButton.addEventListener("click", () => {
    const theme = toggleTheme();
    themeButton.textContent = `Theme: ${theme}`;
    mounted?.bridge.sendHostContextChange({
      theme,
      styles: { variables: HOST_STYLE_VARIABLES },
    });
  });

  const controls = document.createElement("div");
  controls.className = "host-controls";
  controls.append(select, themeButton);
  const viewContainer = document.createElement("div");
  viewContainer.id = "view";
  const mediaContainer = document.createElement("div");
  mediaContainer.id = "media";
  app.append(banner, controls, viewContainer, mediaContainer);

  return { banner, mediaContainer, select, viewContainer };
}

async function main(): Promise<void> {
  const app = document.getElementById("app");
  if (!app) throw new Error("Missing #app container");
  const { banner, mediaContainer, select, viewContainer } = buildControls(app);

  const response = await fetch("/api/connection");
  if (!response.ok) {
    fail("Connection not configured", banner);
    return;
  }
  const connection = (await response.json()) as ConnectionDescriptor;

  const serverInfo = await connectToServer(
    new URL(connection.url),
    connection.headers,
  );
  const rendererTool = serverInfo.tools.get(RENDERER_TOOL_NAME);
  if (!rendererTool) {
    fail(`Server does not expose ${RENDERER_TOOL_NAME}`, banner);
    return;
  }
  const rendererUri = getToolUiResourceUri(rendererTool);
  if (!rendererUri) {
    fail(`${RENDERER_TOOL_NAME} declares no UI resource`, banner);
    return;
  }

  const authorization =
    connection.headers["Authorization"] ?? connection.headers["authorization"];
  const bearerPrefix = "Bearer ";
  if (!authorization?.startsWith(bearerPrefix)) {
    fail("Connection does not provide bearer authorization", banner);
    return;
  }
  const mediaClient = await createOubliaiMcpClient({
    url: connection.url,
    token: authorization.slice(bearerPrefix.length),
  });
  mountMediaPanel(mediaContainer, {
    createVoiceSession,
    mintVoiceToken: (credentialId) => mintVoiceToken(mediaClient, credentialId),
  });

  hostState.state = "connected";

  select.addEventListener("change", () => {
    const domain = select.value;
    if (!isWorkspaceDomain(domain)) return;
    banner.hidden = true;
    renderWorkspace(serverInfo, rendererUri, domain, viewContainer).catch(
      (error: unknown) => {
        fail(error instanceof Error ? error.message : String(error), banner);
      },
    );
  });

  window.addEventListener(
    "pagehide",
    () => {
      void mounted?.bridge.close();
      void mediaClient.close();
    },
    { once: true },
  );
}

main().catch((error: unknown) => {
  hostState.state = "error";
  hostState.lastError = error instanceof Error ? error.message : String(error);
  log.error("Host startup failed:", error);
});
