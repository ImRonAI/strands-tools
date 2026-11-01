import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

/**
 * Build the official AppBridge host, the two-origin sandbox proxy, and the
 * serving entry, following the recipe proven in the build probe:
 *
 *   dist/host/index.js      browser bundle of the page entry
 *   dist/host/index.html    page shell that loads it
 *   dist/sandbox/sandbox.html  official sandbox HTML with the bundle inlined
 *   dist/serve.js           node bundle of the vendored express servers
 *
 * Ports and the sandbox referrer allowlist are build-time configuration; the
 * vendored sources read them through `define` identifiers so the official code
 * stays byte-identical apart from the documented `// oubliai:` edits.
 */

const PACKAGE_ROOT = dirname(fileURLToPath(import.meta.url));
const HOST_DIR = join(PACKAGE_ROOT, "src", "host");
const DIST = join(PACKAGE_ROOT, "dist");

const HOST_PORT = process.env.HOST_PORT ?? "8080";
const SANDBOX_PORT = process.env.SANDBOX_PORT ?? "8081";
const SANDBOX_PROXY_BASE_URL =
  process.env.SANDBOX_PROXY_BASE_URL ??
  `http://localhost:${SANDBOX_PORT}/sandbox.html`;
const ALLOWED_REFERRER =
  process.env.OUBLIAI_ALLOWED_REFERRER ??
  String.raw`^http://(localhost|127\.0\.0\.1)(:|/|$)`;

const SANDBOX_SCRIPT_TAG =
  '<script type="module" src="/src/sandbox.ts"></script>';

const PAGE_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light dark" />
    <title>Oubliai host</title>
    <style>
      * { box-sizing: border-box; }
      body {
        margin: 0;
        background: var(--color-background-secondary);
        color: var(--color-text-primary);
        font-family: var(--font-sans);
      }
      #app {
        display: grid;
        gap: 20px;
        width: min(100%, 1280px);
        margin: 0 auto;
        padding: 24px;
      }
      .host-controls {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }
      select, input, button {
        min-height: 40px;
        border: var(--border-width-regular) solid var(--color-border-secondary);
        border-radius: var(--border-radius-md);
        background: var(--color-background-primary);
        color: var(--color-text-primary);
        font: inherit;
      }
      select, input { padding: 8px 12px; }
      button {
        padding: 8px 16px;
        cursor: pointer;
        font-weight: var(--font-weight-semibold);
      }
      button:focus-visible, select:focus-visible, input:focus-visible {
        outline: 2px solid var(--color-ring-primary);
        outline-offset: 2px;
      }
      button:disabled {
        background: var(--color-background-tertiary);
        color: light-dark(#4b5563, #d1d5db);
        cursor: not-allowed;
      }
      #view:empty { display: none; }
      #app-frame { display: block; }
      #media-panel {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: end;
        gap: 12px;
        padding: 20px;
        border: var(--border-width-regular) solid var(--color-border-primary);
        border-radius: var(--border-radius-xl);
        background: var(--color-background-primary);
        box-shadow: var(--shadow-sm);
      }
      #media-panel-title, #media-panel label, #media-panel output {
        grid-column: 1 / -1;
      }
      #media-panel-title {
        margin: 0;
        font-size: var(--font-heading-lg-size);
        line-height: var(--font-heading-lg-line-height);
      }
      #media-panel label {
        color: var(--color-text-secondary);
        font-size: var(--font-text-sm-size);
        font-weight: var(--font-weight-medium);
      }
      #media-panel output {
        min-height: var(--font-text-sm-line-height);
        color: var(--color-text-secondary);
        font-size: var(--font-text-sm-size);
      }
      #media-panel output[data-media-state="denied"],
      #media-panel output[data-media-state="error"] {
        color: var(--color-text-danger);
      }
      #media-panel output[data-media-state="mic-ready"] {
        color: var(--color-text-success);
      }
      @media (max-width: 560px) {
        #app { padding: 16px; }
        #media-panel { grid-template-columns: 1fr; }
        #media-panel button { width: 100%; }
      }
    </style>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/index.js"></script>
  </body>
</html>
`;

await mkdir(join(DIST, "host"), { recursive: true });
await mkdir(join(DIST, "sandbox"), { recursive: true });

// Host page bundle.
await build({
  entryPoints: [join(HOST_DIR, "index.ts")],
  outfile: join(DIST, "host", "index.js"),
  bundle: true,
  platform: "browser",
  format: "esm",
  target: "es2022",
  define: {
    __OUBLIAI_SANDBOX_PROXY_BASE_URL__: JSON.stringify(SANDBOX_PROXY_BASE_URL),
  },
});
await writeFile(join(DIST, "host", "index.html"), PAGE_HTML, "utf8");

// Sandbox proxy bundle, inlined into the official sandbox HTML.
const sandboxBundle = await build({
  entryPoints: [join(HOST_DIR, "sandbox.ts")],
  bundle: true,
  platform: "browser",
  format: "esm",
  target: "es2022",
  write: false,
  define: {
    __OUBLIAI_ALLOWED_REFERRER__: JSON.stringify(ALLOWED_REFERRER),
  },
});
const sandboxCode = sandboxBundle.outputFiles[0];
if (!sandboxCode) {
  throw new Error("esbuild produced no sandbox output file");
}
const sandboxHtml = await readFile(join(HOST_DIR, "sandbox.html"), "utf8");
if (!sandboxHtml.includes(SANDBOX_SCRIPT_TAG)) {
  throw new Error(
    `sandbox.html no longer contains the expected script tag: ${SANDBOX_SCRIPT_TAG}`,
  );
}
await writeFile(
  join(DIST, "sandbox", "sandbox.html"),
  sandboxHtml.replace(
    SANDBOX_SCRIPT_TAG,
    () =>
      '<script type="module">' +
      sandboxCode.text.replace(/<\/script/gi, String.raw`<\/script`) +
      "</script>",
  ),
  "utf8",
);

// Serving entry: node bundle with runtime packages left external.
await build({
  entryPoints: [join(HOST_DIR, "serve.ts")],
  outfile: join(DIST, "serve.js"),
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node22",
  packages: "external",
});

process.stdout.write(
  `built host (:${HOST_PORT}) and sandbox (:${SANDBOX_PORT}) bundles into dist/\n`,
);
