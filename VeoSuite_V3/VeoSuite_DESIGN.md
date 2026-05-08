# DESIGN.md - VeoSuite V3 AI Factory

## 1. Visual Theme & Atmosphere
VeoSuite V3 is an advanced AI video production factory. The atmosphere should feel like a high-tech command center: dark, precise, technical, and powerful. 

**Vibe**: Cyber-industrial, Terminal-native, High-performance AI Lab.
**Core Concept**: "Void Black Canvas with Emerald and Violet Accents"

## 2. Color Palette & Roles

| Semantic Token | Hex | Role |
|---------------|-----|------|
| `bg-primary` | `#121212` | Main application background (Void Black) |
| `bg-secondary` | `#1E1E1E` | Panels, sidebars, group boxes |
| `bg-tertiary` | `#2D2D30` | Hover states, selected items |
| `accent-primary` | `#00E676` | Success, "Start/Run" actions, active states (Emerald) |
| `accent-secondary` | `#8E2DE2` | AI features, auto-magic actions (Violet) |
| `accent-warning` | `#F39C12` | Warnings, intermediate states, paused |
| `accent-danger` | `#E74C3C` | Stop, delete, errors |
| `text-primary` | `#FFFFFF` | Main body text |
| `text-secondary` | `#A0A0A0` | Subtitles, disabled text |
| `border-color` | `#333333` | Borders, dividers |

## 3. Typography Rules
- **Font Family**: `Consolas`, `Cascadia Code`, or standard sans-serif (`Segoe UI`).
- **Headings**: 16px to 20px, Bold, usually colored with `accent-primary` or `accent-secondary`.
- **Body Text**: 12px to 14px, standard weight.
- **Console/Logs**: 11px to 12px, Monospace, `text-primary` or `accent-primary` for success.

## 4. Component Stylings

### Buttons
- **Primary (Action)**: Solid background (`accent-primary` or `accent-secondary`), white text, bold, no border, 4px border-radius.
- **Secondary**: Dark background (`bg-tertiary`), white text, 1px solid `border-color`.
- **Danger (Stop/Delete)**: Solid background (`accent-danger`), white text.

### Inputs & Text Areas
- Background: `#181818` (darker than secondary)
- Border: 1px solid `border-color`, changes to `accent-primary` on focus.
- Text: `#FFFFFF`
- Padding: 8px

### GroupBoxes & Panels
- Border: 1px solid `border-color` or 1px dashed `border-color`.
- Title: Bold, capitalized.
- Background: `bg-secondary`.

### Scrollbars
- Slim, modern, dark track with a slightly lighter thumb. No clunky Windows-95 style borders.

## 5. Layout Principles
- Use grid layouts for metrics and dashboards.
- Tight margins for a data-dense look (padding: 8px to 12px).
- Group related controls together using QGroupBox.

## 6. Do's and Don'ts
- **DO** use icons (emoji or SVG) to indicate actions clearly.
- **DO** use gradient backgrounds for "AI Magic" buttons to make them pop.
- **DON'T** use pure white (`#FFFFFF`) for backgrounds.
- **DON'T** mix too many bright colors. Stick to the emerald/violet accent system.
