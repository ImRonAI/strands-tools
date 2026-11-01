# Theme Guidelines

Work here; inherit root/app/host guidance. Use native Prefab Theme and official MCP host styling functions/context. Sources: `docs/reference/prefab/themes.md`, `docs/reference/mcp-apps/host-styles.md`, exact installed public types.

Official helpers include `applyDocumentTheme`, `applyHostStyleVariables`, `applyHostFonts`, `getHostContext` and `onhostcontextchanged`. Native Prefab Theme exposes documented CSS/mode/accent/font fields; obtain exact props from the selected version before use. Integrators explicitly provide tokens; do not scrape their DOM or claim arbitrary CSS/component libraries automatically cross an iframe.

Map semantic surfaces/text/accent/typography/radius/spacing and light/dark tokens consistently. Apply initial context and runtime changes. Honor CSP/font requirements. Keep live media connections stable across a theme or generated-view update. Proof requires computed styles/screenshots under two host themes; receiving one CSS variable is not proof of complete design-system equivalence. No renderer fork or parallel styling interpreter.

## Assigned directory
Project target: `packages/app/src/theme`. Change into this directory before development. This copy is a planning template; the project scaffold is not installed until the worker applies it.
