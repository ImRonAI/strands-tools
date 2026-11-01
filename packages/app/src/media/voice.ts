import { TelnyxRTC } from "@telnyx/webrtc";
import type { IClientOptions } from "@telnyx/webrtc";

interface VoiceClient {
  connect(): Promise<void>;
  disconnect(): Promise<void>;
}

export interface VoiceSession {
  connect(): Promise<void>;
  disconnect(): Promise<void>;
}

export interface VoiceSessionDependencies {
  readonly createClient?: (options: IClientOptions) => VoiceClient;
}

export function createVoiceSession(
  loginToken: string,
  dependencies: VoiceSessionDependencies = {},
): VoiceSession {
  const createClient =
    dependencies.createClient ??
    ((options: IClientOptions): VoiceClient => new TelnyxRTC(options));
  const client = createClient({ login_token: loginToken });

  return {
    connect: () => client.connect(),
    disconnect: () => client.disconnect(),
  };
}
