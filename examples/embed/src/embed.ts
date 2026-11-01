/**
 * Customer page that embeds one Oubliai `$prefab` workspace.
 *
 * Everything protocol-related is the `packages/app` host (which is itself the
 * official `@modelcontextprotocol/ext-apps` basic-host with documented
 * `// oubliai:` edits) plus the public `AppBridge`:
 *
 *   connectToServer()      MCP handshake with the user's own URL + bearer token
 *                          (`src/host/connection.ts`)
 *   buildRenderPlan()      `execute(call_tool('<domain>_workspace'))` + renderer
 *                          resource read with the MIME / `_meta.ui` checks
 *                          (`src/workspace/render-plan.ts`)
 *   newAppBridge()         the official AppBridge wiring (`src/host/implementation.ts`)
 *   loadSandboxProxy()     the official two-origin sandbox iframe, CSP in the URL
 *   initializeApp()        connect, `sendSandboxResourceReady`, wait for
 *                          `oninitialized`, `sendToolInput`, `sendToolResult`
 *   applyThemeWithPrefab() integrator design tokens -> `sendHostContextChange`
 *                          (`src/theme/apply.ts`)
 *
 * The page adds only what an integrator owns: the connection form, the
 * workspace picker, its design tokens, and the mount / unmount lifecycle. It
 * never talks to the iframe directly.
 */

import {
  getToolUiResourceUri,
  type AppBridge,
} from "@modelcontextprotocol/ext-apps/app-bridge";
import { connectToServer } from "../../../packages/app/src/host/connection.js";
import {
  initializeApp,
  loadSandboxProxy,
  log,
  newAppBridge,
  type ServerInfo,
} from "../../../packages/app/src/host/implementation.js";
import {
  getTheme,
  onThemeChange,
  toggleTheme,
} from "../../../packages/app/src/host/theme.js";
import { applyThemeWithPrefab } from "../../../packages/app/src/theme/apply.js";
import {
  hostStyleVariables,
  type ThemeTokens,
} from "../../../packages/app/src/theme/tokens.js";
import {
  isWorkspaceDomain,
  WORKSPACE_DOMAINS,
  type WorkspaceDomain,
} from "../../../packages/app/src/workspace/domains.js";
import { buildRenderPlan } from "../../../packages/app/src/workspace/render-plan.js";

/** The tool whose `_meta.ui.resourceUri` names the Prefab renderer. */
const RENDERER_TOOL_NAME = "generate_prefab_ui";

/**
 * Acme's own design tokens. These are the integrator's brand, mapped by
 * `packages/app` onto the documented host-style and Prefab variable names.
 */
const ACME_TOKENS: ThemeTokens = {
  light: {
    primary: "#0f766e",
    primaryForeground: "#ffffff",
    secondary: "#f0fdfa",
    secondaryForeground: "#134e4a",
    accent: "#ccfbf1",
    accentForeground: "#134e4a",
    background: "#fafaf9",
    foreground: "#1c1917",
    card: "#ffffff",
    cardForeground: "#1c1917",
    muted: "#f5f5f4",
    mutedForeground: "#57534e",
    destructive: "#b91c1c",
    success: "#15803d",
    warning: "#a16207",
    info: "#0f766e",
    border: "#e7e5e4",
    ring: "#0f766e",
    chart: ["#0f766e", "#15803d", "#a16207", "#b91c1c", "#6d28d9"],
  },
  dark: {
    primary: "#2dd4bf",
    primaryForeground: "#042f2e",
    secondary: "#1c1917",
    secondaryForeground: "#fafaf9",
    accent: "#134e4a",
    accentForeground: "#ccfbf1",
    background: "#0c0a09",
    foreground: "#fafaf9",
    card: "#1c1917",
    cardForeground: "#fafaf9",
    muted: "#292524",
    mutedForeground: "#a8a29e",
    destructive: "#f87171",
    success: "#4ade80",
    warning: "#fbbf24",
    info: "#2dd4bf",
    border: "#44403c",
    ring: "#2dd4bf",
    chart: ["#2dd4bf", "#4ade80", "#fbbf24", "#f87171", "#c4b5fd"],
  },
  radius: "6px",
};

/** Debug state the e2e test reads; mirrors `window.__oubliaiHost` in the app. */
export interface EmbedDebugState {
  state: "idle" | "connecting" | "connected" | "mounting" | "rendered" | "error";
  lastError?: string;
  bridgeInitialized: boolean;
  teardownRequested: boolean;
  teardownOutcome?: "acknowledged" | "declined";
  bridgeClosed: boolean;
  theme: "light" | "dark";
}

declare global {
  interface Window {
    __oubliaiEmbed: EmbedDebugState;
  }
}

