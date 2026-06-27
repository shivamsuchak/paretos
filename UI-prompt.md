# paretos Design System — Prompt

Use this as a system/style prompt when generating any UI, deck, document, or mockup in the **paretos** visual language. It is extracted from paretos's **Cockpit** product (React + Material UI) and the Cockpit Component Library Figma file. Follow it exactly — do not invent colors, type, spacing, or components that aren't grounded here.

> **Scope note:** This describes a visual style only. Any product, brand, or person mentioned as an example is unrelated to the task at hand.

---

## 1. What paretos is

paretos is a **decision-intelligence platform** — AI-based optimization for business operations (demand forecast, replenishment, article allocation). The product, **Cockpit**, is a desktop web app: a sidebar + topbar + content shell hosting data-heavy dashboards, a data grid, charts, and an AI chat panel.

**The vibe in one line:** a sober operations cockpit — a restrained black/white/grey shell with the loud magenta→amber brand gradient used *sparingly*. The contrast between the calm UI and the rare brand splash *is* the aesthetic.

---

## 2. Voice & copy

- **Tone:** confident, direct, mildly technical. No hype, no exclamation marks, no marketing fluff inside the product. Calm.
- **Casing:** **sentence case for everything** — buttons, menu items, dialog titles. The only lowercase-forced word is the wordmark **paretos** (always lowercase). No all-caps in UI (buttons set `text-transform: initial`); overlines are the one uppercase exception.
- **Person:** third-person / imperative. Talk *about* the data ("Target revenue: 35.0 M€"), rarely "you", never "we" in-app.
- **Numbers:** tabular figures (`font-variant-numeric: tabular-nums`) in any data context. European separators appear (`35.0 M€`); currency symbol follows the number in the German locale.
- **CTAs:** verb first — "View title", "Compare with actual values", "Apply zoom", "Reset zoom", "Expand", "Collapse".
- **Microcopy:** empty states are full sentences with a period; tooltips are short, no period; disabled buttons surface a tooltip explaining *why*; "…" signals in-progress/loading; "—" is fine for breaks.
- **Emoji:** never. Don't add them.
- **Section headers:** short noun phrases — "Overview", "Restock strategy", "Iterations".

---

## 3. Color

Foundation is **monochrome**: pure black text on pure white surfaces, `#CCC` hairline borders, `#F2F2F2` hover surfaces. Black alphas (5/10/20/40/60%) replace tinted greys for state work. **The primary action color is BLACK, not violet.**

### Neutrals
| Token | Value | Use |
|---|---|---|
| `business-black` | `#000000` | primary text, primary button |
| `business-black-60` | `#666666` | secondary text, strong border on hover |
| `business-black-40` | `#999999` | tertiary text / placeholder |
| `business-black-20` | `#CCCCCC` | **the workhorse 1px border** |
| `business-black-10` | `rgba(0,0,0,.10)` | pressed neutral surface |
| `business-black-5` | `rgba(0,0,0,.05)` | disabled surface |
| `smokey-silver` | `#F2F2F2` | universal hover / subtle row surface |
| `white` | `#FFFFFF` | every surface |

### Brand accents
| Token | Value | Use |
|---|---|---|
| `versatile-violet` | `#5F26E0` | **selection** (selected nav/menu), focus, links, AI/highlighted CTAs, chart brush |
| `popular-pink` | `#F500E1` | gradient start |
| `youthful-yellow` | `#FBB03B` | warning / gradient end |
| `gainful-grey` | `#AAA3CC` | "data slate" — chart axes, neutral lavender |

Violet has soft tints `-5 #F7F4FD`, `-10 #EFE9FC`, `-20 #DFD4F9` for selected backgrounds.

### Semantic
| Meaning | Color | Soft background |
|---|---|---|
| Success | `generous-green #00C04D` | `#E6F9ED` |
| Error / destructive | `rebellious-red #FB6C4A` | `#FFF0ED` |
| Warning | `youthful-yellow #FBB03B` | `#FFF6E6` |
| Info | `talkative-turquoise #51D7E6` | `#E6F9F9` |

### The signature gradient
`linear-gradient(45.03deg, #F500E1 0%, #FBB03B 100%)` (magenta → amber). Appears **only** on: the brand mark, AI-related CTAs, `.gradient-text` headlines, loading shimmer (20% opacity), decorative brand frames. Also `-20` and `-10` opacity variants. There is one other gradient: `sustainability-gradient` (green-on-green at 10%) for sustainability views.

### Chart colorway (categorical, in order)
`#9F7DED` `#96E7F0` `#FDA792` `#66D994` `#FDD089` `#999999` `#FC896E` `#51D7E6` `#666666` `#33CD71` — soft, desaturated, accessible. Leads lavender / mint / peach / jade.

**No dark mode.** Every surface is white; dark only appears on the primary button and the gradient mark.

---

## 4. Type

- **Aeonik Pro** — the only display/text face. Regular (400) + Medium (500) only.
- **Consolas** — mono face for tabular values, code, chip labels.
- Base `1rem = 16px`. Body text `16px / 1.25`. Captions & overlines `12px`.
- Negative letter-spacing at every headline tier. Headlines default to **Medium 500**; `Alt` variants use **Regular 400** for softer/editorial use.
- Overline: `12px`, uppercase, `0.6px` tracking, `rgba(0,0,0,0.4)`.
- Numerals **tabular by default** in data contexts.

