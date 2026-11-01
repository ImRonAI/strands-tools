/**
 * Integrator design tokens mapped onto the two documented variable contracts.
 *
 * Integrators explicitly supply tokens (see `src/theme/AGENTS.md`); nothing here
 * scrapes their page or injects CSS into the sandbox. The module only translates
 * a token object into the variable names the official host protocol and the
 * Prefab renderer already define.
 *
 * Two namespaces exist and are deliberately kept disjoint:
 *
 * 1. MCP Apps host-styles variables — the closed union `McpUiStyleVariableKey`
 *    (`node_modules/@modelcontextprotocol/ext-apps/dist/src/spec.types.d.ts:31`,
 *    76 literals) carried on `McpUiHostStyles.variables`
 *    (`spec.types.d.ts:212-217`). `McpUiStyles` is
 *    `Record<McpUiStyleVariableKey, string | undefined>` (`spec.types.d.ts:41`),
 *    i.e. a *total* record: a partial object is rejected with TS2740, so
 *    {@link hostStyleVariables} always returns all 76 keys. There is no
 *    `Partial<McpUiStyles>` alias in the public API.
 *
 * 2. Prefab renderer variables — unnamespaced shadcn/ui names
 *    (`docs/reference/prefab/themes.md:685-698` Variable Reference;
 *    `:700` "Prefab's CSS variables follow shadcn/ui naming conventions";
 *    `:676-677` documented `light_css`/`dark_css` override using `--primary`
 *    and `--ring`). These names are *not* members of `McpUiStyleVariableKey`,
 *    so they are not type-legal inside `styles.variables`. The only type-legal
 *    carrier in `McpUiHostContext` is its forward-compatibility index signature
 *    `[key: string]: unknown` (`spec.types.d.ts:221-223`), which
 *    {@link hostContextFor} uses via {@link PREFAB_VARIABLES_CONTEXT_KEY}.
 *
 * Prefab selects a palette by CSS scope (`:root` vs `.dark`,
 * `themes.md:466`/`:532`/`:624`) and its renderer watches the document `class`
 * (`themes.md:35`, `:67-72`); it does not read `hostContext.theme`. Prefab's own
 * mode field is `"light" | "dark"` (`docs/reference/prefab/app.md:68`), which is
 * exactly `McpUiTheme` (`spec.types.d.ts:23`), so one mode value drives both.
 */

import type {
  McpUiHostContext,
  McpUiStyleVariableKey,
  McpUiStyles,
  McpUiTheme,
} from "@modelcontextprotocol/ext-apps";

/**
 * Prefab CSS variable names, verbatim from the documented Variable Reference
 * table (`docs/reference/prefab/themes.md:685-698`), in table order.
 */
export const PREFAB_VARIABLE_NAMES = [
  // themes.md:685 — Primary buttons, active states
  "--primary",
  "--primary-foreground",
  // themes.md:686 — Secondary buttons
  "--secondary",
  "--secondary-foreground",
  // themes.md:687 — Highlighted surfaces
  "--accent",
  "--accent-foreground",
  // themes.md:688 — Page background and default text
  "--background",
  "--foreground",
  // themes.md:689 — Card surfaces
  "--card",
  "--card-foreground",
  // themes.md:690 — Subdued text and surfaces
  "--muted",
  "--muted-foreground",
  // themes.md:691 — Delete and error states
  "--destructive",
  // themes.md:692 — Semantic status colors
  "--success",
  "--warning",
  "--info",
  // themes.md:693 — Borders and dividers
  "--border",
  // themes.md:694 — Focus rings
  "--ring",
  // themes.md:695 — Chart color palette
  "--chart-1",
  "--chart-2",
  "--chart-3",
  "--chart-4",
  "--chart-5",
  // themes.md:696 — Border radius
  "--radius",
  // themes.md:697 — Card vertical padding (default `1rem`)
  "--card-padding-y",
  // themes.md:698 — Gap between cards in containers (default `1rem`)
  "--layout-gap",
] as const;

/** A documented Prefab CSS variable name. */
export type PrefabVariableName = (typeof PREFAB_VARIABLE_NAMES)[number];

