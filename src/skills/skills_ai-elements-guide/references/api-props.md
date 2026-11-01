# AI Elements API Props (Snapshot)

This file is a snapshot of the `## Props` sections from the AI Elements docs.
Update rule: regenerate from docs when new links appear.

## Agent
Doc: https://ai-sdk.dev/elements/components/agent
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/agent.mdx

```mdx
## Props

### `<Agent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any props are spread to the root div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<AgentHeader />`

<TypeTable
  type={{
    name: {
      description: 'The name of the agent.',
      type: 'string',
      required: true,
    },
    model: {
      description: 'The model identifier (e.g. "anthropic/claude-sonnet-4-5").',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the container div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<AgentContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the container div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<AgentInstructions />`

<TypeTable
  type={{
    children: {
      description: 'The instruction text.',
      type: 'string',
      required: true,
    },
    '...props': {
      description: 'Any other props are spread to the container div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<AgentTools />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the Accordion component.',
      type: 'React.ComponentProps<typeof Accordion>',
    },
  }}
/>

### `<AgentTool />`

<TypeTable
  type={{
    tool: {
      description: 'The tool object from the AI SDK containing description and inputSchema.',
      type: 'Tool',
      required: true,
    },
    value: {
      description: 'Unique identifier for the accordion item.',
      type: 'string',
      required: true,
    },
    '...props': {
      description: 'Any other props are spread to the AccordionItem component.',
      type: 'React.ComponentProps<typeof AccordionItem>',
    },
  }}
/>

### `<AgentOutput />`

<TypeTable
  type={{
    schema: {
      description: 'The output schema as a string (displayed with syntax highlighting).',
      type: 'string',
      required: true,
    },
    '...props': {
      description: 'Any other props are spread to the container div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>
```

## Artifact
Doc: https://ai-sdk.dev/elements/components/artifact
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/artifact.mdx

```mdx
## Props

### `<Artifact />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<ArtifactHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<ArtifactTitle />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying paragraph element.',
      type: 'React.HTMLAttributes<HTMLParagraphElement>',
    },
  }}
/>

### `<ArtifactDescription />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying paragraph element.',
      type: 'React.HTMLAttributes<HTMLParagraphElement>',
    },
  }}
/>

### `<ArtifactActions />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<ArtifactAction />`

<TypeTable
  type={{
    tooltip: {
      description: 'Tooltip text to display on hover.',
      type: 'string',
    },
    label: {
      description: 'Screen reader label for the action button.',
      type: 'string',
    },
    icon: {
      description: 'Lucide icon component to display in the button.',
      type: 'LucideIcon',
    },
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<ArtifactClose />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<ArtifactContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>
```

## Attachments
Doc: https://ai-sdk.dev/elements/components/attachments
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/attachments.mdx

```mdx
## Props

### `<Attachments />`

Container component that sets the layout variant.

<TypeTable
  type={{
    variant: {
      description: 'The display layout variant.',
      type: '"grid" | "inline" | "list"',
      default: '"grid"',
      optional: true,
    },
    '...props': {
      description: 'Spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<Attachment />`

Individual attachment item wrapper.

<TypeTable
  type={{
    data: {
      description: 'The attachment data (FileUIPart or SourceDocumentUIPart with id).',
      type: '(FileUIPart & { id: string }) | (SourceDocumentUIPart & { id: string })',
    },
    onRemove: {
      description: 'Callback fired when the remove button is clicked.',
      type: '() => void',
      optional: true,
    },
    '...props': {
      description: 'Spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<AttachmentPreview />`

Displays the media preview (image, video, or icon).

<TypeTable
  type={{
    fallbackIcon: {
      description: 'Custom icon to display when no preview is available.',
      type: 'React.ReactNode',
      optional: true,
    },
    '...props': {
      description: 'Spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<AttachmentInfo />`

Displays the filename and optional media type.

<TypeTable
  type={{
    showMediaType: {
      description: 'Whether to show the media type below the filename.',
      type: 'boolean',
      default: 'false',
      optional: true,
    },
    '...props': {
      description: 'Spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<AttachmentRemove />`

Remove button that appears on hover.

<TypeTable
  type={{
    label: {
      description: 'Screen reader label for the button.',
      type: 'string',
      default: '"Remove"',
      optional: true,
    },
    '...props': {
      description: 'Spread to the underlying Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<AttachmentHoverCard />`

Wrapper for hover preview functionality.

<TypeTable
  type={{
    openDelay: {
      description: 'Delay in ms before opening the hover card.',
      type: 'number',
      default: '0',
      optional: true,
    },
    closeDelay: {
      description: 'Delay in ms before closing the hover card.',
      type: 'number',
      default: '0',
      optional: true,
    },
    '...props': {
      description: 'Spread to the underlying HoverCard component.',
      type: 'React.ComponentProps<typeof HoverCard>',
    },
  }}
/>

### `<AttachmentHoverCardTrigger />`

Trigger element for the hover card.

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the underlying HoverCardTrigger component.',
      type: 'React.ComponentProps<typeof HoverCardTrigger>',
    },
  }}
/>

### `<AttachmentHoverCardContent />`

Content displayed in the hover card.

<TypeTable
  type={{
    align: {
      description: 'Alignment of the hover card content.',
      type: '"start" | "center" | "end"',
      default: '"start"',
      optional: true,
    },
    '...props': {
      description: 'Spread to the underlying HoverCardContent component.',
      type: 'React.ComponentProps<typeof HoverCardContent>',
    },
  }}
/>

### `<AttachmentEmpty />`

Empty state component when no attachments are present.

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the underlying div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>
```

## Audio Player
Doc: https://ai-sdk.dev/elements/components/audio-player
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(voice)/audio-player.mdx

```mdx
## Props

### `<AudioPlayer />`

Root MediaController component. Accepts all MediaController props except `audio` (which is set to `true` by default).

<TypeTable
  type={{
    style: {
      description: 'Custom CSS properties can be passed to override media-chrome theming variables.',
      type: 'CSSProperties',
    },
    '...props': {
      description: 'Any other props are spread to the MediaController component.',
      type: 'Omit<React.ComponentProps<typeof MediaController>, "audio">',
    },
  }}
/>

### `<AudioPlayerElement />`

The audio element that contains the media source. Accepts either a remote URL or AI SDK Speech Result data.

<TypeTable
  type={{
    src: {
      description: 'The URL of the audio file to play (for remote audio).',
      type: 'string',
      optional: true,
    },
    data: {
      description: 'AI SDK Speech Result audio data with base64 encoding (for AI-generated audio).',
      type: 'SpeechResult["audio"]',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the audio element (excluding src when using data).',
      type: 'Omit<React.ComponentProps<"audio">, "src">',
    },
  }}
/>

### `<AudioPlayerControlBar />`

Container for control buttons, wraps children in a ButtonGroup.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the MediaControlBar component.',
      type: 'React.ComponentProps<typeof MediaControlBar>',
    },
  }}
/>

### `<AudioPlayerPlayButton />`

Play/pause button wrapped in a shadcn Button component.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the MediaPlayButton component.',
      type: 'React.ComponentProps<typeof MediaPlayButton>',
    },
  }}
/>

### `<AudioPlayerSeekBackwardButton />`

Seek backward button wrapped in a shadcn Button component.

<TypeTable
  type={{
    seekOffset: {
      description: 'The number of seconds to seek backward.',
      type: 'number',
      default: '10',
    },
    '...props': {
      description: 'Any other props are spread to the MediaSeekBackwardButton component.',
      type: 'React.ComponentProps<typeof MediaSeekBackwardButton>',
    },
  }}
/>

### `<AudioPlayerSeekForwardButton />`

Seek forward button wrapped in a shadcn Button component.

<TypeTable
  type={{
    seekOffset: {
      description: 'The number of seconds to seek forward.',
      type: 'number',
      default: '10',
    },
    '...props': {
      description: 'Any other props are spread to the MediaSeekForwardButton component.',
      type: 'React.ComponentProps<typeof MediaSeekForwardButton>',
    },
  }}
/>

### `<AudioPlayerTimeDisplay />`

Displays the current playback time, wrapped in ButtonGroupText.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the MediaTimeDisplay component.',
      type: 'React.ComponentProps<typeof MediaTimeDisplay>',
    },
  }}
/>

### `<AudioPlayerTimeRange />`

Seek slider for controlling playback position, wrapped in ButtonGroupText.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the MediaTimeRange component.',
      type: 'React.ComponentProps<typeof MediaTimeRange>',
    },
  }}
/>

### `<AudioPlayerDurationDisplay />`

Displays the total duration of the audio, wrapped in ButtonGroupText.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the MediaDurationDisplay component.',
      type: 'React.ComponentProps<typeof MediaDurationDisplay>',
    },
  }}
/>

### `<AudioPlayerMuteButton />`

Mute/unmute button, wrapped in ButtonGroupText.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the MediaMuteButton component.',
      type: 'React.ComponentProps<typeof MediaMuteButton>',
    },
  }}
/>

### `<AudioPlayerVolumeRange />`

Volume slider control, wrapped in ButtonGroupText.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the MediaVolumeRange component.',
      type: 'React.ComponentProps<typeof MediaVolumeRange>',
    },
  }}
/>
```

## Canvas
Doc: https://ai-sdk.dev/elements/components/canvas
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(workflow)/canvas.mdx

```mdx
## Props

### `<Canvas />`

<TypeTable
  type={{
    children: {
      description: 'Child components like Background, Controls, or MiniMap.',
      type: 'ReactNode',
    },
    '...props': {
      description: 'Any other React Flow props like nodes, edges, nodeTypes, edgeTypes, onNodesChange, etc.',
      type: 'ReactFlowProps',
    },
  }}
/>
```

## Chain of Thought
Doc: https://ai-sdk.dev/elements/components/chain-of-thought
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/chain-of-thought.mdx

```mdx
## Props

### `<ChainOfThought />`

