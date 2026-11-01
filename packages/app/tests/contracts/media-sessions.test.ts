import { expect, test, vi } from "vitest";

import { createVideoSession } from "../../src/media/video.js";
import { createVoiceSession } from "../../src/media/voice.js";

test("voice session creates one token-authenticated client and delegates lifecycle", async () => {
  const connect = vi.fn(async () => undefined);
  const disconnect = vi.fn(async () => undefined);
  const createClient = vi.fn(() => ({ connect, disconnect }));

  const session = createVoiceSession("voice-login-token", { createClient });

  expect(createClient).toHaveBeenCalledOnce();
  expect(createClient).toHaveBeenCalledWith({ login_token: "voice-login-token" });
  expect(connect).not.toHaveBeenCalled();

  await session.connect();
  await session.disconnect();

  expect(connect).toHaveBeenCalledOnce();
  expect(disconnect).toHaveBeenCalledOnce();
});

test("video session initializes one room on connect and delegates lifecycle", async () => {
  const connect = vi.fn(async () => undefined);
  const disconnect = vi.fn(async () => undefined);
  const initialize = vi.fn(async () => ({ connect, disconnect }));
  const session = createVideoSession("room-client-token", { initialize });

  expect(initialize).not.toHaveBeenCalled();
  await session.connect("room-fixture-001");

  expect(initialize).toHaveBeenCalledOnce();
  expect(initialize).toHaveBeenCalledWith({
    roomId: "room-fixture-001",
    clientToken: "room-client-token",
  });
  expect(connect).toHaveBeenCalledOnce();

  await session.disconnect();
  expect(disconnect).toHaveBeenCalledOnce();
});

test("video session does not initialize a second room", async () => {
  const room = {
    connect: vi.fn(async () => undefined),
    disconnect: vi.fn(async () => undefined),
  };
  const initialize = vi.fn(async () => room);
  const session = createVideoSession("room-client-token", { initialize });

  await session.connect("room-fixture-001");
  await session.connect("room-fixture-001");

  expect(initialize).toHaveBeenCalledOnce();
  expect(room.connect).toHaveBeenCalledTimes(2);
});