const debug: EmbedDebugState = {
  state: "idle",
  bridgeInitialized: false,
  teardownRequested: false,
  bridgeClosed: false,
  theme: getTheme(),
};
window.__oubliaiEmbed = debug;

interface MountedView {
  bridge: AppBridge;
  iframe: HTMLIFrameElement;
  initialized: boolean;
}

/**
 * A connected Oubliai server plus the one workspace view it currently shows.
 * `open()` replaces a previous view through `close()` first.
 */
export class WorkspaceEmbed {
  #view: MountedView | undefined;

  private constructor(
    private readonly serverInfo: ServerInfo,
    private readonly rendererUri: string,
    private readonly container: HTMLElement,
    private readonly tokens: ThemeTokens,
  ) {}

  /**
   * Connect with the user's own MCP URL and bearer token. The token travels
   * only in the transport's request headers (`connection.ts`); nothing here
   * stores it.
   */
  static async connect(
    url: string,
    token: string,
    container: HTMLElement,
    tokens: ThemeTokens,
  ): Promise<WorkspaceEmbed> {
    const serverInfo = await connectToServer(new URL(url), {
      Authorization: `Bearer ${token}`,
    });
    const rendererTool = serverInfo.tools.get(RENDERER_TOOL_NAME);
    if (!rendererTool) {
      throw new Error(`Server does not expose ${RENDERER_TOOL_NAME}`);
    }
    const rendererUri = getToolUiResourceUri(rendererTool);
    if (!rendererUri) {
      throw new Error(`${RENDERER_TOOL_NAME} declares no UI resource`);
    }
    return new WorkspaceEmbed(serverInfo, rendererUri, container, tokens);
  }

  get mounted(): boolean {
    return this.#view !== undefined;
  }

  /** Mount one `$prefab` workspace in the official sandbox. */
  async open(domain: WorkspaceDomain): Promise<void> {
    await this.close();

    const iframe = document.createElement("iframe");
    iframe.id = "app-frame";
    iframe.title = `Oubliai ${domain} workspace`;
    iframe.style.cssText = "width:100%;height:640px;border:0";
    this.container.appendChild(iframe);

    // Real tool result (`structuredContent.$prefab`) + renderer resource with
    // its declared CSP/permissions, exactly as the product host does.
    const plan = buildRenderPlan(this.serverInfo, domain, this.rendererUri);
    const { csp, permissions } = await plan.appResourcePromise;

    // Load the official sandbox proxy first. `newAppBridge` observes the
    // iframe with a ResizeObserver whose first callback sends a host-context
    // notification; creating the bridge only once the proxy is ready keeps
    // that callback after `connect()` (the first step of `initializeApp`).
    const proxyReady = loadSandboxProxy(iframe, csp, permissions);
    debug.bridgeInitialized = false;
    debug.bridgeClosed = false;
    debug.teardownRequested = false;
    delete debug.teardownOutcome;
    await proxyReady;

    const bridge = newAppBridge(this.serverInfo, iframe);
    const view: MountedView = { bridge, iframe, initialized: false };
    // `addEventListener("initialized", …)` is the documented composable path
    // (`app-bridge.d.ts` deprecates replacing `oninitialized`); `initializeApp`
    // keeps its own `oninitialized` hook untouched.
    bridge.addEventListener("initialized", () => {
      view.initialized = true;
      debug.bridgeInitialized = true;
      debug.state = "rendered";
      // Push the integrator's tokens once the view is listening.
      void applyThemeWithPrefab(bridge, this.tokens, getTheme());
    });
    const previousOnClose = bridge.onclose;
    bridge.onclose = () => {
      debug.bridgeClosed = true;
      previousOnClose?.();
    };
    this.#view = view;

    await initializeApp(iframe, bridge, plan);
  }

  /**
   * Documented teardown: `teardownResource` (graceful shutdown request to the
   * view), then `close()` on the bridge, then remove the iframe.
   *
   * The documented example wraps `teardownResource` in try/catch: a view that
   * does not register an `onteardown` handler answers "Method not found", and
   * the host must still unmount.
   */
  async close(): Promise<void> {
    const view = this.#view;
    if (!view) return;
    this.#view = undefined;
    if (view.initialized) {
      debug.teardownRequested = true;
      try {
        await view.bridge.teardownResource({});
        debug.teardownOutcome = "acknowledged";
      } catch (error) {
        debug.teardownOutcome = "declined";
        log.warn("Teardown not acknowledged by the view:", error);
      }
    }
    await view.bridge.close();
    view.iframe.remove();
    debug.bridgeInitialized = false;
    if (debug.state === "rendered" || debug.state === "mounting") {
      debug.state = "connected";
    }
  }

  /** Forward the integrator's theme change through the bridge. */
  async setTheme(mode: "light" | "dark"): Promise<void> {
    const view = this.#view;
    if (view?.initialized) {
      await applyThemeWithPrefab(view.bridge, this.tokens, mode);
    }
  }

