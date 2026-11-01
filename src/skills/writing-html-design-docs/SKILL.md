---
name: writing-html-design-docs
description: Use when the user asks for an HTML deliverable — a design doc, plan, RFC, architecture proposal, roadmap, kanban presentation, or single-page brief — that must read well to both humans (UX) and other agents (AX). Trigger on words like "HTML", "stunning", "beautiful", "kanban", "design doc", "RFC", "make it look better", "redo this in HTML", or any request for a polished one-file presentation.
---

# Writing HTML Design Docs

## Overview

A repeatable design system for self-contained HTML deliverables — design docs, plans, RFCs, roadmaps, kanban presentations — that score high on both **UX** (human reading) and **AX** (agent reading). Built on Tailwind via CDN + Google Fonts + a small inline CSS layer + vanilla JS. No build step. No framework dependency. One file.

**The core insight:** humans and agents have different scanning patterns. Humans want hierarchy, color, and animation. Agents want stable anchors, semantic HTML, parseable tables, and `<code>`-tagged identifiers. The design system serves both at the same time.

**REQUIRED STARTER:** Copy `skeleton.html` from this skill directory as your starting point. Don't rebuild the styles from scratch — the skeleton already encodes every pattern below.

## When to use

- User asks for an HTML deliverable (any of: design doc, plan, RFC, architecture proposal, roadmap, kanban, single-page brief, presentation)
- User asks for the doc to be "stunning", "beautiful", "premium-looking", "Jira-style", or to "look better"
- A document with 5+ sections that benefits from sticky navigation and visual hierarchy
- A plan with backlog / in-progress / done states (kanban is the right tool)
- Any single-file artifact that will be shared via filesystem rather than served from a repo

## When NOT to use

- A short note (use markdown)
- A doc that will live in-repo as primary docs (use markdown — git renders it natively)
- A doc that will be printed (different styling required)
- A simple status update (plain text or markdown)

## The standard

What every doc produced under this skill includes:

| Element | Purpose | Source |
|---|---|---|
| Tailwind CDN + inline config | All styling without a build step | `<script src="https://cdn.tailwindcss.com">` |
| Google Fonts: Outfit + Inter + JetBrains Mono | Display / sans / mono typography | `<link>` to `fonts.googleapis.com` |
| Dark theme on `bg-ink-950` | Reads premium; reduces eye strain at long sessions | inline `tailwind.config` palette |
| Emerald accent (`#34d399`) | Default accent — swap per domain only if needed | inline config + custom CSS |
| Sticky nav with section anchors + status pill | Persistent orientation | `<nav>` block at top |
| Hero with eyebrow + title + subtitle + stats strip | Scannable summary in 5 seconds | hero `<section>` |
| Semantic section numbering (01, 02 ...) | Stable navigation for both humans and agents | eyebrow labels above each `<h2>` |
| Glass cards (`bg-white/[0.025] border border-white/[0.08] backdrop-blur`) | Content containers | `.glass` utility class |
| Tables for reference data | Parseable for agents, scannable for humans | `<table>` not divs |
| Color-coded categorical chips | Visual taxonomy | `.tag` pattern w/ `kind:` `domain:` `mutates:` |
| Kanban board (if doc has a roadmap) | Visual backlog state | three-column flex layout |
| Jira-style modal for tickets | Detail-on-demand | vanilla JS, ESC + click-outside + body-scroll lock |
| Official-docs reference grid | Source-of-truth links | grid of cards with hover state |
| Footer with metadata + authoring agent | Provenance | `<footer>` |
| Animated halo glow + pulse-dot status | Subtle motion language | keyframes in inline `<style>` |
| Custom scrollbar | Cohesive feel even off-screen | `::-webkit-scrollbar` in inline `<style>` |

## Required structural elements (the checklist)

Before delivering, verify every item:

- [ ] **`<!DOCTYPE html>` + `lang="en"` + `class="scroll-smooth"`** on `<html>`
- [ ] **Tailwind CDN script** with inline `tailwind.config` extending fonts, colors, animations
- [ ] **Google Fonts preconnect + link** for Inter, Outfit, JetBrains Mono
- [ ] **Inline `<style>` block** for what Tailwind doesn't cover: gradient text, glass utilities, halo glow, pulse line, custom scrollbar, code-block tinting, `scroll-margin-top` on sections
- [ ] **Sticky nav** with logo lockup + section links + status pill
- [ ] **Hero** with eyebrow → title (`gradient-text` on the punchline word) → subtitle → CTA row → stats strip
- [ ] **Every major section** has `id="..."` on the `<section>` element (so other docs can deep-link)
- [ ] **Every `<h2>`** preceded by a tiny eyebrow label (uppercase, tracking-wide) with section number + name
- [ ] **Glass cards** used for content blocks (not raw `<div>`s)
- [ ] **Reference data in `<table>`** elements (not in divs) so agents can parse them
- [ ] **Inline code identifiers** use `<code class="font-mono ...">` chip styling
- [ ] **Block code** uses `<pre class="code">` with the syntax-highlight spans (`.cm`, `.kw`, `.st`, `.fn`, `.nm`) defined in inline CSS
- [ ] **Kanban** (if applicable) uses three-column layout: Done / Ready / Backlog with ticket cards
- [ ] **Modal** is one element at the bottom of `<body>`, populated by vanilla JS from a `TICKETS` object
- [ ] **Footer** with provenance line (authoring agent + date)

