import { copyFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

/**
 * Bundle the customer page.
 *
 * `src/embed.ts` imports the `packages/app` host modules straight from their
 * TypeScript sources (through the `oubliai-app` link in `package.json`), so the
 * same esbuild recipe as `packages/app/build.mjs` applies: browser ESM, with
 * the sandbox proxy base URL injected through the `define` identifier the
 * official `implementation.ts` reads. Nothing is copied or forked.
 */

const ROOT = dirname(fileURLToPath(import.meta.url));
const DIST = join(ROOT, "dist");

const SANDBOX_PORT = process.env.SANDBOX_PORT ?? "8081";
const SANDBOX_PROXY_BASE_URL =
  process.env.SANDBOX_PROXY_BASE_URL ??
  `http://localhost:${SANDBOX_PORT}/sandbox.html`;

await mkdir(DIST, { recursive: true });

await build({
  entryPoints: [join(ROOT, "src", "embed.ts")],
  outfile: join(DIST, "embed.js"),
  bundle: true,
  platform: "browser",
  format: "esm",
  target: "es2022",
  define: {
    __OUBLIAI_SANDBOX_PROXY_BASE_URL__: JSON.stringify(SANDBOX_PROXY_BASE_URL),
  },
});
await copyFile(join(ROOT, "src", "index.html"), join(DIST, "index.html"));

process.stdout.write(
  `built embed page into dist/ (sandbox proxy: ${SANDBOX_PROXY_BASE_URL})\n`,
);
