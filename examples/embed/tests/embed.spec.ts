import { expect, test, type Page } from "@playwright/test";

/**
 * Embed example e2e.
 *
 * Given the customer page served on :8090 (its own origin), the official
 * sandbox proxy served by `packages/app` on :8081, and the real Oubliai
 * fixture server behind the CORS shim,
 * When the page connects with the user's own URL + bearer token and opens the
 * `numbers` workspace,
 * Then the official sandbox iframe mounts, the AppBridge handshake completes,
 * the inner view shows the fixture's own number, the sandbox response carries a
 * CSP header, no console errors occur, and closing / page hide run the
 * documented bridge teardown.
 */

const EMBED_ORIGIN = "http://localhost:8090";
const SANDBOX_HTML = "http://localhost:8081/sandbox.html";
const FIXTURE_TOKEN = "e2e-token";

import type { EmbedDebugState } from "../src/embed.js";

function mcpUrlFromHarness(): string {
  const url = process.env.OUBLIAI_EMBED_MCP_URL;
  if (!url) {
    throw new Error("global-setup did not export OUBLIAI_EMBED_MCP_URL");
  }
  return url;
}

async function embedState(page: Page): Promise<EmbedDebugState | null> {
  return page.evaluate(
    () =>
      (window as Window & { __oubliaiEmbed?: EmbedDebugState }).__oubliaiEmbed ??
      null,
  );
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test.describe.configure({ mode: "serial" });

test("customer page embeds the numbers workspace in the official sandbox", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.stack ?? error.message}`));

  // Given: the customer page loads on its own origin.
  await page.goto(`${EMBED_ORIGIN}/`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("h1")).toContainText("Acme");

  // Given: the connection form is prefilled from the page's own backend
  // (`/api/connection`, development only) with the fixture connection.
  const urlInput = page.locator("#mcp-url");
  const tokenInput = page.locator("#mcp-token");
  await expect(urlInput).toHaveValue(mcpUrlFromHarness());
  await expect(tokenInput).toHaveValue(FIXTURE_TOKEN);

  // When: the user connects with that URL + bearer token.
  await page.locator("#connect").click();
  await expect
    .poll(async () => (await embedState(page))?.state ?? "missing", {
      timeout: 30_000,
      message: "embed never reached the connected state",
    })
    .toBe("connected");

  // When: the `numbers` workspace is opened.
  const workspaceSelect = page.locator("#workspace-select");
  await expect(workspaceSelect).toBeEnabled();
  await expect(workspaceSelect.locator("option")).toHaveCount(14);
  await workspaceSelect.selectOption("numbers");
  await page.locator("#open-workspace").click();

  // Then: the official sandbox proxy iframe is mounted on the sandbox origin
  // and its URL carries the CSP declared by the renderer resource `_meta`.
  const sandboxFrame = page.locator("iframe#app-frame");
  await expect(sandboxFrame).toHaveAttribute(
    "src",
    new RegExp(`^${escapeRegExp(SANDBOX_HTML)}\\?csp=`),
    { timeout: 30_000 },
  );
  await expect(sandboxFrame).toHaveAttribute(
    "sandbox",
    "allow-scripts allow-same-origin allow-forms",
  );

  // Then: the AppBridge initialization handshake completes with the view.
  await expect
    .poll(async () => (await embedState(page))?.bridgeInitialized === true, {
      timeout: 30_000,
      message: "AppBridge never reported initialization",
    })
    .toBe(true);
  expect((await embedState(page))?.state).toBe("rendered");

  // Then: the inner view rendered the real `$prefab` workspace payload — a
  // value from the fixture's own Telnyx response, not a blank document.
  const viewFrame = page.frameLocator("iframe#app-frame").frameLocator("iframe");
  const fixtureNumber = viewFrame.getByText("+15555550100");
  await expect(fixtureNumber).toBeVisible({ timeout: 30_000 });

  // When: the integrator toggles its theme, the documented host-context
  // notification reaches the view without errors and the data stays visible.
  await page.locator("#theme-toggle").click();
  await expect
    .poll(async () => (await embedState(page))?.theme)
    .toBe("dark");
  await expect(fixtureNumber).toBeVisible();

  await page.screenshot({
    path: "test-results/embed-numbers.png",
    fullPage: true,
  });
  await sandboxFrame.screenshot({ path: "test-results/embed-numbers-view.png" });

  // Then: the sandbox origin enforces a script-src CSP via HTTP header.
  const sandboxResponse = await page.request.get(SANDBOX_HTML);
  expect(sandboxResponse.status()).toBe(200);
  const cspHeader = sandboxResponse.headers()["content-security-policy"];
  expect(cspHeader, "sandbox.html must send a Content-Security-Policy header")
    .toBeTruthy();
  expect(cspHeader).toContain("script-src");

  // When: the customer closes the workspace.
  await page.locator("#close-workspace").click();

  // Then: the documented teardown ran (`teardownResource` then `close`) and
  // the sandbox iframe is gone.
  await expect
    .poll(async () => (await embedState(page))?.bridgeClosed === true, {
      timeout: 15_000,
      message: "bridge was not closed on unmount",
    })
    .toBe(true);
  const afterClose = await embedState(page);
  expect(afterClose?.teardownRequested).toBe(true);
  expect(["acknowledged", "declined"]).toContain(afterClose?.teardownOutcome);
  await expect(sandboxFrame).toHaveCount(0);
  expect(afterClose?.state).toBe("connected");

  // When: the workspace is opened again and the page is hidden (navigation /
  // tab close), the bridge is closed through the same lifecycle.
  await page.locator("#open-workspace").click();
  await expect
    .poll(async () => (await embedState(page))?.bridgeInitialized === true, {
      timeout: 30_000,
    })
    .toBe(true);
  expect((await embedState(page))?.bridgeClosed).toBe(false);
  await page.evaluate(() => {
    window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: false }));
  });
  await expect
    .poll(async () => (await embedState(page))?.bridgeClosed === true, {
      timeout: 15_000,
      message: "bridge was not closed on pagehide",
    })
    .toBe(true);

  // Then: no console errors were produced anywhere in the flow.
  expect((await embedState(page))?.lastError ?? null).toBeNull();
  expect(consoleErrors).toEqual([]);
});

test("a rejected bearer token never mounts a view", async ({ page }) => {
  await page.goto(`${EMBED_ORIGIN}/`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#mcp-url")).toHaveValue(mcpUrlFromHarness());

  // When: the user connects with a token the server does not accept.
  await page.locator("#mcp-token").fill("not-the-fixture-token");
  await page.locator("#connect").click();

  // Then: the page reports the failure and nothing is mounted.
  await expect
    .poll(async () => (await embedState(page))?.state ?? "missing", {
      timeout: 30_000,
    })
    .toBe("error");
  const state = await embedState(page);
  expect(state?.lastError).toBeTruthy();
  await expect(page.locator("#embed-banner")).toBeVisible();
  await expect(page.locator("#open-workspace")).toBeDisabled();
  await expect(page.locator("iframe#app-frame")).toHaveCount(0);
});

test("the sandbox origin refuses to serve anything but sandbox.html", async ({
  request,
}) => {
  // Then: the embed page itself is not reachable from the sandbox origin, so
  // the two origins stay distinct.
  const response = await request.get("http://localhost:8081/index.html");
  expect(response.status()).toBe(404);
});