/**
 * MCP Apps host style variable names, verbatim from the
 * `McpUiStyleVariableKey` union (`spec.types.d.ts:31`), in declaration order.
 *
 * Declared here rather than imported from `src/host/host-styles.ts`: that file
 * belongs to the host worker's subtree and is outside this package's typecheck
 * scope (`packages/app/tsconfig.json` `exclude`). The element type is pinned to
 * `McpUiStyleVariableKey`, so any drift from the installed SDK union is a
 * compile error here.
 */
export const HOST_STYLE_VARIABLE_NAMES: readonly McpUiStyleVariableKey[] = [
  "--color-background-primary",
  "--color-background-secondary",
  "--color-background-tertiary",
  "--color-background-inverse",
  "--color-background-ghost",
  "--color-background-info",
  "--color-background-danger",
  "--color-background-success",
  "--color-background-warning",
  "--color-background-disabled",
  "--color-text-primary",
  "--color-text-secondary",
  "--color-text-tertiary",
  "--color-text-inverse",
  "--color-text-ghost",
  "--color-text-info",
  "--color-text-danger",
  "--color-text-success",
  "--color-text-warning",
  "--color-text-disabled",
  "--color-border-primary",
  "--color-border-secondary",
  "--color-border-tertiary",
  "--color-border-inverse",
  "--color-border-ghost",
  "--color-border-info",
  "--color-border-danger",
  "--color-border-success",
  "--color-border-warning",
  "--color-border-disabled",
  "--color-ring-primary",
  "--color-ring-secondary",
  "--color-ring-inverse",
  "--color-ring-info",
  "--color-ring-danger",
  "--color-ring-success",
  "--color-ring-warning",
  "--font-sans",
  "--font-mono",
  "--font-weight-normal",
  "--font-weight-medium",
  "--font-weight-semibold",
  "--font-weight-bold",
  "--font-text-xs-size",
  "--font-text-sm-size",
  "--font-text-md-size",
  "--font-text-lg-size",
  "--font-heading-xs-size",
  "--font-heading-sm-size",
  "--font-heading-md-size",
  "--font-heading-lg-size",
  "--font-heading-xl-size",
  "--font-heading-2xl-size",
  "--font-heading-3xl-size",
  "--font-text-xs-line-height",
  "--font-text-sm-line-height",
  "--font-text-md-line-height",
  "--font-text-lg-line-height",
  "--font-heading-xs-line-height",
  "--font-heading-sm-line-height",
  "--font-heading-md-line-height",
  "--font-heading-lg-line-height",
  "--font-heading-xl-line-height",
  "--font-heading-2xl-line-height",
  "--font-heading-3xl-line-height",
  "--border-radius-xs",
  "--border-radius-sm",
  "--border-radius-md",
  "--border-radius-lg",
  "--border-radius-xl",
  "--border-radius-full",
  "--border-width-regular",
  "--shadow-hairline",
  "--shadow-sm",
  "--shadow-md",
  "--shadow-lg",
];

/**
 * Semantic colour palette for one mode.
 *
 * Keys are the camelCase form of the documented Prefab semantic colours
 * (`themes.md:685-695`); {@link prefabVariables} maps them onto the exact CSS
 * names. Values are CSS colour strings.
 */
export interface ThemePalette {
  /** `--primary` — primary buttons, active states (themes.md:685). */
  primary: string;
  /** `--primary-foreground` (themes.md:685). */
  primaryForeground: string;
  /** `--secondary` — secondary buttons (themes.md:686). */
  secondary: string;
  /** `--secondary-foreground` (themes.md:686). */
  secondaryForeground: string;
  /** `--accent` — highlighted surfaces (themes.md:687). */
  accent: string;
  /** `--accent-foreground` (themes.md:687). */
  accentForeground: string;
  /** `--background` — page background (themes.md:688). */
  background: string;
  /** `--foreground` — default text (themes.md:688). */
  foreground: string;
  /** `--card` — card surfaces (themes.md:689). */
  card: string;
  /** `--card-foreground` (themes.md:689). */
  cardForeground: string;
  /** `--muted` — subdued surfaces (themes.md:690). */
  muted: string;
  /** `--muted-foreground` — subdued text (themes.md:690). */
  mutedForeground: string;
  /** `--destructive` — delete and error states (themes.md:691). */
  destructive: string;
  /** `--success` — semantic status colour (themes.md:692). */
  success: string;
  /** `--warning` — semantic status colour (themes.md:692). */
  warning: string;
  /** `--info` — semantic status colour (themes.md:692). */
  info: string;
  /** `--border` — borders and dividers (themes.md:693). */
  border: string;
  /** `--ring` — focus rings (themes.md:694). */
  ring: string;
  /** `--chart-1` … `--chart-5` chart palette, in order (themes.md:695). */
  chart: readonly [string, string, string, string, string];
}

