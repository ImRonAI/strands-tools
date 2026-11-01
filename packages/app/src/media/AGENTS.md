# Media Guidelines

Work here; inherit root/app/host instructions. Use official Telnyx `@telnyx/webrtc` and `@telnyx/video` public APIs, short-lived browser credentials and documented state events. Sources: `docs/reference/telnyx/sdk/voice.md`, `video.md`, `network.md`; source schema for credential/token operations.

The official Video example imports `Room` and `createLocalParticipant`, uses `clientToken`, listens to `state_changed`, then calls `connect`, `publish`, `subscribe`. Read actual selected SDK types; do not guess additional props/methods. Signaling/ICE/transcoding are SDK responsibilities, not application inventions.

FastMCP ResourcePermissions requests microphone/camera; a host MAY honor those requests. Browser user permission, autoplay, network and actual call-leg topology remain required tests. No promise of universal inline media across MCP hosts. Generated UI controls a stable SDK media surface; do not rebuild a PeerConnection every model turn.

Meeting Bot belongs only to its supported external platforms; do not attach it to Telnyx Rooms. Verify monitor/whisper/barge relationships from Telnyx contracts and controlled call evidence, not just enum names. REST acceptance or a recording player's presence is not proof of a live connected media path. Dispose owned tracks/connections on documented lifecycle events.

## Assigned directory
Project target: `packages/app/src/media`. Change into this directory before development. This copy is a planning template; the project scaffold is not installed until the worker applies it.
