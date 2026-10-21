# Football Intelligence OS — UI/UX Design System

**Date:** 2026-10-21
**Stack:** Tailwind CSS (HSL CSS-variable theming, `darkMode: ["class"]`), Radix UI primitives
(`src/components/ui/*`), Recharts, Lucide icons, Inter typeface.

This is the source of truth for tokens, typography, components, and states. It describes what is
implemented in `Football_OS-frontend/frontend/src`, not an aspiration.

---

## 1. Design tokens

Tokens are **HSL CSS custom properties** declared in `src/index.css` under `@layer base`, and
mapped to Tailwind utilities in `tailwind.config.js`. The app ships a dark operations theme
(`.dark` class on the root); light values exist for completeness.

### 1.1 Colour (semantic, not decorative)

| Token | Tailwind | Role |
|---|---|---|
| `--background` | `background` | App canvas |
| `--foreground` | `foreground` | Primary text |
| `--card` / `--card-foreground` | `card` | Primary surface |
| `--popover` / `--popover-foreground` | `popover` | Elevated surface (menus, tooltips) |
| `--primary` / `--primary-foreground` | `primary` | Brand emphasis / interaction (cyan-teal) |
| `--secondary` / `--secondary-foreground` | `secondary` | Supporting surface |
| `--muted` / `--muted-foreground` | `muted` | Subtle surface / secondary text |
| `--accent` / `--accent-foreground` | `accent` | Interactive hover surface |
| `--destructive` / `--destructive-foreground` | `destructive` | Errors / destructive actions |
| `--border`, `--input`, `--ring` | `border`, `input`, `ring` | Borders, inputs, focus ring |
| `--chart-1..5` | `chart-1..5` | Categorical chart series |

**Colour carries meaning.** Cyan/teal (`--primary`) is brand + interaction only. Green is not a
generic decoration; red is not a universal highlight. Status is **always** paired with a label or
icon — never colour alone.

### 1.2 Radius, spacing, type

- **Radius:** `--radius` token; `rounded-lg/md/sm` derive from it (`var(--radius)`,
  `calc(-2px)`, `calc(-4px)`).
- **Spacing:** Tailwind's default 4px scale (`p-*`, `gap-*`, `space-*`) — used consistently.
- **Type:** Inter (`font-sans`); tabular numerals for statistics and currency; numeric table
  columns right-aligned.

---

## 2. Shared components

### 2.1 Shell & navigation
- **`AppShell.js`** — sidebar + command-palette host + main content region; wraps every
  authenticated route via `withShell(...)`.
- **`Sidebar.js`** — grouped nav (Overview / Intelligence / Recruitment / Match intelligence /
  Squad / Research / AI / System) with Lucide icons and active-route highlighting. Collapses to a
  horizontal scroller on tablet/mobile (verified at 768px & 390px, no viewport overflow).
- **`CommandPalette.js`** — ⌘K global search over players/clubs/actions; debounced, keyboard
  navigable, Escape closes.

### 2.2 Data-display primitives (`src/components/ui/*`)
Radix-backed, shadcn-style: `table`, `badge`, `card`, `button`, `input`, `select`, `tabs`,
`skeleton`, `dialog`, `sheet`, `drawer`, `pagination`, `separator`, `scroll-area`, `accordion`,
`tooltip`, `sonner` (toasts), `breadcrumb`, `progress`, `switch`, `checkbox`, `radio-group`,
`slider`, `calendar`, `command`. These are the building blocks — pages compose them rather than
re-styling one-off elements.

### 2.3 Domain components
- **`ModuleStateBanner.js`** — truthful banner for demo-gated (`409 DEMO_ONLY`) modules; explains
  *why* a module is unavailable instead of rendering blank.
- **`EvidenceDrawer.js`** — provenance/evidence side panel: source, sample size, epistemic label.
- **`AddToShortlistButton.js`** — shortlist action wired to the real endpoint.
- **`PerformanceRadar.js`** — Recharts radar for position-aware percentiles; axes labelled,
  consistent 0–1 domain, renders only with data.
- **`PitchHeatmap.js`** — football pitch visualisation for tactical/formation views.

### 2.4 API layer
- **`lib/footballApi.js`** — the single API client. Every screen goes through it; no competing
  endpoints. Holds the bearer token **in memory only**.
- **`lib/playerPagination.js`** — server-side pagination helper (unit-tested); keeps the true
  total and page math in sync with the backend.

---

## 3. States (the core of the product's honesty)

Every data screen implements this state machine explicitly:

| State | Meaning | UI |
|---|---|---|
| **Loading** | Request in flight | Skeleton / spinner |
| **Empty** | Legitimately no rows | Explained empty state + safe next action |
| **Error** | Request failed | Error panel + working retry |
| **Partial** | Valid subset available | Partial banner + what's missing |
| **Demo-gated** | `409 DEMO_ONLY` | `ModuleStateBanner` explanation |

### 3.1 Epistemic / data-availability labels
Rendered as badges, always with text:
`MEASURED` · `MODELLED` · `OBSERVED` · `INSUFFICIENT_DATA` · `INSUFFICIENT_SAMPLE` ·
`OUT_OF_DISTRIBUTION` · `MODEL_UNCALIBRATED` · `BLOCKED_BY_PLAN` · `DEMO_ONLY`.

### 3.2 The null-vs-zero rule (non-negotiable)
- Unknown/absent metric → `—` (em dash). **Never `0`.**
- `0` is reserved for an *observed* zero (e.g. 0 yellow cards).
- Players below the minutes threshold (<600) output `INSUFFICIENT_SAMPLE` / `INSUFFICIENT_DATA`.

---

## 4. Charts

- Recharts only (already installed; no new charting dependency).
- Every chart: title, labelled axes with units, meaningful legend, keyboard/screen-reader text
  alternative, correct empty/partial handling, responsive container.
- No 3D, no decorative charts, no unlike-unit comparisons on a shared scale, no chart built on
  fabricated sample data.

---

## 5. Accessibility (WCAG 2.2 AA target)

- Visible keyboard focus (`--ring`), semantic headings/labels, accessible names on icon buttons.
- Status never conveyed by colour alone (label/icon always present).
- Reduced-motion respected; restrained, functional motion only.
- Tables use deliberate local horizontal scroll; the app never becomes an uncontrolled
  horizontally-scrolling page (verified at 1440 / 768 / 390).

---

## 6. Responsiveness

Primary target: desktop scouting workstation. Verified no viewport-level horizontal overflow at
1440 (desktop), 768 (tablet — sidebar collapses to horizontal nav), and 390 (mobile — tables use
contained local scroll). Evidence screenshots in `docs/evidence/` (e.g.
`desktop-players-1440.png`, `mobile-players-390.png`).