/**
 * Integrator-supplied design tokens.
 *
 * `radius` feeds `--radius` (themes.md:696) and the host `--border-radius-*`
 * scale. `fonts` feeds the host `--font-sans` / `--font-mono` variables
 * (`spec.types.d.ts:31`); omitted entries keep the defaults.
 */
export interface ThemeTokens {
  light: ThemePalette;
  dark: ThemePalette;
  radius: string;
  fonts?: { sans?: string; mono?: string };
}

/**
 * Key under which the Prefab variable block travels on `McpUiHostContext`.
 *
 * `McpUiStyles` is a closed union of 76 host-style keys (`spec.types.d.ts:31`,
 * `:41`) and `McpUiHostStyles` has no index signature (`spec.types.d.ts:212`),
 * so Prefab's `--primary`-style names cannot be placed in `styles.variables`.
 * `McpUiHostContext` does declare `[key: string]: unknown`
 * ("Allow additional properties for forward compatibility",
 * `spec.types.d.ts:222-223`), which is the only type-legal carrier.
 */
export const PREFAB_VARIABLES_CONTEXT_KEY = "prefabVariables";

const DEFAULT_FONT_SANS =
  "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
const DEFAULT_FONT_MONO =
  "ui-monospace, 'SF Mono', Monaco, 'Cascadia Code', monospace";

/**
 * Neutral, accessible default palette. Integrators override it; these values
 * exist so the host always has a complete, contrast-checked set to send.
 *
 * Light text/background is #18181b on #ffffff; dark is #fafafa on #18181b —
 * both well above the WCAG AA 4.5:1 body-text ratio.
 */
export const DEFAULT_TOKENS: ThemeTokens = {
  light: {
    primary: "#1a56db",
    primaryForeground: "#ffffff",
    secondary: "#f4f4f5",
    secondaryForeground: "#18181b",
    accent: "#eff6ff",
    accentForeground: "#1e3a8a",
    background: "#ffffff",
    foreground: "#18181b",
    card: "#ffffff",
    cardForeground: "#18181b",
    muted: "#f4f4f5",
    mutedForeground: "#52525b",
    destructive: "#b91c1c",
    success: "#15803d",
    warning: "#a16207",
    info: "#1d4ed8",
    border: "#e4e4e7",
    ring: "#1a56db",
    chart: ["#1a56db", "#15803d", "#a16207", "#b91c1c", "#6d28d9"],
  },
  dark: {
    primary: "#60a5fa",
    primaryForeground: "#0b1220",
    secondary: "#27272a",
    secondaryForeground: "#fafafa",
    accent: "#1e3a5f",
    accentForeground: "#dbeafe",
    background: "#18181b",
    foreground: "#fafafa",
    card: "#1f1f23",
    cardForeground: "#fafafa",
    muted: "#27272a",
    mutedForeground: "#a1a1aa",
    destructive: "#f87171",
    success: "#4ade80",
    warning: "#fbbf24",
    info: "#60a5fa",
    border: "#3f3f46",
    ring: "#60a5fa",
    chart: ["#60a5fa", "#4ade80", "#fbbf24", "#f87171", "#c4b5fd"],
  },
  radius: "8px",
};

function paletteFor(tokens: ThemeTokens, mode: McpUiTheme): ThemePalette {
  return mode === "dark" ? tokens.dark : tokens.light;
}

/**
 * Translucent variant of an opaque `#rrggbb` colour.
 *
 * The host contract defines `ghost` and `disabled` variables
 * (`spec.types.d.ts:31`) that are translucent by nature. Non-hex inputs are
 * returned unchanged so integrators may pass any CSS colour function.
 */