<TypeTable
  type={{
    open: {
      description: 'Controlled open state of the collapsible.',
      type: 'boolean',
    },
    defaultOpen: {
      description: 'Default open state when uncontrolled.',
      type: 'boolean',
      default: 'false',
    },
    onOpenChange: {
      description: 'Callback when the open state changes.',
      type: '(open: boolean) => void',
    },
    '...props': {
      description: 'Any other props are spread to the root div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<ChainOfThoughtHeader />`

<TypeTable
  type={{
    children: {
      description: 'Custom header text.',
      type: 'React.ReactNode',
      default: '"Chain of Thought"',
    },
    '...props': {
      description: 'Any other props are spread to the CollapsibleTrigger component.',
      type: 'React.ComponentProps<typeof CollapsibleTrigger>',
    },
  }}
/>

### `<ChainOfThoughtStep />`

<TypeTable
  type={{
    icon: {
      description: 'Icon to display for the step.',
      type: 'LucideIcon',
      default: 'DotIcon',
    },
    label: {
      description: 'The main text label for the step.',
      type: 'string',
    },
    description: {
      description: 'Optional description text shown below the label.',
      type: 'string',
    },
    status: {
      description: 'Visual status of the step.',
      type: '"complete" | "active" | "pending"',
      default: '"complete"',
    },
    '...props': {
      description: 'Any other props are spread to the root div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<ChainOfThoughtSearchResults />`

<TypeTable
  type={{
    '...props': {
      description: 'Any props are spread to the container div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<ChainOfThoughtSearchResult />`

<TypeTable
  type={{
    '...props': {
      description: 'Any props are spread to the Badge component.',
      type: 'React.ComponentProps<typeof Badge>',
    },
  }}
/>

### `<ChainOfThoughtContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any props are spread to the CollapsibleContent component.',
      type: 'React.ComponentProps<typeof CollapsibleContent>',
    },
  }}
/>

### `<ChainOfThoughtImage />`

<TypeTable
  type={{
    caption: {
      description: 'Optional caption text displayed below the image.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the container div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>
```

## Checkpoint
Doc: https://ai-sdk.dev/elements/components/checkpoint
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/checkpoint.mdx

```mdx
## Props

### `<Checkpoint />`

<TypeTable
  type={{
    children: {
      description: 'The checkpoint icon and trigger components. Automatically includes a Separator at the end.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CheckpointIcon />`

<TypeTable
  type={{
    children: {
      description: 'Custom icon content. If not provided, defaults to a BookmarkIcon from lucide-react.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the BookmarkIcon component.',
      type: 'LucideProps',
    },
  }}
/>

### `<CheckpointTrigger />`

<TypeTable
  type={{
    children: {
      description: 'The text or content to display in the trigger button.',
      type: 'React.ReactNode',
    },
    variant: {
      description: 'The button variant style.',
      type: 'string',
      default: '"ghost"',
    },
    size: {
      description: 'The button size.',
      type: 'string',
      default: '"sm"',
    },
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>
```

## Code Block
Doc: https://ai-sdk.dev/elements/components/code-block
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/code-block.mdx

```mdx
## Props

### `<CodeBlock />`

<TypeTable
  type={{
    code: {
      description: 'The code content to display.',
      type: 'string',
    },
    language: {
      description: 'The programming language for syntax highlighting.',
      type: 'BundledLanguage',
    },
    showLineNumbers: {
      description: 'Whether to show line numbers.',
      type: 'boolean',
      default: 'false',
    },
    children: {
      description: 'Child elements like CodeBlockHeader.',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<CodeBlockHeader />`

Container for the header row. Uses flexbox with `justify-between`.

<TypeTable
  type={{
    children: {
      description: 'Header content (CodeBlockTitle, CodeBlockActions, etc.).',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<CodeBlockTitle />`

Left-aligned container for icon and filename. Uses flexbox with `gap-2`.

<TypeTable
  type={{
    children: {
      description: 'Title content (icon, CodeBlockFilename, etc.).',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<CodeBlockFilename />`

Displays the filename in monospace font.

<TypeTable
  type={{
    children: {
      description: 'The filename to display.',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<CodeBlockActions />`

Right-aligned container for action buttons. Uses flexbox with `gap-2`.

<TypeTable
  type={{
    children: {
      description: 'Action buttons (CodeBlockCopyButton, CodeBlockLanguageSelector, etc.).',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<CodeBlockCopyButton />`

<TypeTable
  type={{
    onCopy: {
      description: 'Callback fired after a successful copy.',
      type: '() => void',
    },
    onError: {
      description: 'Callback fired if copying fails.',
      type: '(error: Error) => void',
    },
    timeout: {
      description: 'How long to show the copied state (ms).',
      type: 'number',
      default: '2000',
    },
    children: {
      description: 'Custom content for the button. Defaults to copy/check icons.',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<CodeBlockLanguageSelector />`

Wrapper for the language selector. Extends shadcn/ui Select.

<TypeTable
  type={{
    value: {
      description: 'The currently selected language.',
      type: 'string',
    },
    onValueChange: {
      description: 'Callback when the language changes.',
      type: '(value: string) => void',
    },
    children: {
      description: 'Selector components (Trigger, Content, Items).',
      type: 'React.ReactNode',
    },
  }}
/>

### `<CodeBlockLanguageSelectorTrigger />`

Trigger button for the language selector dropdown. Pre-styled for code block header.

### `<CodeBlockLanguageSelectorValue />`

Displays the selected language value.

### `<CodeBlockLanguageSelectorContent />`

Dropdown content container. Defaults to `align="end"`.

### `<CodeBlockLanguageSelectorItem />`

Individual language option in the dropdown.

<TypeTable
  type={{
    value: {
      description: 'The language value.',
      type: 'string',
    },
    children: {
      description: 'The display label.',
      type: 'React.ReactNode',
    },
  }}
/>

### `<CodeBlockContainer />`

Low-level container component with performance optimizations (`contentVisibility`). Used internally by CodeBlock.

### `<CodeBlockContent />`

Low-level component that handles syntax highlighting. Used internally by CodeBlock, but can be used directly for custom layouts.

<TypeTable
  type={{
    code: {
      description: 'The code content to display.',
      type: 'string',
    },
    language: {
      description: 'The programming language for syntax highlighting.',
      type: 'BundledLanguage',
    },
    showLineNumbers: {
      description: 'Whether to show line numbers.',
      type: 'boolean',
      default: 'false',
    },
  }}
/>
```

## Commit
Doc: https://ai-sdk.dev/elements/components/commit
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/commit.mdx

```mdx
## Props

### `<Commit />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the Collapsible component.',
      type: 'React.ComponentProps<typeof Collapsible>',
    },
  }}
/>

### `<CommitHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the CollapsibleTrigger component.',
      type: 'React.ComponentProps<typeof CollapsibleTrigger>',
    },
  }}
/>

### `<CommitAuthor />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CommitAuthorAvatar />`

<TypeTable
  type={{
    initials: {
      description: 'Author initials to display.',
      type: 'string',
      required: true,
    },
    '...props': {
      description: 'Spread to the Avatar component.',
      type: 'React.ComponentProps<typeof Avatar>',
    },
  }}
/>

### `<CommitInfo />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CommitMessage />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<CommitMetadata />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CommitHash />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<CommitSeparator />`

<TypeTable
  type={{
    children: {
      description: 'Custom separator content.',
      type: 'React.ReactNode',
      default: '"•"',
    },
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<CommitTimestamp />`

<TypeTable
  type={{
    date: {
      description: 'Commit date.',
      type: 'Date',
      required: true,
    },
    children: {
      description: 'Custom timestamp content. Defaults to relative time.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the time element.',
      type: 'React.HTMLAttributes<HTMLTimeElement>',
    },
  }}
/>

### `<CommitActions />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CommitCopyButton />`

<TypeTable
  type={{
    hash: {
      description: 'Commit hash to copy.',
      type: 'string',
      required: true,
    },
    onCopy: {
      description: 'Callback after successful copy.',
      type: '() => void',
    },
    onError: {
      description: 'Callback if copying fails.',
      type: '(error: Error) => void',
    },
    timeout: {
      description: 'Duration to show copied state (ms).',
      type: 'number',
      default: '2000',
    },
    '...props': {
      description: 'Spread to the Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<CommitContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the CollapsibleContent component.',
      type: 'React.ComponentProps<typeof CollapsibleContent>',
    },
  }}
/>

### `<CommitFiles />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CommitFile />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the row div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CommitFileInfo />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CommitFileStatus />`

<TypeTable
  type={{
    status: {
      description: 'File change status.',
      type: '"added" | "modified" | "deleted" | "renamed"',
      required: true,
    },
    children: {
      description: 'Custom status label.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<CommitFileIcon />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the FileIcon component.',
      type: 'React.ComponentProps<typeof FileIcon>',
    },
  }}
/>

### `<CommitFilePath />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<CommitFileChanges />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<CommitFileAdditions />`

<TypeTable
  type={{
    count: {
      description: 'Number of lines added.',
      type: 'number',
      required: true,
    },
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<CommitFileDeletions />`

<TypeTable
  type={{
    count: {
      description: 'Number of lines deleted.',
      type: 'number',
      required: true,
    },
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>
```

## Confirmation
Doc: https://ai-sdk.dev/elements/components/confirmation
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/confirmation.mdx

```mdx
## Props

### `<Confirmation />`

<TypeTable
  type={{
    approval: {
      description: 'The approval object containing the approval ID and status. If not provided or undefined, the component will not render.',
      type: 'ToolUIPart["approval"]',
    },
    state: {
      description: 'The current state of the tool (input-streaming, input-available, approval-requested, approval-responded, output-denied, or output-available). Will not render for input-streaming or input-available states.',
      type: 'ToolUIPart["state"]',
    },
    className: {
      description: 'Additional CSS classes to apply to the Alert component.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the Alert component.',
      type: 'React.ComponentProps<typeof Alert>',
    },
  }}
/>

### `<ConfirmationRequest />`

<TypeTable
  type={{
    children: {
      description: 'The content to display when approval is requested. Only renders when state is "approval-requested".',
      type: 'React.ReactNode',
    },
  }}
/>

### `<ConfirmationAccepted />`

<TypeTable
  type={{
    children: {
      description: 'The content to display when approval is accepted. Only renders when approval.approved is true and state is "approval-responded", "output-denied", or "output-available".',
      type: 'React.ReactNode',
    },
  }}
/>

### `<ConfirmationRejected />`

<TypeTable
  type={{
    children: {
      description: 'The content to display when approval is rejected. Only renders when approval.approved is false and state is "approval-responded", "output-denied", or "output-available".',
      type: 'React.ReactNode',
    },
  }}
/>

### `<ConfirmationActions />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply to the actions container.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the div element. Only renders when state is "approval-requested".',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<ConfirmationAction />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the Button component. Styled with h-8 px-3 text-sm classes by default.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>
```

## Connection
Doc: https://ai-sdk.dev/elements/components/connection
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(workflow)/connection.mdx

```mdx
## Props

### `<Connection />`

<TypeTable
  type={{
    fromX: {
      description: 'The x-coordinate of the connection start point.',
      type: 'number',
    },
    fromY: {
      description: 'The y-coordinate of the connection start point.',
      type: 'number',
    },
    toX: {
      description: 'The x-coordinate of the connection end point.',
      type: 'number',
    },
    toY: {
      description: 'The y-coordinate of the connection end point.',
      type: 'number',
    },
  }}
/>
```

## Context
Doc: https://ai-sdk.dev/elements/components/context
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/context.mdx

```mdx
## Props

### `<Context />`

<TypeTable
  type={{
    maxTokens: {
      description: 'The total context window size in tokens.',
      type: 'number',
    },
    usedTokens: {
      description: 'The number of tokens currently used.',
      type: 'number',
    },
    usage: {
      description: 'Detailed token usage breakdown from the AI SDK (input, output, reasoning, cached tokens).',
      type: 'LanguageModelUsage',
    },
    modelId: {
      description: 'Model identifier for cost calculation (e.g., "openai:gpt-4", "anthropic:claude-3-opus").',
      type: 'ModelId',
    },
    '...props': {
      description: 'Any other props are spread to the HoverCard component.',
      type: 'ComponentProps<HoverCard>',
    },
  }}
/>

### `<ContextTrigger />`

<TypeTable
  type={{
    children: {
      description: 'Custom trigger element. If not provided, renders a default button with percentage and icon.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Props spread to the default button element.',
      type: 'ComponentProps<Button>',
    },
  }}
/>

### `<ContextContent />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes for the hover card content.',
      type: 'string',
    },
    '...props': {
      description: 'Props spread to the HoverCardContent component.',
      type: 'ComponentProps<HoverCardContent>',
    },
  }}
/>

### `<ContextContentHeader />`

<TypeTable
  type={{
    children: {
      description: 'Custom header content. If not provided, renders percentage and token count with progress bar.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Props spread to the header div element.',
      type: 'ComponentProps<div>',
    },
  }}
/>

### `<ContextContentBody />`

<TypeTable
  type={{
    children: {
      description: 'Body content, typically containing usage breakdown components.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Props spread to the body div element.',
      type: 'ComponentProps<div>',
    },
  }}
/>

### `<ContextContentFooter />`

<TypeTable
  type={{
    children: {
      description: 'Custom footer content. If not provided, renders total cost when modelId is provided.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Props spread to the footer div element.',
      type: 'ComponentProps<div>',
    },
  }}
/>

### Usage Components

All usage components (`ContextInputUsage`, `ContextOutputUsage`, `ContextReasoningUsage`, `ContextCacheUsage`) share the same props:

<TypeTable
  type={{
    children: {
      description: 'Custom content. If not provided, renders token count and cost for the respective usage type.',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Props spread to the div element.',
      type: 'ComponentProps<div>',
    },
  }}
/>
```

## Controls
Doc: https://ai-sdk.dev/elements/components/controls
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(workflow)/controls.mdx

```mdx
## Props

### `<Controls />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply to the controls.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props from @xyflow/react Controls component (showZoom, showFitView, showInteractive, position, etc.).',
      type: 'ComponentProps<typeof Controls>',
    },
  }}
/>
```

## Conversation
Doc: https://ai-sdk.dev/elements/components/conversation
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/conversation.mdx

```mdx
## Props

### `<Conversation />`

<TypeTable
  type={{
    contextRef: {
      description: 'Optional ref to access the StickToBottom context object.',
      type: 'React.Ref<StickToBottomContext>',
    },
    instance: {
      description: 'Optional instance for controlling the StickToBottom component.',
      type: 'StickToBottomInstance',
    },
    children: {
      description: 'Render prop or ReactNode for custom rendering with context.',
      type: '((context: StickToBottomContext) => ReactNode) | ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'Omit<React.HTMLAttributes<HTMLDivElement>, "children">',
    },
  }}
/>

### `<ConversationContent />`

<TypeTable
  type={{
    children: {
      description: 'Render prop or ReactNode for custom rendering with context.',
      type: '((context: StickToBottomContext) => ReactNode) | ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'Omit<React.HTMLAttributes<HTMLDivElement>, "children">',
    },
  }}
/>

### `<ConversationEmptyState />`

<TypeTable
  type={{
    title: {
      description: 'The title text to display.',
      type: 'string',
      default: '"No messages yet"',
    },
    description: {
      description: 'The description text to display.',
      type: 'string',
      default: '"Start a conversation to see messages here"',
    },
    icon: {
      description: 'Optional icon to display above the text.',
      type: 'React.ReactNode',
    },
    children: {
      description: 'Optional additional content to render below the text.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'ComponentProps<"div">',
    },
  }}
/>

### `<ConversationScrollButton />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'ComponentProps<typeof Button>',
    },
  }}
/>
```

## Edge
Doc: https://ai-sdk.dev/elements/components/edge
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(workflow)/edge.mdx

```mdx
## Props

Both edge types accept standard React Flow `EdgeProps`:

<TypeTable
  type={{
    id: {
      description: 'Unique identifier for the edge.',
      type: 'string',
    },
    source: {
      description: 'ID of the source node.',
      type: 'string',
    },
    target: {
      description: 'ID of the target node.',
      type: 'string',
    },
    sourceX: {
      description: 'X coordinate of the source handle (Temporary only).',
      type: 'number',
    },
    sourceY: {
      description: 'Y coordinate of the source handle (Temporary only).',
      type: 'number',
    },
    targetX: {
      description: 'X coordinate of the target handle (Temporary only).',
      type: 'number',
    },
    targetY: {
      description: 'Y coordinate of the target handle (Temporary only).',
      type: 'number',
    },
    sourcePosition: {
      description: 'Position of the source handle (Left, Right, Top, Bottom).',
      type: 'Position',
    },
    targetPosition: {
      description: 'Position of the target handle (Left, Right, Top, Bottom).',
      type: 'Position',
    },
    markerEnd: {
      description: 'SVG marker ID for the edge end (Animated only).',
      type: 'string',
    },
    style: {
      description: 'Custom styles for the edge (Animated only).',
      type: 'React.CSSProperties',
    },
  }}
/>
```

## Environment Variables
Doc: https://ai-sdk.dev/elements/components/environment-variables
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/environment-variables.mdx

```mdx
## Props

### `<EnvironmentVariables />`

<TypeTable
  type={{
    showValues: {
      description: 'Controlled visibility state.',
      type: 'boolean',
    },
    defaultShowValues: {
      description: 'Default visibility state.',
      type: 'boolean',
      default: 'false',
    },
    onShowValuesChange: {
      description: 'Callback when visibility changes.',
      type: '(show: boolean) => void',
    },
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<EnvironmentVariablesHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the header div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<EnvironmentVariablesTitle />`

<TypeTable
  type={{
    children: {
      description: 'Custom title text.',
      type: 'React.ReactNode',
      default: '"Environment Variables"',
    },
    '...props': {
      description: 'Spread to the h3 element.',
      type: 'React.HTMLAttributes<HTMLHeadingElement>',
    },
  }}
/>

### `<EnvironmentVariablesToggle />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the Switch component.',
      type: 'React.ComponentProps<typeof Switch>',
    },
  }}
/>

### `<EnvironmentVariablesContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the content div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<EnvironmentVariable />`

<TypeTable
  type={{
    name: {
      description: 'Variable name.',
      type: 'string',
      required: true,
    },
    value: {
      description: 'Variable value.',
      type: 'string',
      required: true,
    },
    '...props': {
      description: 'Spread to the row div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<EnvironmentVariableGroup />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the group div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<EnvironmentVariableName />`

<TypeTable
  type={{
    children: {
      description: 'Custom name content. Defaults to the name from context.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<EnvironmentVariableValue />`

<TypeTable
  type={{
    children: {
      description: 'Custom value content. Defaults to the masked/unmasked value from context.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<EnvironmentVariableCopyButton />`

<TypeTable
  type={{
    copyFormat: {
      description: 'Format to copy.',
      type: '"name" | "value" | "export"',
      default: '"value"',
    },
    onCopy: {
      description: 'Callback after successful copy.',
      type: '() => void',
    },
    onError: {
      description: 'Callback if copying fails.',
      type: '(error: Error) => void',
    },
    timeout: {
      description: 'Duration to show copied state (ms).',
      type: 'number',
      default: '2000',
    },
    '...props': {
      description: 'Spread to the Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<EnvironmentVariableRequired />`

<TypeTable
  type={{
    children: {
      description: 'Custom badge text.',
      type: 'React.ReactNode',
      default: '"Required"',
    },
    '...props': {
      description: 'Spread to the Badge component.',
      type: 'React.ComponentProps<typeof Badge>',
    },
  }}
/>
```

## File Tree
Doc: https://ai-sdk.dev/elements/components/file-tree
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/file-tree.mdx

```mdx
## Props

### `<FileTree />`

<TypeTable
  type={{
    expanded: {
      description: 'Controlled expanded paths.',
      type: 'Set<string>',
    },
    defaultExpanded: {
      description: 'Default expanded paths.',
      type: 'Set<string>',
      default: 'new Set()',
    },
    selectedPath: {
      description: 'Currently selected file/folder path.',
      type: 'string',
    },
    onSelect: {
      description: 'Callback when a file/folder is selected.',
      type: '(path: string) => void',
    },
    onExpandedChange: {
      description: 'Callback when expanded paths change.',
      type: '(expanded: Set<string>) => void',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<FileTreeFolder />`

<TypeTable
  type={{
    path: {
      description: 'Unique folder path.',
      type: 'string',
    },
    name: {
      description: 'Display name.',
      type: 'string',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<FileTreeFile />`

<TypeTable
  type={{
    path: {
      description: 'Unique file path.',
      type: 'string',
    },
    name: {
      description: 'Display name.',
      type: 'string',
    },
    icon: {
      description: 'Custom file icon.',
      type: 'ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### Subcomponents

- `FileTreeIcon` - Icon wrapper
- `FileTreeName` - Name text
- `FileTreeActions` - Action buttons container (stops click propagation)
```

## Image
Doc: https://ai-sdk.dev/elements/components/image
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(utilities)/image.mdx

```mdx
## Props

### `<Image />`

<TypeTable
  type={{
    alt: {
      description: 'Alternative text for the image.',
      type: 'string',
    },
    className: {
      description: 'Additional CSS classes to apply to the image.',
      type: 'string',
    },
    '...props': {
      description: 'The image data to display, as returned by the AI SDK.',
      type: 'Experimental_GeneratedImage',
    },
  }}
/>
```

## Inline Citation
Doc: https://ai-sdk.dev/elements/components/inline-citation
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/inline-citation.mdx

```mdx
## Props

### `<InlineCitation />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the root span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<InlineCitationText />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<InlineCitationCard />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the HoverCard component.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<InlineCitationCardTrigger />`

<TypeTable
  type={{
    sources: {
      description: 'Array of source URLs. The length determines the number displayed in the badge.',
      type: 'string[]',
    },
    '...props': {
      description: 'Any other props are spread to the underlying button element.',
      type: 'React.ComponentProps<"button">',
    },
  }}
/>

### `<InlineCitationCardBody />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<InlineCitationCarousel />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying Carousel component.',
      type: 'React.ComponentProps<typeof Carousel>',
    },
  }}
/>

### `<InlineCitationCarouselContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CarouselContent component.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<InlineCitationCarouselItem />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<InlineCitationCarouselHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<InlineCitationCarouselIndex />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div. Children will override the default index display.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<InlineCitationCarouselPrev />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CarouselPrevious component.',
      type: 'React.ComponentProps<typeof CarouselPrevious>',
    },
  }}
/>

### `<InlineCitationCarouselNext />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CarouselNext component.',
      type: 'React.ComponentProps<typeof CarouselNext>',
    },
  }}
/>

### `<InlineCitationSource />`

<TypeTable
  type={{
    title: {
      description: 'The title of the source.',
      type: 'string',
    },
    url: {
      description: 'The URL of the source.',
      type: 'string',
    },
    description: {
      description: 'A brief description of the source.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the underlying div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<InlineCitationQuote />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying blockquote element.',
      type: 'React.ComponentProps<"blockquote">',
    },
  }}
/>
```

## Loader
Doc: https://ai-sdk.dev/elements/components/loader
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(utilities)/loader.mdx

```mdx
## Props

### `<Loader />`

<TypeTable
  type={{
    size: {
      description: 'The size (width and height) of the loader in pixels.',
      type: 'number',
      default: '16',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>
```

## Message
Doc: https://ai-sdk.dev/elements/components/message
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/message.mdx

```mdx
## Props

### `<Message />`

<TypeTable
  type={{
    from: {
      description:
        'The role of the message sender ("user", "assistant", or "system").',
      type: 'UIMessage["role"]',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<MessageContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the content div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<MessageResponse />`

<TypeTable
  type={{
    children: {
      description: 'The markdown content to render.',
      type: 'string',
    },
    parseIncompleteMarkdown: {
      description: 'Whether to parse and fix incomplete markdown syntax (e.g., unclosed code blocks or lists).',
      type: 'boolean',
      default: 'true',
    },
    className: {
      description: 'CSS class names to apply to the wrapper div element.',
      type: 'string',
    },
    components: {
      description: 'Custom React components to use for rendering markdown elements (e.g., custom heading, paragraph, code block components).',
      type: 'object',
    },
    allowedImagePrefixes: {
      description: 'Array of allowed URL prefixes for images. Use ["*"] to allow all images.',
      type: 'string[]',
      default: '["*"]',
    },
    allowedLinkPrefixes: {
      description: 'Array of allowed URL prefixes for links. Use ["*"] to allow all links.',
      type: 'string[]',
      default: '["*"]',
    },
    defaultOrigin: {
      description: 'Default origin to use for relative URLs in links and images.',
      type: 'string',
    },
    rehypePlugins: {
      description: 'Array of rehype plugins to use for processing HTML. Includes KaTeX for math rendering by default.',
      type: 'array',
      default: '[rehypeKatex]',
    },
    remarkPlugins: {
      description: 'Array of remark plugins to use for processing markdown. Includes GitHub Flavored Markdown and math support by default.',
      type: 'array',
      default: '[remarkGfm, remarkMath]',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<MessageActions />`

<TypeTable
  type={{
    '...props': {
      description: 'HTML attributes to spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<MessageAction />`

<TypeTable
  type={{
    tooltip: {
      description: 'Optional tooltip text shown on hover.',
      type: 'string',
    },
    label: {
      description:
        'Accessible label for screen readers. Also used as fallback if tooltip is not provided.',
      type: 'string',
    },
    '...props': {
      description:
        'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<MessageBranch />`

<TypeTable
  type={{
    defaultBranch: {
      description: 'The index of the branch to show by default.',
      type: 'number',
      default: '0',
    },
    onBranchChange: {
      description: 'Callback fired when the branch changes.',
      type: '(branchIndex: number) => void',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<MessageBranchContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<MessageBranchSelector />`

<TypeTable
  type={{
    from: {
      description: 'Aligns the selector for user, assistant or system messages.',
      type: 'UIMessage["role"]',
    },
    '...props': {
      description: 'Any other props are spread to the selector container.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<MessageBranchPrevious />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<MessageBranchNext />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<MessageBranchPage />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<MessageAttachments />`

A container component for displaying file attachments in a message. Automatically positions attachments at the end of the message with proper spacing and alignment.

<TypeTable
  type={{
    children: {
      description: 'MessageAttachment components to render. Returns null if no children provided.',
      type: 'ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

**Example:**

```tsx
<MessageAttachments className="mb-2">
  {files.map((attachment) => (
    <MessageAttachment data={attachment} key={attachment.url} />
  ))}
</MessageAttachments>
```

### `<MessageAttachment />`

Displays a single file attachment. Images are shown as thumbnails (96px × 96px) with rounded corners. Non-image files show a paperclip icon with the filename.

<TypeTable
  type={{
    data: {
      description: 'The file data to display. Must include url and mediaType.',
      type: 'FileUIPart',
    },
    onRemove: {
      description: 'Optional callback fired when the remove button is clicked. If provided, a remove button will appear on hover.',
      type: '() => void',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

**Example:**

```tsx
<MessageAttachment
  data={{
    type: "file",
    url: "https://example.com/image.jpg",
    mediaType: "image/jpeg",
    filename: "image.jpg"
  }}
  onRemove={() => console.log("Remove clicked")}
/>
```
```

## Mic Selector
Doc: https://ai-sdk.dev/elements/components/mic-selector
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(voice)/mic-selector.mdx

```mdx
## Props

### `<MicSelector />`

Root Popover component that provides context for all child components.

<TypeTable
  type={{
    defaultValue: {
      description: 'The default selected device ID (uncontrolled).',
      type: 'string',
      optional: true,
    },
    value: {
      description: 'The selected device ID (controlled).',
      type: 'string',
      optional: true,
    },
    onValueChange: {
      description: 'Callback fired when the selected device changes.',
      type: '(deviceId: string) => void',
      optional: true,
    },
    defaultOpen: {
      description: 'The default open state (uncontrolled).',
      type: 'boolean',
      optional: true,
      default: 'false',
    },
    open: {
      description: 'The open state (controlled).',
      type: 'boolean',
      optional: true,
    },
    onOpenChange: {
      description: 'Callback fired when the open state changes. Automatically requests microphone permission when opened without permission.',
      type: '(open: boolean) => void',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the Popover component.',
      type: 'React.ComponentProps<typeof Popover>',
    },
  }}
/>

### `<MicSelectorTrigger />`

Button that opens the microphone selector popover. Automatically tracks its width to match the popover content.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<MicSelectorValue />`

Displays the currently selected microphone name or a placeholder.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<MicSelectorContent />`

Container for the Command component, rendered inside the popover.

<TypeTable
  type={{
    popoverOptions: {
      description: 'Props to pass to the underlying PopoverContent component.',
      type: 'React.ComponentProps<typeof PopoverContent>',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the Command component.',
      type: 'React.ComponentProps<typeof Command>',
    },
  }}
/>

### `<MicSelectorInput />`

Search input for filtering microphones.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandInput component.',
      type: 'React.ComponentProps<typeof CommandInput>',
    },
  }}
/>

### `<MicSelectorList />`

Wrapper for the list of microphone items. Uses render props pattern to provide access to device data.

<TypeTable
  type={{
    children: {
      description: 'Render function that receives the array of available devices.',
      type: '(devices: MediaDeviceInfo[]) => ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the CommandList component.',
      type: 'Omit<React.ComponentProps<typeof CommandList>, "children">',
    },
  }}
/>

### `<MicSelectorEmpty />`

Message shown when no microphones match the search.

<TypeTable
  type={{
    children: {
      description: 'The message to display.',
      type: 'ReactNode',
      default: '"No microphone found."',
    },
    '...props': {
      description: 'Any other props are spread to the CommandEmpty component.',
      type: 'React.ComponentProps<typeof CommandEmpty>',
    },
  }}
/>

### `<MicSelectorItem />`

Selectable item representing a microphone.

<TypeTable
  type={{
    value: {
      description: 'The device ID for this item.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the CommandItem component.',
      type: 'React.ComponentProps<typeof CommandItem>',
    },
  }}
/>

### `<MicSelectorLabel />`

Displays a formatted microphone label with intelligent device ID parsing. Automatically extracts and styles device IDs in the format (XXXX:XXXX).

<TypeTable
  type={{
    device: {
      description: 'The MediaDeviceInfo object for the device.',
      type: 'MediaDeviceInfo',
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>
```

## Model Selector
Doc: https://ai-sdk.dev/elements/components/model-selector
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/model-selector.mdx

```mdx
## Props

### `<ModelSelector />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying Dialog component.',
      type: 'React.ComponentProps<typeof Dialog>',
    },
  }}
/>

### `<ModelSelectorTrigger />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying DialogTrigger component.',
      type: 'React.ComponentProps<typeof DialogTrigger>',
    },
  }}
/>

### `<ModelSelectorContent />`

<TypeTable
  type={{
    title: {
      description: 'Accessible title for the dialog (rendered in sr-only).',
      type: 'ReactNode',
      default: '"Model Selector"',
    },
    '...props': {
      description: 'Any other props are spread to the underlying DialogContent component.',
      type: 'React.ComponentProps<typeof DialogContent>',
    },
  }}
/>

### `<ModelSelectorDialog />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CommandDialog component.',
      type: 'React.ComponentProps<typeof CommandDialog>',
    },
  }}
/>

### `<ModelSelectorInput />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CommandInput component.',
      type: 'React.ComponentProps<typeof CommandInput>',
    },
  }}
/>

### `<ModelSelectorList />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CommandList component.',
      type: 'React.ComponentProps<typeof CommandList>',
    },
  }}
/>

### `<ModelSelectorEmpty />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CommandEmpty component.',
      type: 'React.ComponentProps<typeof CommandEmpty>',
    },
  }}
/>

### `<ModelSelectorGroup />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CommandGroup component.',
      type: 'React.ComponentProps<typeof CommandGroup>',
    },
  }}
/>

### `<ModelSelectorItem />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CommandItem component.',
      type: 'React.ComponentProps<typeof CommandItem>',
    },
  }}
/>

### `<ModelSelectorShortcut />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CommandShortcut component.',
      type: 'React.ComponentProps<typeof CommandShortcut>',
    },
  }}
/>

### `<ModelSelectorSeparator />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CommandSeparator component.',
      type: 'React.ComponentProps<typeof CommandSeparator>',
    },
  }}
/>

### `<ModelSelectorLogo />`

<TypeTable
  type={{
    provider: {
      description: 'The AI provider name. Supports major providers like "openai", "anthropic", "google", "mistral", etc.',
      type: 'string',
      required: true,
    },
    '...props': {
      description: 'Any other props are spread to the underlying img element (except src and alt which are generated).',
      type: 'Omit<React.ComponentProps<"img">, "src" | "alt">',
    },
  }}
/>

### `<ModelSelectorLogoGroup />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<ModelSelectorName />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>
```

## Node
Doc: https://ai-sdk.dev/elements/components/node
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(workflow)/node.mdx

```mdx
## Props

### `<Node />`

<TypeTable
  type={{
    handles: {
      description: 'Configuration for connection handles. Target renders on the left, source on the right.',
      type: '{ target: boolean; source: boolean; }',
    },
    className: {
      description: 'Additional CSS classes to apply to the node.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the underlying Card component.',
      type: 'ComponentProps<typeof Card>',
    },
  }}
/>

### `<NodeHeader />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply to the header.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the underlying CardHeader component.',
      type: 'ComponentProps<typeof CardHeader>',
    },
  }}
/>

### `<NodeTitle />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CardTitle component.',
      type: 'ComponentProps<typeof CardTitle>',
    },
  }}
/>

### `<NodeDescription />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CardDescription component.',
      type: 'ComponentProps<typeof CardDescription>',
    },
  }}
/>

### `<NodeAction />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying CardAction component.',
      type: 'ComponentProps<typeof CardAction>',
    },
  }}
