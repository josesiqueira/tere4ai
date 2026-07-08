# DESIGN.md

> Visual design system for the browser web UI. The UI ships from Phase 1 as a
> thin, read-only demo interface over the service layer, and later grows into
> the hosted SaaS UI (Phase 2+). This file does not govern the graph, the MCP
> server, the pipeline, or any backend or agent tooling. Agent working rules
> live in @AGENTS.md; human context lives in @USER.md; stack, schema, and
> domain rules live in @docs/architecture.md.
>
> Formatting rule for this file and all edits to it: never use em dashes, and
> never use en dashes as a sentence break. Use commas, colons, parentheses, or
> separate sentences.

All new web UI components and pages must follow these tokens, patterns, and
conventions.

## Stack (web UI)

- Framework: Next.js (App Router) + React + TypeScript
- Styling: Tailwind CSS v4 (CSS-first config via `@theme inline` in `globals.css`, no `tailwind.config.ts`)
- Components: shadcn/ui (new-york style, neutral base)
- Icons: Lucide React
- Fonts: Geist (sans) + Geist Mono (mono) via `next/font/google`
- Dark mode: next-themes (class-based, system default)
- Utilities: `cn()` from `@/lib/utils` (clsx + tailwind-merge)

Note: this is the web frontend stack. It is separate from the backend core
stack defined in @docs/architecture.md, and there is no conflict between them.

## Colors

All values use the oklch color space, defined as CSS custom properties in
`globals.css` and bridged to Tailwind via `@theme inline`.

### Semantic tokens

| Token | Light | Dark | Usage |
| --- | --- | --- | --- |
| background | oklch(1 0 0) | oklch(0.141 0.005 285.823) | Page background |
| foreground | oklch(0.141 0.005 285.823) | oklch(0.985 0 0) | Primary text |
| primary | oklch(0.21 0.034 270) | oklch(0.92 0.02 270) | Buttons, links, accents |
| primary-foreground | oklch(0.985 0 0) | oklch(0.21 0.006 285.885) | Text on primary |
| secondary | oklch(0.967 0.001 286.375) | oklch(0.274 0.006 286.033) | Secondary buttons, subtle bg |
| secondary-foreground | oklch(0.21 0.006 285.885) | oklch(0.985 0 0) | Text on secondary |
| muted | oklch(0.967 0.001 286.375) | oklch(0.274 0.006 286.033) | Subdued backgrounds |
| muted-foreground | oklch(0.552 0.016 285.938) | oklch(0.705 0.015 286.067) | Subdued text, placeholders |
| accent | oklch(0.96 0.012 270) | oklch(0.28 0.018 270) | Hover backgrounds, highlights |
| accent-foreground | oklch(0.21 0.006 285.885) | oklch(0.985 0 0) | Text on accent |
| destructive | oklch(0.577 0.245 27.325) | oklch(0.704 0.191 22.216) | Error states, delete actions |
| card | oklch(1 0 0) | oklch(0.21 0.006 285.885) | Card backgrounds |
| card-foreground | oklch(0.141 0.005 285.823) | oklch(0.985 0 0) | Card text |
| popover | oklch(1 0 0) | oklch(0.21 0.006 285.885) | Popover / dropdown bg |
| popover-foreground | oklch(0.141 0.005 285.823) | oklch(0.985 0 0) | Popover / dropdown text |
| border | oklch(0.92 0.004 286.32) | oklch(1 0 0 / 10%) | Borders, dividers |
| input | oklch(0.92 0.004 286.32) | oklch(1 0 0 / 15%) | Input borders |
| ring | oklch(0.705 0.06 270) | oklch(0.552 0.05 270) | Focus rings |

### Chart colors

| Token | Light | Dark |
| --- | --- | --- |
| chart-1 | oklch(0.646 0.222 41.116) | oklch(0.488 0.243 264.376) |
| chart-2 | oklch(0.6 0.118 184.704) | oklch(0.696 0.17 162.48) |
| chart-3 | oklch(0.398 0.07 227.392) | oklch(0.769 0.188 70.08) |
| chart-4 | oklch(0.828 0.189 84.429) | oklch(0.627 0.265 303.9) |
| chart-5 | oklch(0.769 0.188 70.08) | oklch(0.645 0.246 16.439) |

### Sidebar colors

| Token | Light | Dark |
| --- | --- | --- |
| sidebar | oklch(0.985 0 0) | oklch(0.21 0.006 285.885) |
| sidebar-foreground | oklch(0.141 0.005 285.823) | oklch(0.985 0 0) |
| sidebar-primary | oklch(0.21 0.006 285.885) | oklch(0.488 0.243 264.376) |
| sidebar-primary-foreground | oklch(0.985 0 0) | oklch(0.985 0 0) |
| sidebar-accent | oklch(0.967 0.001 286.375) | oklch(0.274 0.006 286.033) |
| sidebar-accent-foreground | oklch(0.21 0.006 285.885) | oklch(0.985 0 0) |
| sidebar-border | oklch(0.92 0.004 286.32) | oklch(1 0 0 / 10%) |
| sidebar-ring | oklch(0.705 0.015 286.067) | oklch(0.552 0.016 285.938) |

