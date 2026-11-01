# Embed an Oubliai workspace in your own page

This example is a deliberately plain "customer" page (`Acme Telecom Console`)
that mounts one Oubliai `$prefab` workspace with the **user's own MCP
connection** (URL + bearer token) — no product shell, no chat, no agent.

What it demonstrates:

- `packages/app` host modules are importable by an integrator and are the
  whole protocol surface. `src/embed.ts` uses only:
  - `connectToServer(url, headers)` — MCP handshake with the user's bearer header
    (`packages/app/src/host/connection.ts`)
  - `buildRenderPlan(serverInfo, domain, rendererUri)` — the real
    `execute(call_tool('<domain>_workspace'))` result plus the renderer resource
    read, with the `text/html;profile=mcp-app` MIME check and `_meta.ui`
    CSP/permissions precedence (`packages/app/src/workspace/render-plan.ts`)
  - `newAppBridge`, `loadSandboxProxy`, `initializeApp` — the official
    `@modelcontextprotocol/ext-apps` basic-host flow
    (`packages/app/src/host/implementation.ts`)
  - `applyThemeWithPrefab(bridge, tokens, mode)` — the integrator's design tokens
    delivered through `sendHostContextChange` (`packages/app/src/theme/apply.ts`)
- The official **two-origin sandbox**: the page runs on `http://localhost:8090`,
  the sandbox proxy is the `packages/app` sandbox server on
  `http://localhost:8081/sandbox.html`. Nothing in this example implements a
  postMessage relay, renderer or iframe protocol.
- The documented **teardown lifecycle**: `teardownResource({})` → `bridge.close()`
  → `iframe.remove()` on "Close", and `bridge.close()` on `pagehide`.

Nothing from `packages/app` is copied or forked. `package.json` links it as
`oubliai-app` (`link:../../packages/app`) and esbuild bundles the TypeScript
sources directly; `@modelcontextprotocol/ext-apps` is linked from the same
installed tree so there is exactly one copy of the SDK.

## Files

| Path | Role |
|------|------|
| `src/index.html` | The customer page: connection form, workspace picker, `#view` container |
| `src/embed.ts` | `WorkspaceEmbed` (connect / open / close / theme) + page glue |
| `build.mjs` | esbuild → `dist/embed.js`, copies `index.html` |
| `serve.mjs` | express static server for `dist/` on `:8090` + `/healthz` + dev-only `/api/connection` |
| `tests/embed.spec.ts` | Playwright e2e against the real fixture server |
| `tests/global-setup.ts` / `global-teardown.ts` | spawn/stop fixture, CORS shim, `packages/app` sandbox server, embed server |

## Prerequisites

```bash
cd packages/app && pnpm install && pnpm build        # produces dist/serve.js + dist/sandbox/sandbox.html
cd ../../examples/embed && pnpm install && pnpm build # produces dist/embed.js + dist/index.html
```

Node ≥ 22, pnpm. The repo `.venv` must have `packages/server` installed (the
fixture builds the real server).

## Run against the fixture (no credentials)

The e2e harness does everything:

```bash
cd examples/embed
DENO_NO_PACKAGE_JSON=1 pnpm test:e2e      # = playwright test -c tests/playwright.config.ts
```

It spawns, in order: `packages/app/tests/fixtures/static_token_server.py`
(real Oubliai server, mocked Telnyx HTTP, bearer `e2e-token`), the CORS shim
`packages/app/tests/e2e/cors-proxy.mjs`, `packages/app/dist/serve.js` (for the
sandbox origin `:8081`; its `:8080` host origin is unused and gets no
connection), and `serve.mjs` on `:8090` with `OUBLIAI_DEV_CONNECTION=1` so the
form is prefilled. The test asserts:

- the page connects with the fixture token and the picker offers all 14 workspaces,
- `iframe#app-frame` is mounted at `http://localhost:8081/sandbox.html?csp=…`
  with `sandbox="allow-scripts allow-same-origin allow-forms"`,
- the AppBridge handshake completes and the inner view shows the fixture's own
  number `+15555550100`,
- the theme toggle reaches the view without errors,
- `GET http://localhost:8081/sandbox.html` carries a `Content-Security-Policy`
  header containing `script-src`,
- "Close" runs `teardownResource` then `close()` and removes the iframe;
  `pagehide` closes the bridge too,
- no console errors / page errors; a rejected token never mounts a view; the
  sandbox origin 404s anything but `sandbox.html`.

