import type { VoiceSession } from "./voice.js";

type MediaPanelState =
  | "idle"
  | "requesting"
  | "denied"
  | "mic-ready"
  | "error";

interface MediaDebugState {
  readonly state: MediaPanelState;
  readonly connectCalls: number;
  readonly disconnectCalls: number;
  readonly lastError?: string;
}

declare global {
  interface Window {
    __oubliaiMedia: MediaDebugState;
  }
}

export interface MediaPanelDependencies {
  readonly mintVoiceToken: (credentialId: string) => Promise<string>;
  readonly createVoiceSession: (loginToken: string) => VoiceSession;
  readonly getUserMedia?: (
    constraints: MediaStreamConstraints,
  ) => Promise<MediaStream>;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function mountMediaPanel(
  container: HTMLElement,
  dependencies: MediaPanelDependencies,
): void {
  const getUserMedia =
    dependencies.getUserMedia ??
    ((constraints: MediaStreamConstraints) =>
      navigator.mediaDevices.getUserMedia(constraints));
  let connectCalls = 0;
  let disconnectCalls = 0;
  let session: VoiceSession | undefined;
  let connected = false;

  const disconnectSession = async (): Promise<void> => {
    const activeSession = session;
    session = undefined;
    if (!activeSession) return;

    disconnectCalls += 1;
    window.__oubliaiMedia = {
      ...window.__oubliaiMedia,
      disconnectCalls,
    };
    await activeSession.disconnect();
  };

  const panel = document.createElement("section");
  panel.id = "media-panel";
  panel.setAttribute("aria-labelledby", "media-panel-title");

  const title = document.createElement("h2");
  title.id = "media-panel-title";
  title.textContent = "Voice media";

  const label = document.createElement("label");
  label.htmlFor = "voice-credential-id";
  label.textContent = "Telephony credential ID";

  const input = document.createElement("input");
  input.id = "voice-credential-id";
  input.type = "text";
  input.autocomplete = "off";

  const button = document.createElement("button");
  button.id = "enable-microphone";
  button.type = "button";
  button.textContent = "Enable microphone";

  const status = document.createElement("output");
  status.setAttribute("aria-live", "polite");

  const update = (
    state: MediaPanelState,
    message: string,
    lastError?: string,
  ): void => {
    status.dataset.mediaState = state;
    status.textContent = message;
    window.__oubliaiMedia = lastError
      ? { state, connectCalls, disconnectCalls, lastError }
      : { state, connectCalls, disconnectCalls };
  };

  update("idle", "Microphone access has not been requested.");
  button.addEventListener("click", () => {
    const credentialId = input.value.trim();
    if (!credentialId) {
      update("error", "Enter a telephony credential ID.", "Missing credential ID");
      return;
    }

    button.disabled = true;
    update("requesting", "Requesting microphone access…");
    void (async () => {
      try {
        const stream = await getUserMedia({ audio: true });
        for (const track of stream.getTracks()) track.stop();

        const token = await dependencies.mintVoiceToken(credentialId);
        session = dependencies.createVoiceSession(token);
        connectCalls += 1;
        await session.connect();
        connected = true;
        update("mic-ready", "Microphone ready.");
      } catch (error: unknown) {
        await disconnectSession();
        const message = errorMessage(error);
        if (error instanceof DOMException && error.name === "NotAllowedError") {
          update("denied", "Microphone permission denied.", message);
          return;
        }
        update("error", "Unable to start voice media.", message);
      } finally {
        button.disabled = connected;
      }
    })();
  });

  window.addEventListener(
    "pagehide",
    () => {
      void disconnectSession();
    },
    { once: true },
  );

  panel.append(title, label, input, button, status);
  container.appendChild(panel);
}