/>

### `<NodeContent />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply to the content.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the underlying CardContent component.',
      type: 'ComponentProps<typeof CardContent>',
    },
  }}
/>

### `<NodeFooter />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply to the footer.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the underlying CardFooter component.',
      type: 'ComponentProps<typeof CardFooter>',
    },
  }}
/>
```

## Open In Chat
Doc: https://ai-sdk.dev/elements/components/open-in-chat
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(utilities)/open-in-chat.mdx

```mdx
## Props

### `<OpenIn />`

<TypeTable
  type={{
    query: {
      description: 'The query text to be sent to all AI platforms.',
      type: 'string',
    },
    '...props': {
      description: 'Props to spread to the underlying radix-ui DropdownMenu component.',
      type: 'React.ComponentProps<typeof DropdownMenu>',
    },
  }}
/>

### `<OpenInTrigger />`

<TypeTable
  type={{
    children: {
      description: 'Custom trigger button.',
      type: 'React.ReactNode',
      default: '"Open in chat" button with chevron icon',
    },
    '...props': {
      description: 'Props to spread to the underlying DropdownMenuTrigger component.',
      type: 'React.ComponentProps<typeof DropdownMenuTrigger>',
    },
  }}
/>

### `<OpenInContent />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply to the dropdown content.',
      type: 'string',
    },
    '...props': {
      description: 'Props to spread to the underlying DropdownMenuContent component.',
      type: 'React.ComponentProps<typeof DropdownMenuContent>',
    },
  }}