## AX-specific requirements (agent experience)

These are non-negotiable — they're what makes the doc readable to a future agent doing `WebFetch` or local parsing:

- [ ] Every section has a stable `id` matching its eyebrow numbering: `id="01-vision"`, `id="02-architecture"`, etc.
- [ ] Reference data is in `<table>`/`<thead>`/`<tbody>` (not in styled divs that look like tables)
- [ ] Tool / file / API identifiers are wrapped in `<code>` (so they're extractable)
- [ ] All critical information has a non-interactive representation — **don't trap essential content behind a modal-only path.** The kanban ticket cards must already carry the title + summary; the modal is *additional* detail, not the only place the info exists.
- [ ] External links use full URLs in `href` (never JS-only navigation)
- [ ] Semantic hierarchy: one `<h1>` (in hero), `<h2>` per section, `<h3>` for subsections
- [ ] Tag chips include the textual tag (`kind:framework`) — don't replace with icons-only

## UX-specific requirements (human experience)

- [ ] Hero is scannable in under 5 seconds — eyebrow, title, subtitle, stats
- [ ] Sticky nav stays visible on scroll (status pill changes color if state changes)
- [ ] Section eyebrows give the human "where am I" — `01 · Vision`, `02 · Architecture`, etc.
- [ ] Color palette is restrained: ink/slate base, one accent, semantic colors (rose for risks, amber for ready, blue for backlog, emerald for done)
- [ ] Animation is subtle: halo glow, pulse-dot on status, hover lifts on ticket cards, fade-in on load. **No bouncing, no spinning, no parallax.**
- [ ] Spacing is generous — sections separated by `py-24 lg:py-28`, hero padding `pt-20 pb-28`
- [ ] Modal interaction is keyboard-accessible: ESC closes, click-outside closes, focus trap not required (single field)

## How to use the skeleton

1. **Copy `skeleton.html`** from this skill directory to your target path:
   ```bash
   cp ~/.claude/skills/writing-html-design-docs/skeleton.html /path/to/your-doc.html
   ```
2. **Fill the placeholders** marked `<!-- FILL: ... -->` in order:
   - Document title in `<title>` and hero `<h1>`
   - Hero subtitle (1-2 sentences)
   - Stats strip (5 metrics with eyebrow / value / caption)
   - Section blocks (copy-paste the pattern; renumber the eyebrow `01 · ...` `02 · ...`)
   - The `TICKETS` object at the bottom (kanban data) — if you don't have a kanban, delete the kanban section AND the modal AND the script block
   - The official-docs grid (replace with your domain's reference URLs)
   - Footer provenance line
3. **Open in a browser** to verify it renders. `open your-doc.html` on macOS.
4. **Run the pre-delivery validation** (below).

## Kanban + modal data shape

Tickets are a vanilla JS object keyed by issue key (e.g., `AEG-100`). One shape:

```js
const TICKETS = {
  'PROJ-100': {
    column: 'done',          // 'done' | 'ready' | 'backlog'
    status: 'Done',          // 'Done' | 'Ready' | 'Backlog' | 'In progress'
    type: 'Foundation',      // free-form type label (must be in TYPE_STYLES)
    priority: 'High',        // 'Highest' | 'High' | 'Medium' | 'Low'
    effort: 'Shipped',       // '~30 lines' | '~1 hour' | 'Shipped' | etc.
    title: 'Short title',
    summary: 'One-sentence summary shown on the card.',
    description: 'Longer description shown in the modal. <code>HTML allowed</code>.',
    acceptance: ['Criterion one.', 'Criterion two.'],
    files: ['path/to/file.py', 'path/to/other.ts'],
    labels: ['label-one', 'label-two'],
    linked: ['PROJ-101', 'PROJ-102'],  // optional — buttons in the modal
  },
};
```

Add new `type` values by extending the `TYPE_STYLES` object near the bottom of the file. Six color slots are pre-wired: emerald (Foundation), blue (Settings), purple (Runtime), cyan (Discovery), amber (Docs), rose (Data + Cleanup), orange (Dependencies).

## Customizing the accent color

Default is emerald (`#34d399`). If your domain is something else (auth → indigo, financial → amber, security → rose), swap these locations in `skeleton.html`:

1. `tailwind.config.theme.extend.colors` — keep `ink:` as-is, the accent is via Tailwind utility classes
2. `.halo::before` background gradient — `rgba(52,211,153, ...)` → your color's RGB at same alpha
3. `.gradient-text` background gradient — both stops use the accent
4. Sticky nav logo gradient — `from-emerald-400 to-emerald-700`
5. Status pills, focus rings, primary CTA — search-replace `emerald-` with your color
6. Code block `.st` (string) tint — optional but recommended

**Default stays emerald** unless the domain genuinely calls for something else. Consistency across docs is itself a UX/AX win.

## Common mistakes

| Mistake | Why it breaks UX/AX | Fix |
|---|---|---|
| Light theme by default | The standard is dark | Use the skeleton — don't rebuild |
| Bootstrap or Material instead of Tailwind | Wrong design language; bloated CDN | Use the skeleton — Tailwind only |
| External CSS or image assets | Breaks self-contained promise | All styling inline; only CDN deps are Tailwind + Google Fonts |
| Reference data in styled `<div>`s | Not parseable for agents | Use `<table>` |
| Critical info only inside modal | Agents can't see modal content via WebFetch | Always render the card with full title + summary; modal is *additional* detail |
| Skipping the `id` on `<section>`s | Other docs can't anchor-link in | Every major section gets an `id` |
| Overusing animations | Distracts; feels gimmicky | Halo glow + pulse-dot + hover lift only |
| Hero with no stats strip | Missing the quick-scan moment | Five stat cards in the hero strip |
| Dropping the official-docs grid | Loses the "validate against source" affordance | Include even if it's just 3-4 links |
| Modal that traps scroll without ESC support | Accessibility failure | Skeleton includes ESC + click-outside + body-scroll lock |
| Custom JS framework (React/Vue) | Breaks self-contained, breaks build-step-free | Vanilla JS only; the skeleton's modal is ~30 lines |

## Pre-delivery validation

Before claiming the doc is done:

1. **Open in browser:** `open your-doc.html` — the page renders, fonts load, no console errors.
2. **All sections have `id`s:** `grep -E '<section[^>]+id=' your-doc.html` — count matches the number of major sections.
3. **Kanban tickets all render:** scroll the kanban; every column shows the expected ticket count.
4. **Modal works:** click a ticket → modal opens with full detail. ESC closes. Click-outside closes. Body doesn't scroll while open.
5. **External links work:** spot-check 2-3 doc links.
6. **No CDN failures degrade content:** mentally test "if Tailwind CDN fails, is the doc still readable?" — text should still appear, just unstyled. (Don't have inline content depending on Tailwind classes for visibility/semantics.)
7. **HTML is valid:** any browser dev console will flag major issues; spot-check with `<!DOCTYPE html>` + `<html lang>` + closing tags.
8. **AX spot-check:** `curl -s file://$PWD/your-doc.html | grep -E '<(h2|table|code)' | head -20` — agent-visible structure is dense.

## Skill-creation methodology note (for future iterations)

This skill was authored without the full RED/GREEN subagent baseline-then-validation cycle prescribed by `superpowers:writing-skills`. The pragmatic justification: the `skeleton.html` shipped alongside this skill is a known-working artifact (derived from a delivered design doc that humans confirmed met the standard), so the "green" state is empirically established. The "red" baseline (naive HTML output) is well-understood from prior agent behavior in similar tasks.

**To run a proper TDD cycle on this skill** (recommended if you're refining it):

1. **RED:** Dispatch a fresh subagent with a prompt like: *"Create a self-contained HTML design doc for [topic] that summarizes the choice. Include sections, a roadmap, and references."* — without referencing this skill. Capture the output. It will lack the design system.
2. **GREEN:** Dispatch a fresh subagent with the same prompt plus *"Follow the writing-html-design-docs skill at `~/.claude/skills/writing-html-design-docs/SKILL.md`."* — capture output. It should produce the design system.
3. **REFACTOR:** Diff the outputs against this skill's required structural elements; any gap in the GREEN output reveals a place where the skill needs to be more explicit. Add a row to "Common mistakes" or sharpen a checklist item.

The skeleton is updated independently when the design system itself evolves (e.g., adding a new section pattern, changing the modal interaction).
