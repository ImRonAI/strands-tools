interface VideoRoom {
  connect(): Promise<void>;
  disconnect(): Promise<void>;
}

interface VideoInitializeOptions {
  readonly roomId: string;
  readonly clientToken: string;
}

type InitializeVideo = (options: VideoInitializeOptions) => Promise<VideoRoom>;

export interface VideoSession {
  connect(roomId: string): Promise<void>;
  disconnect(): Promise<void>;
}

export interface VideoSessionDependencies {
  readonly initialize?: InitializeVideo;
}

async function initializeVideo(
  options: VideoInitializeOptions,
): Promise<VideoRoom> {
  const { initialize } = await import("@telnyx/video");
  return initialize(options);
}

export function createVideoSession(
  clientToken: string,
  dependencies: VideoSessionDependencies = {},
): VideoSession {
  const initialize = dependencies.initialize ?? initializeVideo;
  let roomPromise: Promise<VideoRoom> | undefined;

  return {
    async connect(roomId: string): Promise<void> {
      roomPromise ??= initialize({ roomId, clientToken });
      const room = await roomPromise;
      await room.connect();
    },
    async disconnect(): Promise<void> {
      if (!roomPromise) return;
      const room = await roomPromise;
      await room.disconnect();
    },
  };
}