/>

### `<OpenInChatGPT />`, `<OpenInClaude />`, `<OpenInT3 />`, `<OpenInScira />`, `<OpenInv0 />`, `<OpenInCursor />`

<TypeTable
  type={{
    '...props': {
      description: 'Props to spread to the underlying DropdownMenuItem component. The query is automatically provided via context from the parent OpenIn component.',
      type: 'React.ComponentProps<typeof DropdownMenuItem>',
    },
  }}
/>

### `<OpenInItem />`, `<OpenInLabel />`, `<OpenInSeparator />`

Additional composable components for custom dropdown menu items, labels, and separators that follow the same props pattern as their underlying radix-ui counterparts.
```

## Package Info
Doc: https://ai-sdk.dev/elements/components/package-info
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/package-info.mdx

```mdx
## Props

### `<PackageInfo />`

<TypeTable
  type={{
    name: {
      description: 'Package name.',
      type: 'string',
      required: true,
    },
    currentVersion: {
      description: 'Current installed version.',
      type: 'string',
    },
    newVersion: {
      description: 'New version being installed.',
      type: 'string',
    },
    changeType: {
      description: 'Type of version change.',
      type: '"major" | "minor" | "patch" | "added" | "removed"',
    },
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PackageInfoHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the header div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PackageInfoName />`

<TypeTable
  type={{
    children: {
      description: 'Custom name content. Defaults to the name from context.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PackageInfoChangeType />`

<TypeTable
  type={{
    children: {
      description: 'Custom change type label. Defaults to the changeType from context.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the Badge component.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PackageInfoVersion />`

<TypeTable
  type={{
    children: {
      description: 'Custom version content. Defaults to version transition display.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PackageInfoDescription />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the p element.',
      type: 'React.HTMLAttributes<HTMLParagraphElement>',
    },
  }}
/>

### `<PackageInfoContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PackageInfoDependencies />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PackageInfoDependency />`

<TypeTable
  type={{
    name: {
      description: 'Dependency name.',
      type: 'string',
      required: true,
    },
    version: {
      description: 'Dependency version.',
      type: 'string',
    },
    '...props': {
      description: 'Spread to the row div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>
```

## Panel
Doc: https://ai-sdk.dev/elements/components/panel
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(workflow)/panel.mdx

```mdx
## Props

### `<Panel />`

<TypeTable
  type={{
    position: {
      description: 'Position of the panel on the canvas.',
      type: "'top-left' | 'top-center' | 'top-right' | 'bottom-left' | 'bottom-center' | 'bottom-right'",
    },
    className: {
      description: 'Additional CSS classes to apply to the panel.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props from @xyflow/react Panel component.',
      type: 'ComponentProps<typeof Panel>',
    },
  }}
/>
```

## Persona
Doc: https://ai-sdk.dev/elements/components/persona
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(voice)/persona.mdx

```mdx
## Props

### `<Persona />`

The root component that renders the animated AI visual.

<TypeTable
  type={{
    state: {
      description:
        "The current state of the AI persona. Controls which animation is displayed.",
      type: '"idle" | "listening" | "thinking" | "speaking" | "asleep"',
      default: '"idle"',
    },
    variant: {
      description: "The visual style variant to display.",
      type: '"obsidian" | "mana" | "opal" | "halo" | "glint" | "command"',
      optional: true,
      default: '"obsidian"',
    },
    className: {
      description: "Additional CSS classes to apply to the component.",
      type: "string",
      optional: true,
    },
    onLoad: {
      description: "Callback fired when the Rive file starts loading.",
      type: 'RiveParameters["onLoad"]',
      optional: true,
    },
    onLoadError: {
      description: "Callback fired if the Rive file fails to load.",
      type: 'RiveParameters["onLoadError"]',
      optional: true,
    },
    onReady: {
      description: "Callback fired when the Rive animation is ready to play.",
      type: "() => void",
      optional: true,
    },
    onPause: {
      description: "Callback fired when the animation is paused.",
      type: 'RiveParameters["onPause"]',
      optional: true,
    },
    onPlay: {
      description: "Callback fired when the animation starts playing.",
      type: 'RiveParameters["onPlay"]',
      optional: true,
    },
    onStop: {
      description: "Callback fired when the animation is stopped.",
      type: 'RiveParameters["onStop"]',
      optional: true,
    },
  }}
/>
```

## Plan
Doc: https://ai-sdk.dev/elements/components/plan
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/plan.mdx

```mdx
## Props

### `<Plan />`

<TypeTable
  type={{
    isStreaming: {
      description: 'Whether content is currently streaming. Enables shimmer animations on title and description.',
      type: 'boolean',
      default: 'false',
    },
    defaultOpen: {
      description: 'Whether the plan is expanded by default.',
      type: 'boolean',
    },
    '...props': {
      description: 'Any other props are spread to the Collapsible component.',
      type: 'React.ComponentProps<typeof Collapsible>',
    },
  }}
/>

### `<PlanHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CardHeader component.',
      type: 'React.ComponentProps<typeof CardHeader>',
    },
  }}
/>

### `<PlanTitle />`

<TypeTable
  type={{
    children: {
      description: 'The title text. Displays with shimmer animation when isStreaming is true.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props (except children) are spread to the CardTitle component.',
      type: 'Omit<React.ComponentProps<typeof CardTitle>, "children">',
    },
  }}
/>

### `<PlanDescription />`

<TypeTable
  type={{
    children: {
      description: 'The description text. Displays with shimmer animation when isStreaming is true.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props (except children) are spread to the CardDescription component.',
      type: 'Omit<React.ComponentProps<typeof CardDescription>, "children">',
    },
  }}
/>

### `<PlanTrigger />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CollapsibleTrigger component. Renders as a Button with chevron icon.',
      type: 'React.ComponentProps<typeof CollapsibleTrigger>',
    },
  }}
/>

### `<PlanContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CardContent component.',
      type: 'React.ComponentProps<typeof CardContent>',
    },
  }}
