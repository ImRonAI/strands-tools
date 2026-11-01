---
name: ai-elements-guide
description: Implement, compose, and audit Vercel AI SDK AI Elements in React/Next.js (App Router or Pages) and ShadCN/Tailwind projects. Use when asked to build AI Elements chat UIs, integrate AI Elements components, review chain-of-thought/reasoning/plan output, or provide AI Elements API props and reference links.
---

# AI Elements Guide

## Overview
Guide for integrating AI Elements into React/Next.js projects, composing chat and agent UIs, and auditing reasoning or plan presentation. Always target the latest AI Elements release and confirm API props from the official docs or the snapshot.

## Workflow Decision Tree
- New integration or missing AI Elements -> follow "Implement AI Elements in a project"
- Build or redesign chat UI -> follow "Compose a chat UI"
- Review chain-of-thought or reasoning -> follow "Review chain-of-thought or reasoning usage"
- Only need props or links -> use references and the props snapshot, then verify against docs

## Workflow: Implement AI Elements in a project
1. Identify stack: Next.js App Router vs Pages, React version, Tailwind or ShadCN usage.
2. Confirm AI SDK and AI Elements versions: check docs in `references/ai-elements-docs.md`.
3. Install dependencies using the official usage page and record versions in notes.
4. Decide data flow: hook or transport used for streaming and message state.
5. Add AI Elements components progressively and verify CSS and layout.
6. Validate with a minimal example and expand to the full UI.

## Workflow: Compose a chat UI
1. Pick core components: conversation container, message list, prompt input, attachments.
2. Add optional UX: sources, inline citations, suggestions, model selector, shimmer or loader.
3. Add reasoning views only if required and allowed by product needs.
4. Use example compositions in `references/examples.md` and docs.
5. For each component used, include API props in output (pull from doc page).

## Workflow: Review chain-of-thought or reasoning usage
1. Find where chain-of-thought or reasoning components render in the UI.
2. Confirm the content shown is intended for end users.
3. Ensure fallback behavior when reasoning is unavailable or disabled.
4. Verify consistency across streaming and non-streaming paths.
5. Document findings and recommended changes.

## Workflow: Troubleshoot
1. Check `/elements/troubleshooting` for known issues.
2. Validate CSS and layout isolation (Tailwind or ShadCN).
3. Verify client and server boundaries in Next.js.
4. Confirm AI SDK streaming and message state are wired correctly.

## Workflow: Refresh API props snapshot
1. Run `python3 scripts/update_api_props.py` (requires network access).
2. Review `references/api-props.md` for failures and re-run if needed.
3. If props differ from docs, note the delta in your response.

## References
- `references/ai-elements-docs.md` for the canonical link index (update if new docs appear).
- `references/component-index.md` for component map and doc links.
- `references/examples.md` for example compositions and links.
- `references/api-props.md` for the props snapshot (regenerate if docs change).
 - `scripts/update_api_props.py` to refresh the snapshot.

## Output Requirements
When responding to a user request:
- Provide component list and doc links used.
- Include key API props for each component from the docs.
- Provide a short implementation workflow and a concise example.
- Call out any version assumptions and gaps.
- If props differ from the snapshot, note the delta and update `references/api-props.md`.
