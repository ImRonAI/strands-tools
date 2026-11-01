import { expect, test } from "@playwright/test";

interface MediaDebugState {
  state: string;
  connectCalls: number;
  disconnectCalls?: number;
  lastError?: string;
}

async function mediaState(page: import("@playwright/test").Page): Promise<MediaDebugState> {
  return page.evaluate(() => {
    const state = window.__oubliaiMedia;
    if (!state) throw new Error("Missing media debug state");
    return state;
  });
}

async function mediaPanelLayout(
  page: import("@playwright/test").Page,
): Promise<{ display: string; gap: number; borderRadius: number }> {
  return page.locator("#media-panel").evaluate((panel) => {
    const styles = getComputedStyle(panel);
    return {
      display: styles.display,
      gap: Number.parseFloat(styles.gap),
      borderRadius: Number.parseFloat(styles.borderRadius),
    };
  });
}

test("microphone denial does not mint or connect", async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      throw new DOMException("Permission denied", "NotAllowedError");
    };
  });
  await page.goto("/");

  await page.locator("#voice-credential-id").fill("credential-fixture-001");
  await page.locator("#enable-microphone").click();

  await expect(page.locator('[data-media-state="denied"]')).toBeVisible();
  expect(await mediaPanelLayout(page)).toMatchObject({
    display: "grid",
    gap: 12,
    borderRadius: 12,
  });
  await expect.poll(async () => mediaState(page)).toMatchObject({
    state: "denied",
    connectCalls: 0,
  });
  await page.screenshot({
    path: "test-results/media-permission-denied.png",
    fullPage: true,
  });
});

test("microphone grant mints and starts one voice session", async ({
  context,
  page,
}) => {
  await context.grantPermissions(["microphone"], {
    origin: "http://localhost:8080",
  });
  await page.goto("/");

  await page.locator("#voice-credential-id").fill("credential-fixture-001");
  await page.locator("#enable-microphone").click();

  await expect.poll(async () => mediaState(page)).toMatchObject({
    state: "mic-ready",
    connectCalls: 1,
  });
  await expect(page.locator('[data-media-state="mic-ready"]')).toBeVisible();
  await expect(page.locator("#enable-microphone")).toBeDisabled();
  await expect(page.locator("#enable-microphone")).toHaveCSS(
    "color",
    "rgb(75, 85, 99)",
  );
  expect(await mediaState(page)).not.toHaveProperty("token");
  await page.screenshot({
    path: "test-results/media-permission-granted.png",
    fullPage: true,
  });
});

test("pagehide disconnects the connected voice session exactly once", async ({
  context,
  page,
}) => {
  await context.grantPermissions(["microphone"], {
    origin: "http://localhost:8080",
  });
  await page.goto("/");

  await page.locator("#voice-credential-id").fill("credential-fixture-001");
  await page.locator("#enable-microphone").click();
  await expect.poll(async () => mediaState(page)).toMatchObject({
    state: "mic-ready",
    connectCalls: 1,
    disconnectCalls: 0,
  });

  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pagehide")));

  await expect.poll(async () => mediaState(page)).toMatchObject({
    state: "mic-ready",
    connectCalls: 1,
    disconnectCalls: 1,
  });
});