/>

### `<PlanFooter />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<PlanAction />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CardAction component.',
      type: 'React.ComponentProps<typeof CardAction>',
    },
  }}
/>
```

## Prompt Input
Doc: https://ai-sdk.dev/elements/components/prompt-input
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/prompt-input.mdx

```mdx
## Props

### `<PromptInput />`

<TypeTable
  type={{
    onSubmit: {
      description: 'Handler called when the form is submitted with message text and files.',
      type: '(message: PromptInputMessage, event: FormEvent) => void',
    },
    accept: {
      description: 'File types to accept (e.g., "image/*"). Leave undefined for any.',
      type: 'string',
    },
    multiple: {
      description: 'Whether to allow multiple file selection.',
      type: 'boolean',
    },
    globalDrop: {
      description: 'When true, accepts file drops anywhere on the document.',
      type: 'boolean',
    },
    syncHiddenInput: {
      description: 'Render a hidden input with given name for native form posts.',
      type: 'boolean',
    },
    maxFiles: {
      description: 'Maximum number of files allowed.',
      type: 'number',
    },
    maxFileSize: {
      description: 'Maximum file size in bytes.',
      type: 'number',
    },
    onError: {
      description: 'Handler for file validation errors.',
      type: '(err: { code: "max_files" | "max_file_size" | "accept", message: string }) => void',
    },
    '...props': {
      description: 'Any other props are spread to the root form element.',
      type: 'React.HTMLAttributes<HTMLFormElement>',
    },
  }}
/>

### `<PromptInputTextarea />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying Textarea component.',
      type: 'React.ComponentProps<typeof Textarea>',
    },
  }}
/>

### `<PromptInputFooter />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the toolbar div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PromptInputTools />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the tools div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PromptInputButton />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<PromptInputSubmit />`

<TypeTable
  type={{
    status: {
      description: 'Current chat status to determine button icon (submitted, streaming, error).',
      type: 'ChatStatus',
    },
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<PromptInputSelect />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying Select component.',
      type: 'React.ComponentProps<typeof Select>',
    },
  }}
/>

### `<PromptInputSelectTrigger />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying SelectTrigger component.',
      type: 'React.ComponentProps<typeof SelectTrigger>',
    },
  }}
/>

### `<PromptInputSelectContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying SelectContent component.',
      type: 'React.ComponentProps<typeof SelectContent>',
    },
  }}
/>

### `<PromptInputSelectItem />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying SelectItem component.',
      type: 'React.ComponentProps<typeof SelectItem>',
    },
  }}
/>

### `<PromptInputSelectValue />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying SelectValue component.',
      type: 'React.ComponentProps<typeof SelectValue>',
    },
  }}
/>

### `<PromptInputBody />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the body div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### Attachments

Attachment components have been moved to a separate module. See the [Attachment](/elements/components/attachment) component documentation for details on `<Attachments />`, `<Attachment />`, `<AttachmentPreview />`, `<AttachmentInfo />`, and `<AttachmentRemove />`.

### `<PromptInputActionMenu />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying DropdownMenu component.',
      type: 'React.ComponentProps<typeof DropdownMenu>',
    },
  }}
/>

### `<PromptInputActionMenuTrigger />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<PromptInputActionMenuContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying DropdownMenuContent component.',
      type: 'React.ComponentProps<typeof DropdownMenuContent>',
    },
  }}
/>

### `<PromptInputActionMenuItem />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying DropdownMenuItem component.',
      type: 'React.ComponentProps<typeof DropdownMenuItem>',
    },
  }}
/>

### `<PromptInputActionAddAttachments />`

<TypeTable
  type={{
    label: {
      description: 'Label for the menu item.',
      type: 'string',
      default: '"Add photos or files"',
    },
    '...props': {
      description: 'Any other props are spread to the underlying DropdownMenuItem component.',
      type: 'React.ComponentProps<typeof DropdownMenuItem>',
    },
  }}
/>

### `<PromptInputProvider />`

<TypeTable
  type={{
    initialInput: {
      description: 'Initial text input value.',
      type: 'string',
    },
    children: {
      description: 'Child components that will have access to the provider context.',
      type: 'React.ReactNode',
    },
  }}
/>

Optional global provider that lifts PromptInput state outside of PromptInput. When used, it allows you to access and control the input state from anywhere within the provider tree. If not used, PromptInput stays fully self-managed.

### `<PromptInputHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props (except align) are spread to the InputGroupAddon component.',
      type: 'Omit<React.ComponentProps<typeof InputGroupAddon>, "align">',
    },
  }}
/>

### `<PromptInputHoverCard />`