  /** Close the bridge on page hide; the user is leaving, no graceful wait. */
  closeOnPageHide(): void {
    const view = this.#view;
    if (!view) return;
    this.#view = undefined;
    void view.bridge.close();
  }
}

// ---------------------------------------------------------------- page glue

interface Controls {
  banner: HTMLElement;
  urlInput: HTMLInputElement;
  tokenInput: HTMLInputElement;
  connectButton: HTMLButtonElement;
  workspaceSelect: HTMLSelectElement;
  openButton: HTMLButtonElement;
  closeButton: HTMLButtonElement;
  themeButton: HTMLButtonElement;
  view: HTMLElement;
}

function requireElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing ${selector}`);
  return element;
}

function controls(): Controls {
  const workspaceSelect = requireElement<HTMLSelectElement>("#workspace-select");
  for (const domain of WORKSPACE_DOMAINS) {
    const option = document.createElement("option");
    option.value = domain;
    option.textContent = domain;
    workspaceSelect.appendChild(option);
  }
  return {
    banner: requireElement("#embed-banner"),
    urlInput: requireElement("#mcp-url"),
    tokenInput: requireElement("#mcp-token"),
    connectButton: requireElement("#connect"),
    workspaceSelect,
    openButton: requireElement("#open-workspace"),
    closeButton: requireElement("#close-workspace"),
    themeButton: requireElement("#theme-toggle"),
    view: requireElement("#view"),
  };
}

function showError(banner: HTMLElement, error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  debug.state = "error";
  debug.lastError = message;
  banner.textContent = message;
  banner.hidden = false;
}

/**
 * Development convenience: the page's own backend may expose the connection
 * (`serve.mjs` `/api/connection`, only with `OUBLIAI_DEV_CONNECTION=1`). A real
 * integration obtains the user's token from its trusted backend session.
 */
async function prefillConnection(ui: Controls): Promise<void> {
  try {
    const response = await fetch("/api/connection");
    if (!response.ok) return;
    const connection = (await response.json()) as { url: string; token: string };
    ui.urlInput.value = connection.url;
    ui.tokenInput.value = connection.token;
  } catch {
    // No prefill available; the user types the connection.
  }
}

function applyPageStyles(): void {
  const variables = hostStyleVariables(ACME_TOKENS, getTheme());
  for (const [name, value] of Object.entries(variables)) {
    if (value !== undefined) {
      document.documentElement.style.setProperty(name, value);
    }
  }
}

async function main(): Promise<void> {
  const ui = controls();
  applyPageStyles();
  ui.themeButton.textContent = `Theme: ${getTheme()}`;
  await prefillConnection(ui);

  let embed: WorkspaceEmbed | undefined;

  ui.connectButton.addEventListener("click", () => {
    ui.banner.hidden = true;
    delete debug.lastError;
    debug.state = "connecting";
    ui.connectButton.disabled = true;
    WorkspaceEmbed.connect(
      ui.urlInput.value.trim(),
      ui.tokenInput.value.trim(),
      ui.view,
      ACME_TOKENS,
    ).then(
      (connected) => {
        embed = connected;
        debug.state = "connected";
        ui.workspaceSelect.disabled = false;
        ui.openButton.disabled = false;
      },
      (error: unknown) => {
        ui.connectButton.disabled = false;
        showError(ui.banner, error);
      },
    );
  });

  ui.openButton.addEventListener("click", () => {
    const domain = ui.workspaceSelect.value;
    if (!embed || !isWorkspaceDomain(domain)) return;
    ui.banner.hidden = true;
    debug.state = "mounting";
    ui.openButton.disabled = true;
    embed.open(domain).then(
      () => {
        ui.openButton.disabled = false;
        ui.closeButton.disabled = false;
      },
      (error: unknown) => {
        ui.openButton.disabled = false;
        showError(ui.banner, error);
      },
    );
  });

  ui.closeButton.addEventListener("click", () => {
    if (!embed) return;
    ui.closeButton.disabled = true;
    embed.close().catch((error: unknown) => showError(ui.banner, error));
  });

  ui.themeButton.addEventListener("click", () => {
    toggleTheme();
  });
  onThemeChange((theme) => {
    debug.theme = theme;
    ui.themeButton.textContent = `Theme: ${theme}`;
    applyPageStyles();
    void embed?.setTheme(theme);
  });

  window.addEventListener(
    "pagehide",
    () => {
      embed?.closeOnPageHide();
    },
    { once: true },
  );
}

main().catch((error: unknown) => {
  debug.state = "error";
  debug.lastError = error instanceof Error ? error.message : String(error);
  log.error("Embed startup failed:", error);
});
