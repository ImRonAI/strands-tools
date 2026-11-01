// Contract: integrator design tokens map onto BOTH documented variable
// namespaces, and reach the view through the official AppBridge host context.
//
// This test needs no server. It asserts the two variable contracts that the
// theme module must honour verbatim:
//
//   (a) Prefab renderer variables — unnamespaced shadcn names, `--` prefixed.
//       docs/reference/prefab/themes.md:685-698 (Variable Reference table),
//       :700 ("Prefab's CSS variables follow shadcn/ui naming conventions"),
//       :676-677 (documented `light_css`/`dark_css` override using `--primary`,
//       `--ring`). Light/dark is one variable set switched by CSS scope
//       (`:root` vs `.dark`, themes.md:466/:532/:624), so each mode must
//       produce its own complete value set.
//
//   (b) MCP Apps host-styles variables — the closed 76-key union
//       `McpUiStyleVariableKey`
//       (node_modules/@modelcontextprotocol/ext-apps/dist/src/spec.types.d.ts:31)
//       carried on `hostContext.styles.variables`
//       (`McpUiHostStyles.variables?: McpUiStyles`, spec.types.d.ts:212-217).
//
// Mode travels as `hostContext.theme` (`McpUiTheme = "light" | "dark"`,
// spec.types.d.ts:23, field at :232) and `platform` is "web"
// (spec.types.d.ts:263). Runtime updates go through
// `sendHostContextChange(params)` (app-bridge.d.ts:942) whose params are a
// partial `McpUiHostContext` (spec.types.d.ts:287-291).
//
// The fake bridge is a plain object literal typed to the exact structural
// slice under test — no mocking library.

import { test, expect } from "vitest";

import type { AppBridge } from "@modelcontextprotocol/ext-apps/app-bridge";
import type {
  McpUiHostContext,
  McpUiStyleVariableKey,
  McpUiTheme,
} from "@modelcontextprotocol/ext-apps";

import {
  DEFAULT_TOKENS,
  HOST_STYLE_VARIABLE_NAMES,
  PREFAB_VARIABLE_NAMES,
  hostContextFor,
  hostStyleVariables,
  prefabVariables,
} from "../../src/theme/tokens.js";
import { applyTheme, nextMode } from "../../src/theme/apply.js";

const MODES: readonly McpUiTheme[] = ["light", "dark"];

test("every documented Prefab variable is present and non-empty in both modes", () => {
  // themes.md:685-698 — the full documented Variable Reference.
  expect(PREFAB_VARIABLE_NAMES).toEqual([
    "--primary",
    "--primary-foreground",
    "--secondary",
    "--secondary-foreground",
    "--accent",
    "--accent-foreground",
    "--background",
    "--foreground",
    "--card",
    "--card-foreground",
    "--muted",
    "--muted-foreground",
    "--destructive",
    "--success",
    "--warning",
    "--info",
    "--border",
    "--ring",
    "--chart-1",
    "--chart-2",
    "--chart-3",
    "--chart-4",
    "--chart-5",
    "--radius",
    "--card-padding-y",
    "--layout-gap",
  ]);

  for (const mode of MODES) {
    const variables = prefabVariables(DEFAULT_TOKENS, mode);
    for (const name of PREFAB_VARIABLE_NAMES) {
      const value = variables[name];
      expect(value, `${mode} is missing ${name}`).toBeTypeOf("string");
      expect(value, `${mode} ${name} must not be empty`).not.toBe("");
    }
    // No undocumented names may be invented into the Prefab namespace.
    expect(Object.keys(variables).sort()).toEqual(
      [...PREFAB_VARIABLE_NAMES].sort(),
    );
  }
});

test("light and dark differ for the page surface variables", () => {
  // themes.md:688 — `background` / `foreground` control page background and
  // default text, so the two modes must not collapse onto one palette.
  const light = prefabVariables(DEFAULT_TOKENS, "light");
  const dark = prefabVariables(DEFAULT_TOKENS, "dark");

  expect(light["--background"]).not.toBe(dark["--background"]);
  expect(light["--foreground"]).not.toBe(dark["--foreground"]);
});