<TypeTable
  type={{
    openDelay: {
      description: 'Delay in milliseconds before opening.',
      type: 'number',
      default: '0',
    },
    closeDelay: {
      description: 'Delay in milliseconds before closing.',
      type: 'number',
      default: '0',
    },
    '...props': {
      description: 'Any other props are spread to the HoverCard component.',
      type: 'React.ComponentProps<typeof HoverCard>',
    },
  }}
/>

### `<PromptInputHoverCardTrigger />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the HoverCardTrigger component.',
      type: 'React.ComponentProps<typeof HoverCardTrigger>',
    },
  }}
/>

### `<PromptInputHoverCardContent />`

<TypeTable
  type={{
    align: {
      description: 'Alignment of the hover card content.',
      type: '"start" | "center" | "end"',
      default: '"start"',
    },
    '...props': {
      description: 'Any other props are spread to the HoverCardContent component.',
      type: 'React.ComponentProps<typeof HoverCardContent>',
    },
  }}
/>

### `<PromptInputTabsList />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PromptInputTab />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PromptInputTabLabel />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the h3 element.',
      type: 'React.HTMLAttributes<HTMLHeadingElement>',
    },
  }}
/>

### `<PromptInputTabBody />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PromptInputTabItem />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<PromptInputCommand />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the Command component.',
      type: 'React.ComponentProps<typeof Command>',
    },
  }}
/>

### `<PromptInputCommandInput />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandInput component.',
      type: 'React.ComponentProps<typeof CommandInput>',
    },
  }}
/>

### `<PromptInputCommandList />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandList component.',
      type: 'React.ComponentProps<typeof CommandList>',
    },
  }}
/>

### `<PromptInputCommandEmpty />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandEmpty component.',
      type: 'React.ComponentProps<typeof CommandEmpty>',
    },
  }}
/>

### `<PromptInputCommandGroup />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandGroup component.',
      type: 'React.ComponentProps<typeof CommandGroup>',
    },
  }}
/>

### `<PromptInputCommandItem />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandItem component.',
      type: 'React.ComponentProps<typeof CommandItem>',
    },
  }}
/>

### `<PromptInputCommandSeparator />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandSeparator component.',
      type: 'React.ComponentProps<typeof CommandSeparator>',
    },
  }}
/>
```

## Queue
Doc: https://ai-sdk.dev/elements/components/queue
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/queue.mdx

```mdx
## Props

### `<Queue />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<QueueSection />`

<TypeTable
  type={{
    defaultOpen: {
      description: 'Whether the section is open by default.',
      type: 'boolean',
      default: 'true',
    },
    '...props': {
      description: 'Any other props are spread to the Collapsible component.',
      type: 'React.ComponentProps<typeof Collapsible>',
    },
  }}
/>

### `<QueueSectionTrigger />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the button element.',
      type: 'React.ComponentProps<"button">',
    },
  }}
/>

### `<QueueSectionLabel />`

<TypeTable
  type={{
    label: {
      description: 'The label text to display.',
      type: 'string',
    },
    count: {
      description: 'The count to display before the label.',
      type: 'number',
    },
    icon: {
      description: 'An optional icon to display before the count.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<QueueSectionContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CollapsibleContent component.',
      type: 'React.ComponentProps<typeof CollapsibleContent>',
    },
  }}
/>

### `<QueueList />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the ScrollArea component.',
      type: 'React.ComponentProps<typeof ScrollArea>',
    },
  }}
/>

### `<QueueItem />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the li element.',
      type: 'React.ComponentProps<"li">',
    },
  }}
/>

### `<QueueItemIndicator />`

<TypeTable
  type={{
    completed: {
      description: 'Whether the item is completed. Affects the indicator styling.',
      type: 'boolean',
      default: 'false',
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<QueueItemContent />`

<TypeTable
  type={{
    completed: {
      description: 'Whether the item is completed. Affects text styling with strikethrough and opacity.',
      type: 'boolean',
      default: 'false',
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<QueueItemDescription />`

<TypeTable
  type={{
    completed: {
      description: 'Whether the item is completed. Affects text styling.',
      type: 'boolean',
      default: 'false',
    },
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<QueueItemActions />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<QueueItemAction />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props (except variant and size) are spread to the Button component.',
      type: 'Omit<React.ComponentProps<typeof Button>, "variant" | "size">',
    },
  }}
/>

### `<QueueItemAttachment />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<QueueItemImage />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the img element.',
      type: 'React.ComponentProps<"img">',
    },
  }}
/>

### `<QueueItemFile />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>
```

## Reasoning
Doc: https://ai-sdk.dev/elements/components/reasoning
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/reasoning.mdx

```mdx
## Props

### `<Reasoning />`

<TypeTable
  type={{
    isStreaming: {
      description: 'Whether the reasoning is currently streaming (auto-opens and closes the panel).',
      type: 'boolean',
      default: 'false',
    },
    open: {
      description: 'Controlled open state.',
      type: 'boolean',
    },
    defaultOpen: {
      description: 'Default open state when uncontrolled.',
      type: 'boolean',
      default: 'true',
    },
    onOpenChange: {
      description: 'Callback when open state changes.',
      type: '(open: boolean) => void',
    },
    duration: {
      description: 'Duration in seconds to display (can be controlled externally).',
      type: 'number',
    },
    '...props': {
      description: 'Any other props are spread to the underlying Collapsible component.',
      type: 'React.ComponentProps<typeof Collapsible>',
    },
  }}
/>

### `<ReasoningTrigger />`

<TypeTable
  type={{
    getThinkingMessage: {
      description: 'Optional function to customize the thinking message. Receives isStreaming and duration parameters.',
      type: '(isStreaming: boolean, duration?: number) => ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the underlying CollapsibleTrigger component.',
      type: 'React.ComponentProps<typeof CollapsibleTrigger>',
    },
  }}
/>

### `<ReasoningContent />`

<TypeTable
  type={{
    children: {
      description: 'The reasoning text to display (rendered via Streamdown).',
      type: 'string',
      required: true,
    },
    '...props': {
      description: 'Any other props are spread to the underlying CollapsibleContent component.',
      type: 'React.ComponentProps<typeof CollapsibleContent>',
    },
  }}
/>
```

## Sandbox
Doc: https://ai-sdk.dev/elements/components/sandbox
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/sandbox.mdx

```mdx
## Props

### `<Sandbox />`

<TypeTable
  type={{
    "...props": {
      description:
        "Any other props are spread to the underlying Collapsible component.",
      type: "React.ComponentProps<typeof Collapsible>",
    },
  }}
/>

### `<SandboxHeader />`

<TypeTable
  type={{
    title: {
      description: "The title displayed in the header (e.g., filename).",
      type: "string",
      default: "undefined",
    },
    state: {
      description:
        "The current execution state, used to display the appropriate status badge.",
      type: 'ToolUIPart["state"]',
      required: true,
    },
    className: {
      description: "Additional CSS classes for the header.",
      type: "string",
    },
  }}
/>

### `<SandboxContent />`

<TypeTable
  type={{
    "...props": {
      description: "Any other props are spread to the CollapsibleContent.",
      type: "React.ComponentProps<typeof CollapsibleContent>",
    },
  }}
/>

### `<SandboxTabs />`

<TypeTable
  type={{
    "...props": {
      description:
        "Any other props are spread to the underlying Tabs component.",
      type: "React.ComponentProps<typeof Tabs>",
    },
  }}
/>

### `<SandboxTabsBar />`

<TypeTable
  type={{
    "...props": {
      description: "Any other props are spread to the container div.",
      type: "React.HTMLAttributes<HTMLDivElement>",
    },
  }}
/>

### `<SandboxTabsList />`

<TypeTable
  type={{
    "...props": {
      description:
        "Any other props are spread to the underlying TabsList component.",
      type: "React.ComponentProps<typeof TabsList>",
    },
  }}
/>

### `<SandboxTabsTrigger />`

<TypeTable
  type={{
    "...props": {
      description:
        "Any other props are spread to the underlying TabsTrigger component.",
      type: "React.ComponentProps<typeof TabsTrigger>",
    },
  }}
/>

### `<SandboxTabContent />`

<TypeTable
  type={{
    "...props": {
      description:
        "Any other props are spread to the underlying TabsContent component.",
      type: "React.ComponentProps<typeof TabsContent>",
    },
  }}
/>
```

## Schema Display
Doc: https://ai-sdk.dev/elements/components/schema-display
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/schema-display.mdx

```mdx
## Props

### `<SchemaDisplay />`

<TypeTable
  type={{
    method: {
      description: 'HTTP method.',
      type: '"GET" | "POST" | "PUT" | "PATCH" | "DELETE"',
    },
    path: {
      description: 'API endpoint path.',
      type: 'string',
    },
    description: {
      description: 'Endpoint description.',
      type: 'string',
    },
    parameters: {
      description: 'URL/query parameters.',
      type: 'SchemaParameter[]',
    },
    requestBody: {
      description: 'Request body properties.',
      type: 'SchemaProperty[]',
    },
    responseBody: {
      description: 'Response body properties.',
      type: 'SchemaProperty[]',
    },
  }}
/>

### `SchemaParameter`

```tsx
interface SchemaParameter {
  name: string;
  type: string;
  required?: boolean;
  description?: string;
  location?: "path" | "query" | "header";
}
```

### `SchemaProperty`

```tsx
interface SchemaProperty {
  name: string;
  type: string;
  required?: boolean;
  description?: string;
  properties?: SchemaProperty[]; // For objects
  items?: SchemaProperty;        // For arrays
}
```

### Subcomponents

- `SchemaDisplayHeader` - Header container
- `SchemaDisplayMethod` - Color-coded method badge
- `SchemaDisplayPath` - Path with highlighted parameters
- `SchemaDisplayDescription` - Description text
- `SchemaDisplayContent` - Content container
- `SchemaDisplayParameters` - Collapsible parameters section
- `SchemaDisplayParameter` - Individual parameter
- `SchemaDisplayRequest` - Collapsible request body
- `SchemaDisplayResponse` - Collapsible response body
- `SchemaDisplayProperty` - Schema property (recursive)
- `SchemaDisplayExample` - Code example block
```

## Shimmer
Doc: https://ai-sdk.dev/elements/components/shimmer
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/shimmer.mdx

```mdx
## Props

### `<Shimmer />`

<TypeTable
  type={{
    children: {
      description: 'The text content to apply the shimmer effect to.',
      type: 'string',
    },
    as: {
      description: 'The HTML element or React component to render.',
      type: 'ElementType',
      default: '"p"',
    },
    className: {
      description: 'Additional CSS classes to apply to the component.',
      type: 'string',
    },
    duration: {
      description: 'The duration of the shimmer animation in seconds.',
      type: 'number',
      default: '2',
    },
    spread: {
      description: 'The spread multiplier for the shimmer gradient, multiplied by text length.',
      type: 'number',
      default: '2',
    },
  }}
/>
```

## Snippet
Doc: https://ai-sdk.dev/elements/components/snippet
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/snippet.mdx

```mdx
## Props

### `<Snippet />`

<TypeTable
  type={{
    code: {
      description: 'The code content to display.',
      type: 'string',
      required: true,
    },
    children: {
      description: 'Child elements like SnippetAddon, SnippetInput, etc.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the InputGroup component.',
      type: 'React.ComponentProps<typeof InputGroup>',
    },
  }}
/>

### `<SnippetAddon />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the InputGroupAddon component.',
      type: 'React.ComponentProps<typeof InputGroupAddon>',
    },
  }}
