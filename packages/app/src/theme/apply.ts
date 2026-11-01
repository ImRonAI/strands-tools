/**
 * Push theme changes to a connected view through the official AppBridge.
 *
 * The host owns the theme; the view receives it as host context. This module
 * only calls the documented bridge method — it does not touch the view's DOM,
 * inject CSS into the sandbox, or re-implement any renderer.
 */

import type { AppBridge } from "@modelcontextprotocol/ext-apps/app-bridge";
import type { McpUiHostContext, McpUiTheme } from "@modelcontextprotocol/ext-apps";

import {
  PREFAB_VARIABLES_CONTEXT_KEY,
  hostStyleVariables,
  prefabVariables,
  type ThemeTokens,
} from "./tokens.js";

/**
 * The exact bridge surface this module needs.
 *
 * `sendHostContextChange(params: McpUiHostContextChangedNotification["params"])`
 * is declared at
 * `node_modules/@modelcontextprotocol/ext-apps/dist/src/app-bridge.d.ts:942`;
 * narrowing to `Pick` keeps the dependency honest and keeps the unit test free
 * of a live bridge.
 */
export type ThemeBridge = Pick<AppBridge, "sendHostContextChange">;

/**
 * Send a theme change to the view.
 *
 * Emits only the fields that changed — `theme` plus `styles.variables` — which
 * matches the documented partial-update semantics of
 * `sendHostContextChange` ("The context fields that have changed (partial
 * update)", `app-bridge.d.ts:934-942`; params type is `McpUiHostContext` with
 * all fields optional, `spec.types.d.ts:287-291`). The app side applies these
 * with the official `applyDocumentTheme` and `applyHostStyleVariables` helpers
 * (`dist/src/styles.d.ts:62`, `:121`).
 *
 * The Prefab block rides the context's forward-compatibility index signature
 * (`spec.types.d.ts:222-223`) under {@link PREFAB_VARIABLES_CONTEXT_KEY},
 * because Prefab's shadcn variable names are not members of the closed
 * `McpUiStyleVariableKey` union (`spec.types.d.ts:31`).
 *
 * Awaits the call because the method returns `Promise<void> | void`.
 */
export async function applyTheme(
  bridge: ThemeBridge,
  tokens: ThemeTokens,
  mode: McpUiTheme,
): Promise<void> {
  const params: McpUiHostContext = {
    theme: mode,
    styles: { variables: hostStyleVariables(tokens, mode) },
  };
  await bridge.sendHostContextChange(params);
}

/**
 * Send a theme change including the Prefab variable block.
 *
 * Use when the connected view renders a Prefab resource and needs the
 * shadcn-named variables (`docs/reference/prefab/themes.md:685-698`) alongside
 * the host-style variables. Kept separate from {@link applyTheme} so a plain
 * MCP app is never sent context keys it has no use for.
 */
export async function applyThemeWithPrefab(
  bridge: ThemeBridge,
  tokens: ThemeTokens,
  mode: McpUiTheme,
): Promise<void> {
  const params: McpUiHostContext = {
    theme: mode,
    styles: { variables: hostStyleVariables(tokens, mode) },
    [PREFAB_VARIABLES_CONTEXT_KEY]: prefabVariables(tokens, mode),
  };
  await bridge.sendHostContextChange(params);
}

/**
 * The opposite mode.
 *
 * `McpUiTheme` is exactly `"light" | "dark"` (`spec.types.d.ts:23`), matching
 * Prefab's own `mode` field (`docs/reference/prefab/app.md:68`), so the toggle
 * is total.
 */
export function nextMode(mode: McpUiTheme): McpUiTheme {
  return mode === "dark" ? "light" : "dark";
}