test("host style variables cover the full closed McpUiStyles key union", () => {
  // spec.types.d.ts:41 — McpUiStyles is Record<McpUiStyleVariableKey, ...>, so
  // every one of the 76 documented keys must carry a value.
  expect(HOST_STYLE_VARIABLE_NAMES.length).toBe(76);

  for (const mode of MODES) {
    const variables = hostStyleVariables(DEFAULT_TOKENS, mode);
    for (const name of HOST_STYLE_VARIABLE_NAMES) {
      const value = variables[name];
      expect(value, `${mode} is missing ${name}`).toBeTypeOf("string");
      expect(value, `${mode} ${name} must not be empty`).not.toBe("");
    }
  }

  // Integrator tokens must actually reach the host-styles namespace.
  const light = hostStyleVariables(DEFAULT_TOKENS, "light");
  const dark = hostStyleVariables(DEFAULT_TOKENS, "dark");
  expect(light["--color-background-primary"]).not.toBe(
    dark["--color-background-primary"],
  );
  expect(light["--color-text-primary"]).not.toBe(dark["--color-text-primary"]);
});

test("hostContextFor sets theme, web platform and both variable namespaces", () => {
  for (const mode of MODES) {
    const context = hostContextFor(DEFAULT_TOKENS, mode);

    // spec.types.d.ts:232 / :263
    expect(context.theme).toBe(mode);
    expect(context.platform).toBe("web");

    const variables = context.styles?.variables;
    expect(variables).toBeDefined();
    // The protocol namespace travels in styles.variables.
    for (const name of HOST_STYLE_VARIABLE_NAMES) {
      expect(variables?.[name], `${mode} context is missing ${name}`).toBeTypeOf(
        "string",
      );
    }
  }
});

test("hostContextFor merges caller-supplied extra context fields", () => {
  // spec.types.d.ts:221-282 — McpUiHostContext carries `[key: string]: unknown`
  // for forward compatibility, so extra documented fields must survive.
  const extra: Partial<McpUiHostContext> = {
    displayMode: "inline",
    locale: "en-US",
  };
  const context = hostContextFor(DEFAULT_TOKENS, "dark", extra);

  expect(context.theme).toBe("dark");
  expect(context.displayMode).toBe("inline");
  expect(context.locale).toBe("en-US");
});

test("applyTheme sends exactly one host context change with theme and variables", async () => {
  // app-bridge.d.ts:942 — sendHostContextChange takes a partial host context.
  const calls: McpUiHostContext[] = [];
  const bridge: Pick<AppBridge, "sendHostContextChange"> = {
    sendHostContextChange(params: McpUiHostContext): void {
      calls.push(params);
    },
  };

  await applyTheme(bridge, DEFAULT_TOKENS, "dark");

  expect(calls.length).toBe(1);
  const [params] = calls;
  expect(params?.theme).toBe("dark");

  const variables = params?.styles?.variables;
  expect(variables).toBeDefined();
  const expected = hostStyleVariables(DEFAULT_TOKENS, "dark");
  for (const name of HOST_STYLE_VARIABLE_NAMES) {
    expect(variables?.[name]).toBe(expected[name]);
  }

  // Only the fields that changed are sent (app-bridge.d.ts:934-942).
  expect(Object.keys(params ?? {}).sort()).toEqual(["styles", "theme"]);
});

test("applyTheme awaits a bridge that returns a promise", async () => {
  let resolved = false;
  const bridge: Pick<AppBridge, "sendHostContextChange"> = {
    sendHostContextChange(): Promise<void> {
      return Promise.resolve().then(() => {
        resolved = true;
      });
    },
  };

  await applyTheme(bridge, DEFAULT_TOKENS, "light");
  expect(resolved).toBe(true);
});

test("nextMode toggles between the two documented themes", () => {
  // spec.types.d.ts:23 — McpUiTheme is exactly "light" | "dark".
  expect(nextMode("light")).toBe("dark");
  expect(nextMode("dark")).toBe("light");
});

test("prefab and host style namespaces stay disjoint", () => {
  // The 76-key host union (spec.types.d.ts:31) and the Prefab shadcn names
  // (themes.md:685-698) are separate contracts; conflating them would send
  // keys the host protocol does not define.
  const hostNames = new Set<string>(
    HOST_STYLE_VARIABLE_NAMES as readonly McpUiStyleVariableKey[],
  );
  for (const name of PREFAB_VARIABLE_NAMES) {
    expect(hostNames.has(name), `${name} must not be a host style key`).toBe(
      false,
    );
  }
});
