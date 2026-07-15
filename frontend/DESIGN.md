# Design system — Sandbox Control Plane UI

A **technical / console** aesthetic for a governed sandbox + terminal platform.
Reference points: Linear, Vercel, a real terminal. The point is a *committed* look,
not the statistical-average "AI dashboard." Build to these tokens; don't improvise.

## Hard prohibitions (the AI-slop tells)
- **No indigo / violet / purple.** No color gradients anywhere. No gradient text.
- **Not Inter / Roboto / system-ui** as the display face.
- **No glassmorphism / blur**, no big rounded corners, no drop shadows for decoration.
- **No 1px border on everything** — borders are dividers, used deliberately.
- **No emoji as icons** — one icon set (Lucide), consistent size.

## Palette (dark, monochrome-first)
Color carries **meaning only** — the UI is near-grayscale; the only saturated color is status.

| Token | Value | Use |
|---|---|---|
| `bg` | lifted near-black, `oklch(0.17 0 0)` | app background — off pure-black so surfaces read |
| `surface` | zinc-900, `oklch(0.215 0 0)` | cards, panels, dialog, table — a clear step above `bg` |
| `border` | `white / 14%` | dividers, table lines, panel edges |
| `text` | `zinc-100` | primary text |
| `text-muted` | `zinc-400` | labels, meta, secondary |
| primary action | `zinc-100` bg / `zinc-950` text | the one high-contrast button (inverted) |
| destructive | `red-500` | delete |

The base is a **lifted** near-black, not pure `zinc-950` — panels (`surface`) sit a visible step above it
so a sparse page still reads as intentional layers, not a void.

**Status colors** (badges only): running → `emerald-400`, provisioning → `amber-400`,
error/failed → `red-400`, deleting/deleted → `zinc-500`.

## Typography
- **UI:** Geist Sans. **Mono:** Geist Mono — for sandbox ids, image names, namespaces, the terminal,
  any code-like value. (Monospace on technical values is a deliberate dev-tool signal.)
- Dense base size **`text-sm` (14px)**; labels/meta `text-xs`; headings `text-base`/`text-lg`, weight 600.
- Weight contrast (400 body / 500 emphasis / 600 headings), not size alone.

## Shape & spacing
- **Radius:** small and uniform — `--radius: 0.375rem` (6px). One radius everywhere.
- **Borders:** 1px `zinc-800`, only as structure (table rows, panel edges), never decorative.
- **Shadows:** only real elevation (dialog/overlay). None on cards/buttons.
- **Density:** compact table rows; tight vertical rhythm; generous only at section breaks.

## Layout
- **Slim top header:** app name (mono, bold) left · "New Sandbox" button right. No heavy sidebar.
- **Main:** the sandbox table, full width, dense rows, status as a colored badge.
- **Terminal view:** full-height near-black (`zinc-950`) mono panel, own route.

## Components
shadcn/ui as the base — but **override the stock tokens** with the palette above (the defaults *are*
the slop). Use: Button, Table, Dialog, Select, Input, Badge. Icons: Lucide, 16px in dense UI.
