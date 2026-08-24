# DESIGN.md

> Visual design system for the browser web UI and the generated report
> documents. Adopted 2026-08-25 (branch ui-experiment), replacing the earlier
> indigo-tinted neutral system. The reference is the "clinical blueprint on
> frosted paper" style (Refero style 0fd67ec5): achromatic by default, radius
> as hierarchy, whisper-quiet elevation. Lineage: Vercel, Linear, Radix.
>
> This file does not govern the graph, the MCP server, the pipeline, or any
> backend or agent tooling. Agent working rules live in @AGENTS.md; human
> context lives in @USER.md; stack, schema, and domain rules live in
> @docs/architecture.md.
>
> Formatting rule for this file and all edits to it: never use em dashes, and
> never use en dashes as a sentence break. Use commas, colons, parentheses, or
> separate sentences.

## The three principles

1. **Achromatic by default. Color is absence, not expression.** The entire
   interface is a pure neutral ramp. Exactly one chromatic accent exists,
   ember (the destructive red), and it is reserved for destructive actions
   and genuine error states. This is not only aesthetics: it structurally
   enforces the honesty rule that color must never grade content. There is
   no green, no amber, no traffic light anywhere. A calibrated status is a
   state, not a grade, and the palette makes the opposite impossible.
2. **Radius defines hierarchy.** 18px on interactive elements (buttons,
   inputs, badges, chips), 24px on containers (cards, dialogs, notices),
   10px on small nested elements. Never square corners on components.
3. **Elevation is whisper-quiet.** A 1px hairline border plus the default
   small shadow stack. Layering comes from the three-tone surface stack,
   never from heavy shadows.

## Stack (web UI)

- Framework: Next.js (App Router) + React + TypeScript
- Styling: Tailwind CSS v4 (CSS-first config via `@theme inline` in
  `globals.css`, no `tailwind.config.ts`)
- Components: shadcn/ui (new-york style, neutral base)
- Icons: Lucide React
- Fonts: Geist (sans) + Geist Mono (mono) via `next/font/google`, OpenType
  features ss01 and cv11 enabled on the body
- Dark mode: prefers-color-scheme media query (documented deviation from
  next-themes; no client JS needed for the read-only pages). The dark scheme
  is the same achromatic system inverted, derived, never a second identity.
- Utilities: `cn()` from `@/lib/utils` (clsx + tailwind-merge)

The generated report documents (src/tere4ai/report/) implement the same
system with system font stacks (they are self-contained files and load no
webfonts) and one documented exception: byte-exact legal quotes are set in a
serif. That serif is an honesty device separating the law's words from
TERE4AI's words, not decoration, and it stays.

## Colors

All values oklch, chroma 0 everywhere except ember. Defined in
`globals.css` and bridged via `@theme inline`.

### The neutral ramp (light)

| Token | Value | Reference | Usage |
| --- | --- | --- | --- |
| background (paper) | oklch(1 0 0) | #ffffff | Page and card ground |
| sidebar (surface-alt) | oklch(0.985 0 0) | #fafafa | Sidebar, subtle variant |
| secondary / muted (canvas) | oklch(0.97 0 0) | #f5f5f5 | Muted fills, secondary buttons, inputs at rest |
| border (hairline) | oklch(0.922 0 0) | #e5e5e5 | Every border, divider, outline |
| muted-foreground | oklch(0.505 0 0) | darker than #737373 | Helper text, captions, placeholders |
| foreground / primary (ink) | oklch(0.145 0 0) | #0a0a0a | Text, filled buttons, icons |
| destructive (ember) | oklch(0.577 0.245 27.325) | #e7000b family | Destructive and error ONLY |

Documented deviation: muted-foreground is one step darker than the reference
#737373 so helper text passes WCAG 4.5:1 on the canvas surface. Never lighten
it back.

### Dark (derived, inverted ramp)

background oklch(0.145 0 0), card and sidebar oklch(0.185 0 0), muted
oklch(0.235 0 0), border oklch(1 0 0 / 12%), muted-foreground oklch(0.75 0
0), foreground and primary oklch(0.985 0 0), destructive oklch(0.704 0.191
22.216). Same rules, same bans.

### Data ramp (chart-1 to chart-5)

An achromatic tone ramp: light 0.145 / 0.37 / 0.556 / 0.72 / 0.87, inverted
in dark. Layers and series differ by tone, never hue, so every visualization
survives grayscale unchanged. The evidence subgraph's layer legend reads off
this ramp.

### Bans (palette)

- No chromatic color besides ember, and ember never decorates: destructive
  actions and genuine error states only. A prohibited classification is a
  status, not an error; it renders in ink like every other status.
- No green success anything. No amber warnings. No gradients, no colored
  shadows, no gradient text (`bg-clip-text` with a gradient is banned).
- No color-graded statuses. All seven calibrated vocabulary values share one
  neutral badge; `requires_human_review` alone may carry a dashed border,
  which flags pending human action, not valence.