### Status indicators

Not part of the token system, but used consistently:

- Success: `text-green-600` / `dark:text-green-400`, `bg-green-500`
- Error: `text-red-600`, `text-destructive`

## Typography

### Font families

| Token | Font | Usage |
| --- | --- | --- |
| --font-geist-sans | Geist | All UI text (applied to body) |
| --font-geist-mono | Geist Mono | Code, monospace content |

Body has `font-feature-settings: "rlig" 1, "calt" 1` and `antialiased` enabled.

### Type scale

| Class | Size | Usage |
| --- | --- | --- |
| text-xs | 12px | Timestamps, shortcuts, helper text, code |
| text-sm | 14px | Descriptions, labels, body copy, card descriptions |
| text-base | 16px | Base text, inputs (mobile) |
| text-lg | 18px | Dialog titles, sub-headings |
| text-xl | 20px | Section titles, header logo |
| text-2xl | 24px | Page titles, card titles |
| text-3xl | 30px | Dashboard / profile headings |
| text-4xl | 36px | Large display text |
| text-5xl | 48px | Hero title |

### Font weights

| Class | Weight | Usage |
| --- | --- | --- |
| font-medium | 500 | Buttons, labels, nav items |
| font-semibold | 600 | Card titles, section headings, badges, dialog titles |
| font-bold | 700 | Page titles, hero heading |

### Line heights and tracking

| Class | Usage |
| --- | --- |
| leading-none | Labels, card titles |
| leading-5 | Code blocks |
| leading-6 | List items |
| leading-7 | Paragraphs (markdown) |
| tracking-tight | Hero / display text |
| tracking-widest | Keyboard shortcuts |

## Spacing

### Container pattern

`container mx-auto px-4`

Responsive overrides where needed: Header `px-3 sm:px-4`; Footer `px-4 sm:px-6 lg:px-8`.

### Max widths

| Class | Value | Usage |
| --- | --- | --- |
| max-w-sm | 24rem | Auth forms |
| max-w-md | 28rem | Login / register cards, error pages |
| max-w-lg | 32rem | Dialog content (sm+) |
| max-w-2xl | 42rem | Large dialogs |
| max-w-3xl | 48rem | Embeds, protected state |
| max-w-4xl | 56rem | Main content pages |

### Vertical spacing (space-y)

| Class | Usage |
| --- | --- |
| space-y-1 | Tight lists, inline stacks |
| space-y-1.5 | Card header |
| space-y-2 | Form field groups, small stacks |
| space-y-3 | Footer stacks |
| space-y-4 | Form sections, dialog content |
| space-y-6 | Card content sections |
| space-y-8 | Page-level sections |

### Padding

| Class | Usage |
| --- | --- |
| p-1 | Dropdown content, icon buttons |
| p-2 | Code blocks, muted backgrounds |
| p-3 | Chat bubbles, inputs |
| p-4 | Grid items, action buttons, list items |
| p-6 | Cards, dialog content |

### Page vertical padding

| Class | Usage |
| --- | --- |
| py-3 sm:py-4 | Header |
| py-4 sm:py-6 | Footer |
| py-8 | Standard content pages |
| py-12 | Home page, dashboard |
| py-16 | Error / not-found pages |

## Border radius

| Token | Value | Class |
| --- | --- | --- |
| --radius | 0.625rem (10px) | Base |
| --radius-sm | calc(--radius minus 4px) = 6px | rounded-sm |
| --radius-md | calc(--radius minus 2px) = 8px | rounded-md |
| --radius-lg | var(--radius) = 10px | rounded-lg |
| --radius-xl | calc(--radius plus 4px) = 14px | rounded-xl |
| (full) | 9999px | rounded-full |

Usage: `rounded-md` for buttons, inputs, textarea, code blocks, dropdowns;
`rounded-lg` for cards, dialogs, feature cards, chat bubbles; `rounded-xl` for
the hero logo container; `rounded-full` for badges, avatars.

## Shadows

| Class | Usage |
| --- | --- |
| shadow-xs | Inputs, textarea, secondary / outline buttons |
| shadow-sm | Card base |
| shadow-md | Card hover, dropdown content |
| shadow-lg | Dialogs, dropdown sub-content |

No custom shadow definitions; all Tailwind defaults.

## Animations

### Custom keyframes

| Name | Effect | Duration | Easing |
| --- | --- | --- | --- |
| fade-in | Opacity 0 to 1 | 0.3s | ease-out |
| fade-up | Opacity 0 to 1 plus translateY (8px to 0) | 0.4s | ease-out |
| scale-in | Opacity 0 to 1 plus scale (0.97 to 1) | 0.2s | ease-out |

Use via `animate-fade-in`, `animate-fade-up`, `animate-scale-in`.

### tw-animate-css

Used on dialogs and dropdowns: `animate-in` / `animate-out`, `fade-in-0` /
`fade-out-0`, `zoom-in-95` / `zoom-out-95`, `slide-in-from-{top,bottom,left,right}-2`.