/>

### `<SnippetText />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the InputGroupText component.',
      type: 'React.ComponentProps<typeof InputGroupText>',
    },
  }}
/>

### `<SnippetInput />`

<TypeTable
  type={{
    '...props': {
      description: 'Spread to the InputGroupInput component. Value and readOnly are set automatically.',
      type: 'Omit<React.ComponentProps<typeof InputGroupInput>, "readOnly" | "value">',
    },
  }}
/>

### `<SnippetCopyButton />`

<TypeTable
  type={{
    onCopy: {
      description: 'Callback fired after a successful copy.',
      type: '() => void',
    },
    onError: {
      description: 'Callback fired if copying fails.',
      type: '(error: Error) => void',
    },
    timeout: {
      description: 'How long to show the copied state (ms).',
      type: 'number',
      default: '2000',
    },
    children: {
      description: 'Custom button content.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Spread to the InputGroupButton component.',
      type: 'React.ComponentProps<typeof InputGroupButton>',
    },
  }}
/>
```

## Sources
Doc: https://ai-sdk.dev/elements/components/sources
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/sources.mdx

```mdx
## Props

### `<Sources />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<SourcesTrigger />`

<TypeTable
  type={{
    count: {
      description: 'The number of sources to display in the trigger.',
      type: 'number',
      required: true,
    },
    '...props': {
      description: 'Any other props are spread to the CollapsibleTrigger component.',
      type: 'React.ComponentProps<typeof CollapsibleTrigger>',
    },
  }}
/>

### `<SourcesContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the content container.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<Source />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the anchor element.',
      type: 'React.AnchorHTMLAttributes<HTMLAnchorElement>',
    },
  }}
/>
```

## Speech Input
Doc: https://ai-sdk.dev/elements/components/speech-input
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(voice)/speech-input.mdx

```mdx
## Props

### `<SpeechInput />`

The component extends the shadcn/ui Button component, so all Button props are available.

<TypeTable
  type={{
    onTranscriptionChange: {
      description: 'Callback fired when final transcription text is available. Only fires for completed phrases, not interim results.',
      type: '(text: string) => void',
      optional: true,
    },
    onAudioRecorded: {
      description: 'Callback for MediaRecorder fallback. Required for Firefox/Safari support. Receives recorded audio blob and should return transcribed text from an external service (e.g., OpenAI Whisper).',
      type: '(audioBlob: Blob) => Promise<string>',
      optional: true,
    },
    lang: {
      description: 'Language for speech recognition.',
      type: 'string',
      default: '"en-US"',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the Button component, including variant, size, disabled, etc.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>
```

## Stack Trace
Doc: https://ai-sdk.dev/elements/components/stack-trace
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/stack-trace.mdx

```mdx
## Props

### `<StackTrace />`

<TypeTable
  type={{
    trace: {
      description: 'The raw stack trace string to parse and display.',
      type: 'string',
    },
    open: {
      description: 'Controlled open state.',
      type: 'boolean',
    },
    defaultOpen: {
      description: 'Whether the content is expanded by default.',
      type: 'boolean',
      default: 'false',
    },
    onOpenChange: {
      description: 'Callback when open state changes.',
      type: '(open: boolean) => void',
    },
    onFilePathClick: {
      description: 'Callback when a file path is clicked. Receives the file path, line number, and column number.',
      type: '(path: string, line?: number, column?: number) => void',
    },
    children: {
      description: 'Child elements (StackTraceHeader, StackTraceContent, etc.).',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<StackTraceHeader />`

<TypeTable
  type={{
    children: {
      description: 'Header content (typically StackTraceError and StackTraceActions).',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the CollapsibleTrigger.',
      type: 'React.ComponentProps<typeof CollapsibleTrigger>',
    },
  }}
/>

### `<StackTraceError />`

<TypeTable
  type={{
    children: {
      description: 'Error content (typically StackTraceErrorType and StackTraceErrorMessage).',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<StackTraceErrorType />`

<TypeTable
  type={{
    children: {
      description: 'Custom content. Defaults to the parsed error type (e.g., "TypeError").',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<StackTraceErrorMessage />`

<TypeTable
  type={{
    children: {
      description: 'Custom content. Defaults to the parsed error message.',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<StackTraceActions />`

<TypeTable
  type={{
    children: {
      description: 'Action buttons (typically StackTraceCopyButton and StackTraceExpandButton).',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<StackTraceCopyButton />`

<TypeTable
  type={{
    onCopy: {
      description: 'Callback fired after a successful copy.',
      type: '() => void',
    },
    onError: {
      description: 'Callback fired if copying fails.',
      type: '(error: Error) => void',
    },
    timeout: {
      description: 'How long to show the copied state (ms).',
      type: 'number',
      default: '2000',
    },
    children: {
      description: 'Custom content for the button. Defaults to copy/check icons.',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<StackTraceExpandButton />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<StackTraceContent />`

<TypeTable
  type={{
    maxHeight: {
      description: 'Maximum height of the content area. Enables scrolling when content exceeds this height.',
      type: 'number',
      default: '400',
    },
    children: {
      description: 'Content to display (typically StackTraceFrames).',
      type: 'React.ReactNode',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the CollapsibleContent.',
      type: 'React.ComponentProps<typeof CollapsibleContent>',
    },
  }}
/>

### `<StackTraceFrames />`

<TypeTable
  type={{
    showInternalFrames: {
      description: 'Whether to show internal frames (node_modules, node: paths).',
      type: 'boolean',
      default: 'true',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the container div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>
```

## Suggestion
Doc: https://ai-sdk.dev/elements/components/suggestion
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/suggestion.mdx

```mdx
## Props

### `<Suggestions />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying ScrollArea component.',
      type: 'React.ComponentProps<typeof ScrollArea>',
    },
  }}
/>

### `<Suggestion />`

<TypeTable
  type={{
    suggestion: {
      description: 'The suggestion string to display and emit on click.',
      type: 'string',
      required: true,
    },
    onClick: {
      description: 'Callback fired when the suggestion is clicked.',
      type: '(suggestion: string) => void',
    },
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'Omit<React.ComponentProps<typeof Button>, "onClick">',
    },
  }}
/>
```

## Task
Doc: https://ai-sdk.dev/elements/components/task
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(chatbot)/task.mdx

```mdx
## Props

### `<Task />`

<TypeTable
  type={{
    defaultOpen: {
      description: 'Whether the task is open by default.',
      type: 'boolean',
      default: 'true',
    },
    '...props': {
      description: 'Any other props are spread to the root Collapsible component.',
      type: 'React.ComponentProps<typeof Collapsible>',
    },
  }}
/>

### `<TaskTrigger />`

<TypeTable
  type={{
    title: {
      description: 'The title of the task that will be displayed in the trigger.',
      type: 'string',
      required: true,
    },
    '...props': {
      description: 'Any other props are spread to the CollapsibleTrigger component.',
      type: 'React.ComponentProps<typeof CollapsibleTrigger>',
    },
  }}
/>

### `<TaskContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CollapsibleContent component.',
      type: 'React.ComponentProps<typeof CollapsibleContent>',
    },
  }}
/>

### `<TaskItem />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<TaskItemFile />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying div.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>
```

## Terminal
Doc: https://ai-sdk.dev/elements/components/terminal
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/terminal.mdx

```mdx
## Props

### `<Terminal />`

<TypeTable
  type={{
    output: {
      description: 'Terminal output text (supports ANSI codes).',
      type: 'string',
    },
    isStreaming: {
      description: 'Show streaming indicator.',
      type: 'boolean',
      default: 'false',
    },
    autoScroll: {
      description: 'Auto-scroll to bottom on new output.',
      type: 'boolean',
      default: 'true',
    },
    onClear: {
      description: 'Callback to clear output (enables clear button).',
      type: '() => void',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<TerminalCopyButton />`

<TypeTable
  type={{
    onCopy: {
      description: 'Callback after successful copy.',
      type: '() => void',
    },
    onError: {
      description: 'Callback if copying fails.',
      type: '(error: Error) => void',
    },
    timeout: {
      description: 'Duration to show copied state (ms).',
      type: 'number',
      default: '2000',
    },
  }}
/>

### `<TerminalHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TerminalTitle />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TerminalStatus />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TerminalActions />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TerminalClearButton />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<TerminalContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>
```

## Test Results
Doc: https://ai-sdk.dev/elements/components/test-results
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/test-results.mdx

```mdx
## Props

### `<TestResults />`

<TypeTable
  type={{
    summary: {
      description: 'Test results summary.',
      type: '{ passed, failed, skipped, total, duration? }',
    },
    className: {
      description: 'Additional CSS classes.',
      type: 'string',
    },
  }}
/>

### `<TestSuite />`

<TypeTable
  type={{
    name: {
      description: 'Suite name.',
      type: 'string',
    },
    status: {
      description: 'Overall suite status.',
      type: '"passed" | "failed" | "skipped" | "running"',
    },
    defaultOpen: {
      description: 'Initially expanded.',
      type: 'boolean',
    },
  }}
/>

### `<Test />`

<TypeTable
  type={{
    name: {
      description: 'Test name.',
      type: 'string',
    },
    status: {
      description: 'Test status.',
      type: '"passed" | "failed" | "skipped" | "running"',
    },
    duration: {
      description: 'Test duration in ms.',
      type: 'number',
    },
  }}
/>

### `<TestResultsHeader />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TestResultsSummary />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TestResultsDuration />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<TestResultsProgress />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TestResultsContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TestSuiteName />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CollapsibleTrigger component.',
      type: 'React.ComponentProps<typeof CollapsibleTrigger>',
    },
  }}
/>

### `<TestSuiteStats />`

<TypeTable
  type={{
    passed: {
      description: 'Number of passed tests.',
      type: 'number',
      default: '0',
    },
    failed: {
      description: 'Number of failed tests.',
      type: 'number',
      default: '0',
    },
    skipped: {
      description: 'Number of skipped tests.',
      type: 'number',
      default: '0',
    },
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TestSuiteContent />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CollapsibleContent component.',
      type: 'React.ComponentProps<typeof CollapsibleContent>',
    },
  }}
/>

### `<TestStatus />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<TestName />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<TestDuration />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.HTMLAttributes<HTMLSpanElement>',
    },
  }}
/>

### `<TestError />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<TestErrorMessage />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the p element.',
      type: 'React.HTMLAttributes<HTMLParagraphElement>',
    },
  }}
/>

### `<TestErrorStack />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the pre element.',
      type: 'React.HTMLAttributes<HTMLPreElement>',
    },
  }}
/>
```

## Toolbar
Doc: https://ai-sdk.dev/elements/components/toolbar
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(workflow)/toolbar.mdx

```mdx
## Props

### `<Toolbar />`

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply to the toolbar.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props from @xyflow/react NodeToolbar component (position, offset, isVisible, etc.).',
      type: 'ComponentProps<typeof NodeToolbar>',
    },
  }}
/>
```

## Transcription
Doc: https://ai-sdk.dev/elements/components/transcription
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(voice)/transcription.mdx

```mdx
## Props

### `<Transcription />`

Root component that provides context and manages transcript state. Uses render props pattern for rendering segments.