| Tier | Size | Tracking | Leading |
|---|---|---|---|
| h1 | 44.8px | -0.896px | 1.25 |
| h2 | 38.4px | -0.768px | 1 |
| h3 | 32px | -0.64px | 1 |
| h4 | 25.6px | -0.512px | 1.25 |
| h5 | 19.2px | -0.192px | 1.25 |
| h6 | 16px | 0 | 1.25 |
| body1 | 16px | — | 1.25 |
| body2 | 14px | — | 1.25 |
| caption | 12px | 0.24px | 1.25 |
| overline | 12px | 0.6px (uppercase) | 1.25 |

`font-family` stacks: sans `'Aeonik Pro', Roboto, Helvetica, Arial, sans-serif` · mono `'Consolas', 'Courier New', monospace`.

---

## 5. Spacing, radii, shadows, motion

- **Spacing ladder** (MUI base = 10): `5 · 10 · 12 · 20 · 30 · 40 · 60 · 80`. Default paddings: small 10, medium 12, large 20. **Page gutters 40px.**
- **Radii:** `3px` (chips/badges), `7px` (**default** — buttons, inputs, cards, dialogs), `10px` (large cards, accordions), `999px` (pill buttons).
- **Borders:** one weight — **1px solid `#CCCCCC`**. Hover often *strengthens* a border to `#666` rather than recoloring — a signature paretos move.
- **Shadows:** one only — `0 0 10px rgba(0,0,0,0.15)` — for floating UI (tooltips, menus, popovers, cards). Body cards use **borders, not shadows**. No inner shadows, no shadow stacks.
- **Motion:** subtle and short. Canonical button transition `0.3s` on background/color/opacity/outline/border. Layout (sidebar) `0.2s`. Linear or `ease-out` only — no bounce, no spring, no scroll scenes. `prefers-reduced-motion` collapses durations to `0.01ms`.
- **No blur** anywhere. Backdrops are solid `rgba(0,0,0,0.4)`.

---

## 6. Components

- **Buttons:** height 36px, radius 7px (or pill 999px for `rounded` variant), sentence case, `text-transform: initial`. **Primary = black** bg / white text. `paretos` variant = brand gradient (AI actions). Bordered = 1px `#CCC`. Hover: neutral → 5% darker solid (`#F2F2F2`); saturated CTA → `opacity 0.6`. Active: neutral → `business-black-10`; saturated → `opacity 1` (the press returns to full color). Focus reuses the hover look (no separate ring). Disabled: `business-black-5` bg, `rgba(0,0,0,0.20)` text.
- **Cards:** white, **1px `#CCC` border, no shadow**, radius 7px or 10px, padding ~20px.
- **KPI tiles:** card + value + delta. Pure border-and-text; some variants add a thin colored top accent.
- **Inputs:** 1px `#CCC` border, radius 7px. Focus → violet border. Error → red border.
- **Chips/badges:** radius 3px, mono labels common.
- **Topbar:** fixed 60px, full-bleed white, hairline bottom border. Logo in a 60×60 square with the brand gradient as background.
- **Sidebar:** fixed left rail, 60px collapsed / 180px expanded, white, hairline right border, expand toggle at bottom. Selected item uses violet.
- **Content area** scrolls; chrome doesn't. Pages fill width with 40px gutters — **never centered with max-width caps**.

---

## 7. Iconography

- Single in-house **line-icon set**: 1px stroke, ~18×18 viewBox, `stroke-linecap/linejoin: round`, no fill, geometric/mechanical. Default stroke `#000`, recolorable (white on dark, violet when active).
- **No icon font, no Material Icons / Lucide / FontAwesome in production. No emoji, no decorative unicode.**
- For mocks without the exact paretos icon, substitute **Lucide** at `stroke-width: 1` in the brand color — and flag the substitution.

---

## 8. Brand mark

- Three assets: **primary lockup** (arch + "paretos" wordmark — the default), **standalone icon** (the arch, for tight spaces / app icon / favicon), **wordmark only** (rare).
- Clear space = the width of the arch (`x`) on all sides.
- Color treatments, in order: 1) black on light (default), 2) white on black, 3) white on brand gradient (brand moments only).
- The standalone arch has a +3%-of-width optical shift right of center inside square/circle backplates.
- **Never** stretch, recolor outside the palette, add drop shadows, rotate, or alter the wordmark typography.

---

## 9. Backgrounds & imagery

Surfaces are **pure white** — no full-bleed images, patterns, textures, or noise. The only "imagery" in-product is data (charts, gridlines, KPI tiles) and the gradient logo. No illustrations, no stock photos, no avatar placeholders beyond the user initial.

---

## 10. Avoid

- Violet as a primary action color (primary is black).
- Gradients other than the one brand gradient (and the sustainability variant).
- Shadows on body cards (use borders).
- All-caps, emoji, exclamation marks, marketing hype in-product.
- Blur, spring/bounce motion, scroll-driven scenes.
- Inventing new greys (use black alphas), new radii, or a second typeface.