function withAlpha(color: string, alpha: number): string {
  const match = /^#([0-9a-fA-F]{6})$/.exec(color);
  if (!match) return color;
  const hex = match[1];
  if (hex === undefined) return color;
  const value = Number.parseInt(hex, 16);
  const r = (value >> 16) & 0xff;
  const g = (value >> 8) & 0xff;
  const b = value & 0xff;
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
 * Prefab renderer CSS variables for one mode.
 *
 * Returns exactly the documented names (`themes.md:685-698`) — suitable for the
 * documented `light_css` / `dark_css` override channel (`themes.md:672-678`),
 * where Prefab switches palettes by CSS scope rather than per-variable mode.
 */
export function prefabVariables(
  tokens: ThemeTokens,
  mode: McpUiTheme,
): Record<PrefabVariableName, string> {
  const p = paletteFor(tokens, mode);
  const [chart1, chart2, chart3, chart4, chart5] = p.chart;
  return {
    "--primary": p.primary,
    "--primary-foreground": p.primaryForeground,
    "--secondary": p.secondary,
    "--secondary-foreground": p.secondaryForeground,
    "--accent": p.accent,
    "--accent-foreground": p.accentForeground,
    "--background": p.background,
    "--foreground": p.foreground,
    "--card": p.card,
    "--card-foreground": p.cardForeground,
    "--muted": p.muted,
    "--muted-foreground": p.mutedForeground,
    "--destructive": p.destructive,
    "--success": p.success,
    "--warning": p.warning,
    "--info": p.info,
    "--border": p.border,
    "--ring": p.ring,
    "--chart-1": chart1,
    "--chart-2": chart2,
    "--chart-3": chart3,
    "--chart-4": chart4,
    "--chart-5": chart5,
    "--radius": tokens.radius,
    // themes.md:697-698 document `1rem` as the default for both.
    "--card-padding-y": "1rem",
    "--layout-gap": "1rem",
  };
}

/**
 * Serialize Prefab variables as a CSS declaration list.
 *
 * Shaped for the documented `Theme(light_css=..., dark_css=...)` fields
 * (`themes.md:672-678`), whose example is a plain `--primary: …; --ring: …;`
 * string. This returns declarations only — it performs no DOM write and no
 * sandbox CSS injection.
 */
export function prefabModeCss(tokens: ThemeTokens, mode: McpUiTheme): string {
  const variables = prefabVariables(tokens, mode);
  return PREFAB_VARIABLE_NAMES.map(
    (name) => `${name}: ${variables[name]};`,
  ).join(" ");
}

/**
 * Complete MCP Apps host style variables for one mode.
 *
 * All 76 keys of `McpUiStyleVariableKey` are populated because `McpUiStyles` is
 * a total `Record` (`spec.types.d.ts:41`): a partial object fails to typecheck
 * with TS2740. The integrator's semantic tokens drive the background, text,
 * border, ring, font and radius families; the remaining scale values are
 * neutral defaults.
 */
export function hostStyleVariables(
  tokens: ThemeTokens,
  mode: McpUiTheme,
): McpUiStyles {
  const p = paletteFor(tokens, mode);
  const sans = tokens.fonts?.sans ?? DEFAULT_FONT_SANS;
  const mono = tokens.fonts?.mono ?? DEFAULT_FONT_MONO;
  const inverse = paletteFor(tokens, mode === "dark" ? "light" : "dark");

  return {
    // Backgrounds — integrator surfaces.
    "--color-background-primary": p.background,
    "--color-background-secondary": p.card,
    "--color-background-tertiary": p.muted,
    "--color-background-inverse": inverse.background,
    "--color-background-ghost": withAlpha(p.background, 0),
    "--color-background-info": p.accent,
    "--color-background-danger": withAlpha(p.destructive, 0.12),
    "--color-background-success": withAlpha(p.success, 0.12),
    "--color-background-warning": withAlpha(p.warning, 0.12),
    "--color-background-disabled": withAlpha(p.muted, 0.5),

    // Text.
    "--color-text-primary": p.foreground,
    "--color-text-secondary": p.mutedForeground,
    "--color-text-tertiary": withAlpha(p.mutedForeground, 0.8),
    "--color-text-inverse": inverse.foreground,
    "--color-text-ghost": withAlpha(p.mutedForeground, 0.5),
    "--color-text-info": p.info,
    "--color-text-danger": p.destructive,
    "--color-text-success": p.success,
    "--color-text-warning": p.warning,
    "--color-text-disabled": withAlpha(p.foreground, 0.5),

    // Borders.
    "--color-border-primary": p.border,
    "--color-border-secondary": withAlpha(p.border, 0.7),
    "--color-border-tertiary": withAlpha(p.border, 0.4),
    "--color-border-inverse": inverse.border,
    "--color-border-ghost": withAlpha(p.border, 0),
    "--color-border-info": p.info,
    "--color-border-danger": p.destructive,
    "--color-border-success": p.success,
    "--color-border-warning": p.warning,
    "--color-border-disabled": withAlpha(p.border, 0.5),

    // Focus rings.
    "--color-ring-primary": p.ring,
    "--color-ring-secondary": p.mutedForeground,
    "--color-ring-inverse": inverse.ring,
    "--color-ring-info": p.info,
    "--color-ring-danger": p.destructive,
    "--color-ring-success": p.success,
    "--color-ring-warning": p.warning,

    // Typography — family.
    "--font-sans": sans,
    "--font-mono": mono,

    // Typography — weight.
    "--font-weight-normal": "400",
    "--font-weight-medium": "500",
    "--font-weight-semibold": "600",
    "--font-weight-bold": "700",

    // Typography — text size.
    "--font-text-xs-size": "0.75rem",
    "--font-text-sm-size": "0.875rem",
    "--font-text-md-size": "1rem",
    "--font-text-lg-size": "1.125rem",

    // Typography — heading size.
    "--font-heading-xs-size": "0.75rem",
    "--font-heading-sm-size": "0.875rem",
    "--font-heading-md-size": "1rem",
    "--font-heading-lg-size": "1.25rem",
    "--font-heading-xl-size": "1.5rem",
    "--font-heading-2xl-size": "1.875rem",
    "--font-heading-3xl-size": "2.25rem",

    // Typography — text line height.
    "--font-text-xs-line-height": "1.4",
    "--font-text-sm-line-height": "1.4",
    "--font-text-md-line-height": "1.5",
    "--font-text-lg-line-height": "1.5",

    // Typography — heading line height.
    "--font-heading-xs-line-height": "1.4",
    "--font-heading-sm-line-height": "1.4",
    "--font-heading-md-line-height": "1.4",
    "--font-heading-lg-line-height": "1.3",
    "--font-heading-xl-line-height": "1.25",
    "--font-heading-2xl-line-height": "1.2",
    "--font-heading-3xl-line-height": "1.1",

    // Radius — `tokens.radius` is the integrator's base (themes.md:696).
    "--border-radius-xs": "2px",
    "--border-radius-sm": "4px",
    "--border-radius-md": "6px",
    "--border-radius-lg": tokens.radius,
    "--border-radius-xl": "12px",
    "--border-radius-full": "9999px",

    // Border width.
    "--border-width-regular": "1px",

    // Shadows.
    "--shadow-hairline": "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
    "--shadow-sm":
      "0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1)",
    "--shadow-md":
      "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1)",
    "--shadow-lg":
      "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)",
  };
}

/**
 * Build the host context a view receives for a given mode.
 *
 * `theme` (`spec.types.d.ts:232`) carries the mode and `platform: "web"`
 * (`spec.types.d.ts:263`) describes this browser host. The 76 host-style
 * variables go in `styles.variables` (`spec.types.d.ts:214`); the Prefab block
 * travels under {@link PREFAB_VARIABLES_CONTEXT_KEY} on the context's
 * forward-compatibility index signature (`spec.types.d.ts:222-223`), because
 * `McpUiStyles` does not admit those names.
 *
 * `extra` is spread last so callers can supply additional documented context
 * fields (`displayMode`, `locale`, `containerDimensions`, …).
 */
export function hostContextFor(
  tokens: ThemeTokens,
  mode: McpUiTheme,
  extra?: Partial<McpUiHostContext>,
): McpUiHostContext {
  return {
    theme: mode,
    platform: "web",
    styles: { variables: hostStyleVariables(tokens, mode) },
    [PREFAB_VARIABLES_CONTEXT_KEY]: prefabVariables(tokens, mode),
    ...extra,
  };
}