<TypeTable
  type={{
    segments: {
      description: 'Array of transcription segments from AI SDK transcribe() function.',
      type: 'TranscriptionSegment[]',
    },
    currentTime: {
      description: 'Current playback time in seconds (controlled).',
      type: 'number',
      optional: true,
      default: '0',
    },
    onSeek: {
      description: 'Callback fired when a segment is clicked or when currentTime changes.',
      type: '(time: number) => void',
      optional: true,
    },
    children: {
      description: 'Render function that receives each segment and its index.',
      type: '(segment: TranscriptionSegment, index: number) => ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the root div element.',
      type: 'Omit<React.ComponentProps<"div">, "children">',
    },
  }}
/>

### `<TranscriptionSegment />`

Individual segment button with automatic state styling and click-to-seek functionality.

<TypeTable
  type={{
    segment: {
      description: 'The transcription segment data.',
      type: 'TranscriptionSegment',
    },
    index: {
      description: 'The segment index.',
      type: 'number',
    },
    '...props': {
      description: 'Any other props are spread to the button element.',
      type: 'React.ComponentProps<"button">',
    },
  }}
/>
```

## Voice Selector
Doc: https://ai-sdk.dev/elements/components/voice-selector
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(voice)/voice-selector.mdx

```mdx
## Props

### `<VoiceSelector />`

Root Dialog component that provides context for all child components. Manages both voice selection and dialog open states.

<TypeTable
  type={{
    value: {
      description: 'The selected voice ID (controlled).',
      type: 'string',
      optional: true,
    },
    defaultValue: {
      description: 'The default selected voice ID (uncontrolled).',
      type: 'string',
      optional: true,
    },
    onValueChange: {
      description: 'Callback fired when the selected voice changes.',
      type: '(value: string | undefined) => void',
      optional: true,
    },
    defaultOpen: {
      description: 'The default open state (uncontrolled).',
      type: 'boolean',
      optional: true,
      default: 'false',
    },
    open: {
      description: 'The open state (controlled).',
      type: 'boolean',
      optional: true,
    },
    onOpenChange: {
      description: 'Callback fired when the open state changes.',
      type: '(open: boolean) => void',
      optional: true,
    },
    modal: {
      description: 'Whether the dialog is modal (blocks interaction with the rest of the page).',
      type: 'boolean',
      optional: true,
      default: 'true',
    },
    '...props': {
      description: 'Any other props are spread to the Dialog component.',
      type: 'React.ComponentProps<typeof Dialog>',
    },
  }}
/>

### `<VoiceSelectorTrigger />`

Button or element that opens the voice selector dialog.

<TypeTable
  type={{
    asChild: {
      description: 'Change the default rendered element for the one passed as a child, merging their props and behavior.',
      type: 'boolean',
      optional: true,
      default: 'false',
    },
    '...props': {
      description: 'Any other props are spread to the DialogTrigger component.',
      type: 'React.ComponentProps<typeof DialogTrigger>',
    },
  }}
/>

### `<VoiceSelectorContent />`

Container for the Command component and voice list, rendered inside the dialog.

<TypeTable
  type={{
    title: {
      description: 'The title for screen readers. Hidden visually but accessible to assistive technologies.',
      type: 'ReactNode',
      optional: true,
      default: '"Voice Selector"',
    },
    className: {
      description: 'Additional CSS classes to apply to the dialog content.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the DialogContent component.',
      type: 'React.ComponentProps<typeof DialogContent>',
    },
  }}
/>

### `<VoiceSelectorDialog />`

Alternative dialog implementation using CommandDialog for a full-screen command palette style.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandDialog component.',
      type: 'React.ComponentProps<typeof CommandDialog>',
    },
  }}
/>

### `<VoiceSelectorInput />`

Search input for filtering voices.

<TypeTable
  type={{
    placeholder: {
      description: 'Placeholder text for the search input.',
      type: 'string',
      optional: true,
    },
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the CommandInput component.',
      type: 'React.ComponentProps<typeof CommandInput>',
    },
  }}
/>

### `<VoiceSelectorList />`

Scrollable container for voice items and groups.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandList component.',
      type: 'React.ComponentProps<typeof CommandList>',
    },
  }}
/>

### `<VoiceSelectorEmpty />`

Message shown when no voices match the search query.

<TypeTable
  type={{
    children: {
      description: 'The message to display.',
      type: 'ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the CommandEmpty component.',
      type: 'React.ComponentProps<typeof CommandEmpty>',
    },
  }}
/>

### `<VoiceSelectorGroup />`

Groups related voices together with an optional heading.

<TypeTable
  type={{
    heading: {
      description: 'The heading text for the group.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the CommandGroup component.',
      type: 'React.ComponentProps<typeof CommandGroup>',
    },
  }}
/>

### `<VoiceSelectorItem />`

Selectable item representing a voice.

<TypeTable
  type={{
    value: {
      description: 'The unique identifier for this voice. Used for search filtering.',
      type: 'string',
    },
    onSelect: {
      description: 'Callback fired when the voice is selected.',
      type: '(value: string) => void',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the CommandItem component.',
      type: 'React.ComponentProps<typeof CommandItem>',
    },
  }}
/>

### `<VoiceSelectorSeparator />`

Visual separator between voice groups.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandSeparator component.',
      type: 'React.ComponentProps<typeof CommandSeparator>',
    },
  }}
/>

### `<VoiceSelectorName />`

Displays the voice name with proper styling.

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<VoiceSelectorGender />`

Displays the voice gender metadata with icons from Lucide. Supports multiple gender identities with corresponding icons.

<TypeTable
  type={{
    value: {
      description: 'The gender value that determines which icon to display. Supported values: "male" (Mars), "female" (Venus), "transgender", "androgyne", "non-binary", "intersex". Defaults to a small circle if no value matches.',
      type: '"male" | "female" | "transgender" | "androgyne" | "non-binary" | "intersex"',
      optional: true,
    },
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    children: {
      description: 'Override the icon with custom content.',
      type: 'ReactNode',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<VoiceSelectorAccent />`

Displays the voice accent metadata with emoji flags representing different countries/regions.

<TypeTable
  type={{
    value: {
      description: 'The accent value that determines which flag emoji to display. Supports 27 different accents including: "american" 🇺🇸, "british" 🇬🇧, "australian" 🇦🇺, "canadian" 🇨🇦, "irish" 🇮🇪, "scottish" 🏴󠁧󠁢󠁳󠁣󠁴󠁿, "indian" 🇮🇳, "south-african" 🇿🇦, "new-zealand" 🇳🇿, "spanish" 🇪🇸, "french" 🇫🇷, "german" 🇩🇪, "italian" 🇮🇹, "portuguese" 🇵🇹, "brazilian" 🇧🇷, "mexican" 🇲🇽, "argentinian" 🇦🇷, "japanese" 🇯🇵, "chinese" 🇨🇳, "korean" 🇰🇷, "russian" 🇷🇺, "arabic" 🇸🇦, "dutch" 🇳🇱, "swedish" 🇸🇪, "norwegian" 🇳🇴, "danish" 🇩🇰, "finnish" 🇫🇮, "polish" 🇵🇱, "turkish" 🇹🇷, "greek" 🇬🇷. Also accepts any custom string value.',
      type: '"american" | "british" | "australian" | "canadian" | "irish" | "scottish" | "indian" | "south-african" | "new-zealand" | "spanish" | "french" | "german" | "italian" | "portuguese" | "brazilian" | "mexican" | "argentinian" | "japanese" | "chinese" | "korean" | "russian" | "arabic" | "dutch" | "swedish" | "norwegian" | "danish" | "finnish" | "polish" | "turkish" | "greek" | string',
      optional: true,
    },
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    children: {
      description: 'Override the flag emoji with custom content.',
      type: 'ReactNode',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<VoiceSelectorAge />`

Displays the voice age metadata with muted styling and tabular numbers for consistent alignment.

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<VoiceSelectorDescription />`

Displays a description for the voice with muted styling.

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<VoiceSelectorAttributes />`

Container for grouping voice attributes (gender, accent, age) together. Use with `VoiceSelectorBullet` for separation.

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the div element.',
      type: 'React.ComponentProps<"div">',
    },
  }}
/>

### `<VoiceSelectorBullet />`

Displays a bullet separator (•) between voice attributes. Hidden from screen readers via `aria-hidden`.

<TypeTable
  type={{
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the span element.',
      type: 'React.ComponentProps<"span">',
    },
  }}
/>

### `<VoiceSelectorShortcut />`

Displays keyboard shortcuts for voice items.

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the CommandShortcut component.',
      type: 'React.ComponentProps<typeof CommandShortcut>',
    },
  }}
/>

### `<VoiceSelectorPreview />`

A button that allows users to preview/play a voice sample before selecting it. Shows play, pause, or loading icons based on state.

<TypeTable
  type={{
    playing: {
      description: 'Whether the voice is currently playing. Shows pause icon when true.',
      type: 'boolean',
      optional: true,
    },
    loading: {
      description: 'Whether the voice preview is loading. Shows loading spinner and disables the button.',
      type: 'boolean',
      optional: true,
    },
    onPlay: {
      description: 'Callback fired when the preview button is clicked.',
      type: '() => void',
      optional: true,
    },
    className: {
      description: 'Additional CSS classes to apply.',
      type: 'string',
      optional: true,
    },
    '...props': {
      description: 'Any other props are spread to the button element.',
      type: 'Omit<React.ComponentProps<"button">, "children">',
    },
  }}
/>
```

## Web Preview
Doc: https://ai-sdk.dev/elements/components/web-preview
Source: https://raw.githubusercontent.com/vercel/ai-elements/main/apps/docs/content/docs/components/(code)/web-preview.mdx

```mdx
## Props

### `<WebPreview />`

<TypeTable
  type={{
    defaultUrl: {
      description: 'The initial URL to load in the preview.',
      type: 'string',
      default: '""',
    },
    onUrlChange: {
      description: 'Callback fired when the URL changes.',
      type: '(url: string) => void',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<WebPreviewNavigation />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the navigation container.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>

### `<WebPreviewNavigationButton />`

<TypeTable
  type={{
    tooltip: {
      description: 'Tooltip text to display on hover.',
      type: 'string',
    },
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Button component.',
      type: 'React.ComponentProps<typeof Button>',
    },
  }}
/>

### `<WebPreviewUrl />`

<TypeTable
  type={{
    '...props': {
      description: 'Any other props are spread to the underlying shadcn/ui Input component.',
      type: 'React.ComponentProps<typeof Input>',
    },
  }}
/>

### `<WebPreviewBody />`

<TypeTable
  type={{
    loading: {
      description: 'Optional loading indicator to display over the preview.',
      type: 'React.ReactNode',
    },
    '...props': {
      description: 'Any other props are spread to the underlying iframe.',
      type: 'React.IframeHTMLAttributes<HTMLIFrameElement>',
    },
  }}
/>

### `<WebPreviewConsole />`

<TypeTable
  type={{
    logs: {
      description: 'Console log entries to display in the console panel.',
      type: 'Array<{ level: "log" | "warn" | "error"; message: string; timestamp: Date }>',
    },
    '...props': {
      description: 'Any other props are spread to the root div.',
      type: 'React.HTMLAttributes<HTMLDivElement>',
    },
  }}
/>
```