### Transition classes

| Class | Usage |
| --- | --- |
| transition-colors | Links, hover color changes |
| transition-opacity | Avatar hover, reveal-on-hover |
| transition-all duration-200 | Card interactive hover, buttons |
| transition-[color,box-shadow] | Input / textarea focus |

### Utility classes

```css
.card-interactive {
  @apply transition-all duration-200 ease-out;
}
.card-interactive:hover {
  @apply shadow-md -translate-y-0.5;
}

.auth-bg {
  background-image: radial-gradient(
    circle at 50% 0%,
    var(--accent) 0%,
    transparent 50%
  );
}
```

## Layout

### Root structure

```html
<body class="antialiased min-h-screen flex flex-col">
  <SiteHeader />
  <main id="main-content" class="flex-1">{children}</main>
  <SiteFooter />
  <Toaster />
</body>
```

### Page layout patterns

- Auth pages: `flex min-h-[calc(100vh-4rem)] items-center justify-center p-4`, then a Card `w-full max-w-md`.
- Standard content pages: `container mx-auto px-4 py-8`, then `max-w-4xl mx-auto`.
- Error / not-found pages: `container mx-auto px-4 py-16`, then `max-w-md mx-auto text-center`.

### Grid patterns

| Pattern | Usage |
| --- | --- |
| `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6` | Feature cards (4-col) |
| `grid grid-cols-1 md:grid-cols-2 gap-6` | Dashboard cards |
| `grid grid-cols-1 md:grid-cols-2 gap-4` | Profile info |
| `grid grid-cols-1 md:grid-cols-3 gap-4` | Quick actions |

### Responsive breakpoints

Standard Tailwind breakpoints: `sm:` (640px) for padding, text alignment, and
button sizing; `md:` (768px) for grid to 2 columns and input font size; `lg:`
(1024px) for grid to 4 columns and wide padding.

## Icons

Library: Lucide React.

| Size | Classes | Usage |
| --- | --- | --- |
| XS | h-3 w-3 | Inline badge icons |
| SM | h-3.5 w-3.5 | Copy buttons |
| Default | h-4 w-4 or size-4 | Standard UI icons |
| MD | h-5 w-5 | Header logo icon |
| LG | h-7 w-7 | Hero logo icon |
| XL | h-16 w-16 | Error / empty state illustrations |

Commonly used: Bot, User, Lock, Shield, Mail, Calendar, Copy, Check, Loader2,
LogOut, Sun, Moon, Github, ArrowLeft, RefreshCw, AlertCircle, FileQuestion,
Database, Palette, Video.

## Components (shadcn/ui)

All components live in `src/components/ui/`. They use `data-slot` attributes,
accept `className` for overrides via `cn()`, and follow either
`React.forwardRef` or functional component patterns.

### Button

6 variants (default, secondary, outline, ghost, destructive, link), 4 sizes
(CVA-based):

| Size | Height | Padding |
| --- | --- | --- |
| sm | h-8 | px-3 |
| default | h-9 | px-4 |
| lg | h-10 | px-6 |
| icon | size-9 | (none) |

### Card

Sub-components: Card, CardHeader, CardTitle, CardDescription, CardContent,
CardFooter. Base: `rounded-lg border bg-card text-card-foreground shadow-sm`.

### Input / Textarea

- Height: `h-9` (input), `min-h-16` (textarea)
- Border: `border bg-transparent rounded-md shadow-xs`
- Focus: `focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]`
- Validation: `aria-invalid:border-destructive aria-invalid:ring-destructive/20`
- Responsive font: `text-base md:text-sm`

### Badge

4 variants (default, secondary, destructive, outline). Base:
`rounded-full border px-2.5 py-0.5 text-xs font-semibold`.

### Dialog

Radix-based with overlay (`bg-black/50`), fade plus zoom animations, optional
close button.

### DropdownMenu

Radix-based. Content: `rounded-md border p-1 shadow-md min-w-[8rem]`. Items
support a destructive variant.

### Spinner

Sizes: sm (h-4 w-4), md (h-6 w-6), lg (h-8 w-8). Uses Loader2 with
`animate-spin`.

### Toast (Sonner)

Custom icons per state (success, info, warning, error, loading). Themed via CSS
variable overrides.

## Focus and interaction states

- Focus ring (global): `outline-2 outline-offset-2 outline-ring/70`. Component-level override: `focus-visible:ring-ring/50 focus-visible:ring-[3px]`.
- Disabled: `disabled:pointer-events-none disabled:opacity-50`.
- Interactive card hover: `transition-all duration-200 ease-out`, `hover:shadow-md hover:-translate-y-0.5`.

## Dark mode

- Method: class-based via next-themes with `attribute="class"` and `disableTransitionOnChange`.
- Default: system preference.
- Toggle: 3-way dropdown (Light, Dark, System).
- All semantic color tokens swap automatically via the `.dark` CSS selector.
- Use the `dark:` prefix for component-specific overrides (for example `dark:bg-input/30`).

## Branding

- Logo text: `bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent`.
- Logo icon container: `w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center`.
