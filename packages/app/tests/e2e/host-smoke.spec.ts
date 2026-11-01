import { expect, test } from "@playwright/test";

/**
 * Host smoke test for the official AppBridge two-origin sandbox.
 *
 * Given the vendored host served on :8080 and the sandbox proxy on :8081,
 * When the page connects to the fixture MCP server and a workspace is selected,
 * Then the official sandbox iframe mounts, the AppBridge handshake completes,
 * the sandbox response carries a `script-src` CSP header, and the page logs no
 * console errors.
 */

const HOST_ORIGIN = "http://localhost:8080";
const SANDBOX_SANDBOX_HTML = "http://localhost:8081/sandbox.html";

interface HostDebugState {
  state: "idle" | "connected" | "rendered" | "error";
  lastError?: string;
  bridgeInitialized: boolean;
}

declare global {
  interface Window {
    __oubliaiHost?: HostDebugState;
  }
}

test("official host renders a real $prefab workspace in the two-origin sandbox", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  // Given: the host page is served and the MCP connection is configured.
  await page.goto(`${HOST_ORIGIN}/`, { waitUntil: "domcontentloaded" });

  // Then: the host reaches the connected state from the real server handshake.
  await expect
    .poll(
      async () =>
        await page.evaluate(() => window.__oubliaiHost?.state ?? "missing"),
      { timeout: 30_000, message: "host never reached the connected state" },
    )
    .toBe("connected");

  // When: the `numbers` workspace is selected.
  const workspaceSelect = page.locator("#workspace-select");
  await expect(workspaceSelect).toBeVisible();
  await workspaceSelect.selectOption("numbers");

  // Then: the official sandbox proxy iframe is mounted on the sandbox origin.
  const sandboxFrame = page.locator("iframe#app-frame");
  await expect(sandboxFrame).toHaveAttribute(
    "src",
    new RegExp(`^${SANDBOX_SANDBOX_HTML.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`),
    { timeout: 30_000 },
  );

  // Then: the AppBridge initialization handshake completes with the view.
  await expect
    .poll(
      async () =>
        await page.evaluate(
          () => window.__oubliaiHost?.bridgeInitialized === true,
        ),
      { timeout: 30_000, message: "AppBridge never reported initialization" },
    )
    .toBe(true);

  // Then: the sandbox URL carries the CSP declared by the renderer resource's
  // `_meta`, so the real resource metadata reached `loadSandboxProxy` intact.
  const mountedSrc = await sandboxFrame.getAttribute("src");
  expect(mountedSrc, "sandbox src must carry the resource CSP").toContain("csp=");

  // Then: the inner view rendered the real workspace payload, not a blank
  // document. Asserting on a value from the fixture's own tool result is what
  // separates a genuine render from an initialized-but-empty iframe.
  const viewFrame = page.frameLocator("iframe#app-frame").frameLocator("iframe");
  await expect(viewFrame.locator("body")).toContainText("+15555550100", {
    timeout: 30_000,
  });

  // Then: all rendered pagination controls fit inside the embedded view rather
  // than being cut off by its fixed viewport.
  const paginationFits = await viewFrame
    .getByRole("button", { name: /previous|next/i })
    .evaluateAll((buttons) =>
      buttons.every((button) => {
        const rect = button.getBoundingClientRect();
        return rect.top >= 0 && rect.bottom <= window.innerHeight;
      }),
    );
  expect(paginationFits, "pagination controls must fit inside the embedded view")
    .toBe(true);
  const workspaceFits = await viewFrame.locator("html").evaluate((root) =>
    root.scrollHeight <= window.innerHeight,
  );
  expect(workspaceFits, "workspace must not overflow the embedded view vertically")
    .toBe(true);

  // Then: the host-owned media panel is visibly integrated alongside the
  // mounted workspace rather than appearing as an unstyled control run.
  await expect(page.locator("#media-panel")).toHaveCSS("display", "grid");

  await page.screenshot({
    path: "test-results/host-smoke-numbers.png",
    fullPage: true,
  });

  // Then: the sandbox origin enforces a script-src CSP via HTTP header.
  const sandboxResponse = await page.request.get(SANDBOX_SANDBOX_HTML);
  expect(sandboxResponse.status()).toBe(200);
  const cspHeader = sandboxResponse.headers()["content-security-policy"];
  expect(cspHeader, "sandbox.html must send a Content-Security-Policy header")
    .toBeTruthy();
  expect(cspHeader).toContain("script-src");

  // Then: no console errors were produced anywhere in the flow.
  const hostDebug = await page.evaluate(() => window.__oubliaiHost ?? null);
  expect(hostDebug?.lastError ?? null).toBeNull();
  expect(consoleErrors).toEqual([]);
});
