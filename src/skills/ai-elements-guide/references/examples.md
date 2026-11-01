# AI Elements Examples and Composition Patterns

## Official example pages
- https://ai-sdk.dev/elements/examples/chatbot
- https://ai-sdk.dev/elements/examples/v0
- https://ai-sdk.dev/elements/examples/workflow

## Composition sketches
These are conceptual compositions. Verify import paths and props from the component docs.

### Chat UI
- conversation + message + prompt-input
- attachments + sources + inline-citation
- suggestion + model-selector + shimmer or loader

### Research or analysis UI
- message + sources + inline-citation
- context + checkpoint + queue

### Reasoning UI
- reasoning + plan + task
- chain-of-thought only if intended for end users

### Agent workbench
- agent + artifact
- code-block + terminal + test-results
- file-tree + package-info + environment-variables + web-preview

### Flow UI
- canvas + node + edge
- controls + panel + toolbar

### Audio UI
- speech-input + transcription
- audio-player + voice-selector + mic-selector + persona

## Usage guidance
- Always include a short API props summary for each component used.
- Keep examples minimal and focused on the user request.