Screenshots land in `test-results/embed-numbers.png` (full page) and
`test-results/embed-numbers-view.png` (the sandbox iframe). `test-results/`,
`playwright-report/`, `dist/` and `node_modules/` are gitignored.

To poke at it by hand with the same fixture:

```bash
# terminal 1 — fixture + CORS shim (prints OUBLIAI_FIXTURE_URL / OUBLIAI_CORS_PROXY_URL)
cd packages/app
../../.venv/bin/python tests/fixtures/static_token_server.py
node tests/e2e/cors-proxy.mjs <OUBLIAI_FIXTURE_URL>

# terminal 2 — sandbox origin (:8081)
cd packages/app && node dist/serve.js

# terminal 3 — embed page (:8090), form prefilled from the dev endpoint
cd examples/embed
OUBLIAI_DEV_CONNECTION=1 OUBLIAI_MCP_URL=<OUBLIAI_CORS_PROXY_URL> OUBLIAI_TOKEN=e2e-token node serve.mjs
open http://localhost:8090
```

## Run against a real server

1. Deploy `packages/server` with the module entry point and allow this page's
   origin for browser CORS: `OUBLIAI_BROWSER_ORIGINS='["http://localhost:8090"]'`
   (see `CLAUDE.md`; FastMCP emits no CORS headers by itself).
2. Point the page at it. Either type the URL and token into the form, or let
   the dev endpoint prefill them:

   ```bash
   cd examples/embed
   OUBLIAI_DEV_CONNECTION=1 \
   OUBLIAI_MCP_URL="$(node -p "require('../../mcp.json').mcpServers['oubliai-telnyx'].url")" \
   OUBLIAI_TOKEN=<the user's bearer token> \
   node serve.mjs
   ```

   `mcp.json` at the repo root holds the server URL; the token is the per-user
   bearer obtained through the server's OAuth flow (BYOK). It is read from the
   environment at request time and **never committed** — there is no `.env`
   in this example and `OUBLIAI_TOKEN` is not written to disk.
3. Start the sandbox origin: `cd packages/app && node dist/serve.js`.

`/api/connection` exists for development only: it returns 404 unless
`OUBLIAI_DEV_CONNECTION=1`, `OUBLIAI_MCP_URL` and `OUBLIAI_TOKEN` are all set.
A production integration obtains the user's token from its own trusted backend
session and hands it to `WorkspaceEmbed.connect(url, token, container, tokens)`.

### Changing ports / origins

- Embed origin: `EMBED_PORT` for `serve.mjs` (default `8090`).
- Sandbox proxy URL baked into the bundle: `SANDBOX_PORT` or
  `SANDBOX_PROXY_BASE_URL` for `build.mjs` (default
  `http://localhost:8081/sandbox.html`).
- The sandbox's referrer allowlist is build-time configuration of
  `packages/app` (`OUBLIAI_ALLOWED_REFERRER`, default
  `^http://(localhost|127\.0\.0\.1)(:|/|$)`). A deployed embed origin must be
  added there and the sandbox rebuilt — not bypassed.

## Security boundaries kept

- **Separate origins.** Page (`:8090`) and sandbox (`:8081`) are different
  origins, as the MCP Apps spec requires. The page never serves `sandbox.html`;
  the sandbox server serves nothing else (asserted in the e2e).
- **CSP from the resource `_meta`.** `buildRenderPlan` reads the renderer
  resource's `_meta.ui.csp` / `permissions`; `loadSandboxProxy` passes them in
  the sandbox URL and the sandbox server turns them into a tamper-proof
  `Content-Security-Policy` **header**. The example neither widens nor drops
  any directive.
- **Referrer allowlist.** The official sandbox proxy refuses to boot unless
  `document.referrer` matches the allowlist; `localhost:8090` satisfies the
  default. Unknown embedding origins fail inside the sandbox.
- **MIME check.** `readUiResource` rejects any renderer resource whose MIME is
  not `text/html;profile=mcp-app`.
- **Untrusted view.** The generated view only talks to the page through the
  AppBridge; the page never reaches into the iframe DOM. Theme reaches the view
  as host context, not injected CSS.
- **BYOK.** The bearer token is the connected user's; it travels only in the
  transport's request headers and is bound to that user's server session.

## Verification

```bash
cd examples/embed
pnpm typecheck
pnpm build
DENO_NO_PACKAGE_JSON=1 pnpm test:e2e
```
