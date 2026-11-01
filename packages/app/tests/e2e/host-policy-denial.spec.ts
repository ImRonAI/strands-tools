import { expect, test } from "@playwright/test";

/**
 * Host policy denial (plan A3) using only the checks the vendored official
 * host already performs:
 *
 * 1. Referrer allowlist — `src/host/sandbox.ts` throws before creating the
 *    inner iframe or announcing `ui/notifications/sandbox-proxy-ready` when
 *    `document.referrer` does not match `__OUBLIAI_ALLOWED_REFERRER__`
 *    (`^http://(localhost|127\.0\.0\.1)(:|/|$)` from `build.mjs`).
 *    `src/host/serve.ts` itself does not gate on `Referer`; it always serves
 *    `sandbox.html` with the CSP header, so the HTTP status is 200 and the
 *    denial is proven at the embedding level. The foreign embedder is the
 *    same express host reached through `http://[::1]:8080`: a real origin the
 *    browser can embed from (Chromium blocks route-fulfilled fake origins
 *    such as `evil.example` from reaching loopback at all), yet one the
 *    allowlist does not accept. `http://localhost:8080` is the positive control.
 *
 * 2. MIME contract — `readUiResource` (`src/host/connection.ts`, the
 *    official `getUiResource` with the bearer header) rejects a renderer
 *    whose `mimeType` is not `text/html;profile=mcp-app`. The test tampers
 *    with the server's `resources/read` response on the wire (a misbehaving
 *    server, not a host hook) and asserts the host records the error and
 *    never loads the sandbox.
 */

const HOST_ORIGIN = "http://localhost:8080";
const SANDBOX_HTML = "http://localhost:8081/sandbox.html";
const FOREIGN_ORIGIN = "http://[::1]:8080";
const PROXY_READY = "ui/notifications/sandbox-proxy-ready";
const APP_MIME = "text/html;profile=mcp-app";

interface HostDebugState {
  state: "idle" | "connected" | "rendered" | "error";
  lastError?: string;
  bridgeInitialized: boolean;
}

declare global {
  interface Window {
    __oubliaiHost?: HostDebugState;
    __sandboxMessages?: string[];
  }
}

/** A minimal embedding page that records every `postMessage` it receives. */
const EMBEDDING_PAGE = `<!doctype html><html><body>
<script>
  window.__sandboxMessages = [];
  window.addEventListener("message", (event) => {
    window.__sandboxMessages.push(String(event.data && event.data.method));
  });
</script>
<iframe id="sandbox" src="${SANDBOX_HTML}"></iframe>
</body></html>`;

/**
 * Load the embedding page under `origin`. `page.goto` establishes the real
 * origin from the express host server; `setContent` then replaces the document
 * body while keeping that origin, so `document.referrer` seen by the sandbox is
 * the genuine embedding origin.
 */
async function embedSandboxFrom(
  page: import("@playwright/test").Page,
  origin: string,
): Promise<void> {
  const health = await page.goto(`${origin}/healthz`);
  expect(health?.status()).toBe(200);
  await page.setContent(EMBEDDING_PAGE, { waitUntil: "load" });
}

test("sandbox refuses to bootstrap for an embedding origin outside the referrer allowlist", async ({
  page,
}) => {
  // Given: the sandbox server does not gate on Referer itself…
  const response = await page.request.get(SANDBOX_HTML, {
    headers: { referer: `${FOREIGN_ORIGIN}/` },
  });
  expect(response.status()).toBe(200);
  expect(response.headers()["content-security-policy"]).toContain("script-src");

  // …so the denial must come from the sandbox script's referrer check.
  const frameErrors: string[] = [];
  page.on("pageerror", (error) => frameErrors.push(error.message));

  // When: a page on an origin outside the allowlist embeds sandbox.html.
  await embedSandboxFrom(page, FOREIGN_ORIGIN);
  const sandboxFrame = page.frameLocator("iframe#sandbox");
  await expect(sandboxFrame.locator("body")).toBeAttached({ timeout: 30_000 });

  // Then: the sandbox throws the official referrer error…
  await expect
    .poll(() => frameErrors, { timeout: 30_000 })
    .toContainEqual(
      expect.stringContaining(
        `Embedding domain not allowed in referrer ${FOREIGN_ORIGIN}/`,
      ),
    );
  // …creates no inner view iframe…
  expect(await sandboxFrame.locator("iframe").count()).toBe(0);
  // …and never announces readiness to the embedding page.
  expect(
    await page.evaluate(() => window.__sandboxMessages ?? []),
  ).not.toContain(PROXY_READY);
});

test("sandbox bootstraps for the allowlisted host origin (positive control)", async ({
  page,
}) => {
  const frameErrors: string[] = [];
  page.on("pageerror", (error) => frameErrors.push(error.message));

  await embedSandboxFrom(page, HOST_ORIGIN);

  await expect
    .poll(() => page.evaluate(() => window.__sandboxMessages ?? []), {
      timeout: 30_000,
    })
    .toContain(PROXY_READY);
  await expect(page.frameLocator("iframe#sandbox").locator("iframe")).toHaveCount(1);
  expect(frameErrors).toEqual([]);
});

test("host refuses to render a renderer resource with the wrong MIME type", async ({
  page,
}) => {
  // Given: the server's resources/read answer is tampered on the wire so the
  // renderer arrives as plain `text/html` instead of the MCP App profile.
  let tamperedReads = 0;
  await page.route("**/mcp*", async (route) => {
    const postData = route.request().postData() ?? "";
    if (!postData.includes('"resources/read"')) {
      await route.continue();
      return;
    }
    const upstream = await route.fetch();
    const body = await upstream.text();
    expect(body, "fixture must still serve the MCP App MIME type").toContain(APP_MIME);
    tamperedReads += 1;
    await route.fulfill({
      response: upstream,
      body: body.replaceAll(APP_MIME, "text/html"),
    });
  });

  await page.goto(`${HOST_ORIGIN}/`, { waitUntil: "domcontentloaded" });
  await expect
    .poll(() => page.evaluate(() => window.__oubliaiHost?.state ?? "missing"), {
      timeout: 30_000,
    })
    .toBe("connected");

  // When: a workspace is selected.
  await page.locator("#workspace-select").selectOption("numbers");

  // Then: the host records the MIME rejection from the official check…
  await expect
    .poll(() => page.evaluate(() => window.__oubliaiHost ?? null), {
      timeout: 30_000,
    })
    .toMatchObject({
      state: "error",
      lastError: "Unsupported MIME type: text/html",
      bridgeInitialized: false,
    });
  expect(tamperedReads).toBeGreaterThan(0);
  // …shows it in the banner, and never loads the sandbox proxy.
  await expect(page.locator("#host-banner")).toHaveText(
    "Unsupported MIME type: text/html",
  );
  const frame = page.locator("iframe#app-frame");
  expect(await frame.count()).toBeLessThanOrEqual(1);
  if ((await frame.count()) === 1) {
    await expect(frame).not.toHaveAttribute("src", /sandbox\.html/);
  }
});