## Typography

One family carries everything: Geist for UI, Geist Mono for code, ids, and
data. Weights 400, 500, 600 only. Never 700.

| Role | Size | Weight | Notes |
| --- | --- | --- | --- |
| Caption / labels | 12px (text-xs) | 500 | may letter-space up to 0.05em |
| Body / controls | 14px (text-sm) | 400 | the default |
| Body large | 16px (text-base) | 400 | |
| Subheading | 18px (text-lg) | 400 | |
| Card / section titles | 20px (text-xl) | 600 | |
| Page titles | 24 to 30px (text-2xl / text-3xl) | 600 | tracking-tight |
| Display | 36 to 48px | 500 to 600 | tracking to -0.05em, never tighter |

Body text never below 14px. Letter spacing stays within -0.05em to 0.05em.
Line length for prose capped at 65 to 75ch; tables may run denser.

## Radius

| Token | Value | Usage |
| --- | --- | --- |
| rounded-sm | 10px | nested elements, small marks |
| rounded-md | 18px | buttons, inputs, textareas, chips |
| rounded-lg / rounded-xl | 24px | cards, dialogs, notices |
| rounded-full | pill | badges (visually equivalent to 18px at badge height) |

Never square corners on components. Never values outside this scale.

## Elevation and borders

- Every card carries a 1px hairline border. Non-negotiable.
- Shadows: Tailwind `shadow-sm` on cards, `shadow-md` on popovers and
  dropdowns, `shadow-lg` on dialogs. Nothing heavier. Filled buttons carry
  no shadow; they rely on tonal contrast (ink on paper).
- Layering without dividers: paper cards on canvas ground, sidebar one
  tonal step off (surface-alt). The three-tone stack does the separating.

## Components

### Buttons

- Primary: ink background, near-white text, radius 18px, weight 500, no
  shadow. The dark inversion is the only primary treatment.
- Secondary: canvas background, ink text, no border.
- Outline: transparent, ink text, 1px hairline border.
- Destructive: ember, reserved for destructive actions.
- Sizes as shadcn defaults (h-8 / h-9 / h-10), 14px labels.

### Badges and chips

One neutral style: 1px hairline border, canvas or transparent fill, ink
text, 12px weight 500, pill radius. Status badges add nothing but the
dashed-border variant for `requires_human_review`. Mono face for ids,
spans, and code locations.

### Inputs

Canvas background at rest, ink text, radius 18px, placeholder in
muted-foreground, 1px hairline border on focus plus the global focus
outline. Responsive font `text-base md:text-sm`.

### Cards

Paper background, radius 24px, hairline border, `shadow-sm`, padding 20px
(p-5) as the default. Never nested cards.

### Stat blocks

Typographic, no chrome: 12px weight-500 muted label, 26 to 30px weight-600
tabular-nums value, muted qualifier line. No cards around single numbers
unless the block is interactive.

### Sidebar

surface-alt background, full height, ink links, active item on canvas fill.
No divider against the page; the tonal step is the separation.

## Focus and interaction

- Focus ring: 2px ink outline at 70% via color-mix, offset 2px. Documented
  deviation from the reference's 1px hairline focus: visibility is an
  accessibility requirement and outranks the aesthetic.
- Disabled: `disabled:pointer-events-none disabled:opacity-50`.
- Transitions 150 to 250ms, ease-out. Motion conveys state, never
  decoration. `prefers-reduced-motion` collapses all motion (global rule in
  globals.css).

## Honesty furniture (unchanged by any restyle)

These are load-bearing and survive every redesign:

- The non-legal-advice notice on every page and both ends of every report.
- The HLEG "LLM-generated, not expert-validated" caveat adjacent to every
  alignment rendering.
- The seven-value calibrated status vocabulary rendered as states, never
  grades: one badge style, no icons, no color coding.
- Judge verdicts with model and run id on generated content.
- Span ids, snapshot files, byte offsets, and checksums as the traceability
  credentials; byte-exact quotes visually marked as quotes (serif in the
  report).
- The trace-is-a-claim sentence inside every traceability matrix rendering.

## Report documents (src/tere4ai/report/)

Same tokens translated to self-contained CSS with system font stacks:
paper/canvas/surface-alt ramp, ink, hairline, ember reserved for document
failures (checksum mismatch, degraded envelope), never for statuses or the
risk category. Radius 18px on chips and badges, 24px on notices and figure
blocks. The serif is reserved for byte-exact quotes of the frozen legal
snapshot, with the credential caption beneath. Print collapses to
near-monochrome by construction; the grayscale test (print with
`filter: grayscale(1)`, nothing may lose meaning) is a release gate.

## Branding

Logo: an ink "T4" mark on a 10 percent ink tint, radius 10px, next to
"TERE4AI v2" in solid ink at weight 600. No gradient text anywhere.
