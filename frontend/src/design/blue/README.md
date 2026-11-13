# Blue design (students) — contract for page authors

Everything here is student-only. The student shell (`StudentShell.jsx`, rendered by
`AppShell` in `App.jsx` when `user.role === 'student'`) puts `nb-blue` on
`.app-shell.role-student`. **Write page CSS under `.nb-blue`** and never touch the
classic classes (`.panel`, `.card`, `.button`, `.sidebar`, ...) for students.

Files: `tokens.css` (variables, loaded globally, scoped), `ui.jsx` + `ui.css`
(primitives), `controls.jsx` (language / theme pickers), `shell.css` +
`StudentShell.jsx` (shell), `theme.js` (appearance store), `login.css` (sign-in
page only, class `.nb-login`).

`App.jsx` already imports `tokens.css`, `ui.css`, `shell.css`. A page imports only
its own css file. Import primitives with:

```jsx
import { PageHeader, KpiRow, KpiTile, GlassCard } from '../design/blue/ui';
```

## Conventions

* Class prefix `nb-`. Page-level classes: `nb-<page>-...` (e.g. `nb-meet-row`).
* Colours, radii, shadows only through tokens (below); never hard-code light-mode
  hex values, or the two dark looks and Reading mode break.
* Font sizes in `rem` / `var(--nb-text-*)`; `tests/typeScale.test.mjs` forbids `px`
  font sizes and anything under 12px (`--nb-text-xs` is 0.75rem).
* Media queries must use the stylelint breakpoints: `max-width: 380 / 560 / 820 / 1100 / 1200px`.
  The shell turns into the mobile layout (drawer + bottom dock) at `max-width: 820px`.
* Every visible string goes through `t()` (uz + ru in your own `translations/blue*.js`).
* Real data only; the primitives hold no data.

## Tokens (`.nb-blue`, switched by `data-nb-theme` = `light | tinted | night`, `data-nb-read`)

| Group | Variables |
| --- | --- |
| Type | `--nb-font` (Mona Sans), `--nb-text-xs/sm/md/lg/xl/2xl/title` |
| Shape | `--nb-r-xs/sm/md/lg/xl/pill`, `--nb-gap` (16px), `--nb-gap-lg`, `--nb-pad` (card padding 22px), `--nb-page-x` |
| Ink | `--nb-ink`, `--nb-ink-strong`, `--nb-ink-2`, `--nb-muted`, `--nb-faint`, `--nb-line`, `--nb-line-soft` |
| Brand | `--nb-blue`, `--nb-blue-d`, `--nb-blue-l`, `--nb-link`, `--nb-tint`, `--nb-tint-strong`, `--nb-chip-bg/fg` |
| Surfaces | `--nb-glass` (+`-hover`, `-line`, `--nb-blur`, `--nb-shadow`), `--nb-card` (solid white / dark surface), `--nb-card-fg`, `--nb-card-soft`, `--nb-card-hover` |
| Tiles | `--nb-kpi-0..3`, `--nb-kpi-fg`, `--nb-kpi-line`, `--nb-kpi-shadow`, `--nb-kpi-chip`; `--nb-hero` (navy panel), `--nb-hero-fg/soft/line` |
| Buttons | `--nb-btn`, `--nb-btn-fg`, `--nb-btn-shadow`, `--nb-btn-ghost`, `--nb-btn-ghost-fg` |
| Status | `--nb-ok(-bg)`, `--nb-warn(-bg)`, `--nb-late(-bg/-line)`, `--nb-gold`, `--nb-gold-fg`, `--nb-dot`, `--nb-focus` |

Dark looks are flat (no blur, no backdrop): the `--nb-blur` / `--nb-glass*` tokens
already resolve to flat surfaces, so use them instead of writing `backdrop-filter`
yourself. Light cards over the mountain backdrop use `GlassCard` (frosted) or
`GlassCard tone="solid"` (opaque white) when text-heavy.

## Shell geometry

* `.nb-main` is the content column (left padding 0, the sidebar column has the gap).
  The top-right controls (search, export PDF, language, theme and anything you add with
  `HeaderTools`) are an absolutely positioned overlay in the first ~72px of the column:
  `.nb-main` has `padding-top: 80px` so a normal `PageHeader` starts below them.
  A page whose header should share the controls' row (the dashboard greeting) can pull
  itself up with `.nb-page-dashboard .nb-page-header { margin-top: -56px; }`
  (`nb-page-<page key>` is on `.nb-main`, `data-nb-page` on the shell). On mobile (<=820px)
  the controls are a normal row above the content: no negative margin there.
* Page content is a `div.page-content.nb-content` (the PDF export and old code still use `.page-content`).
* Bottom dock on mobile is 68px + 12px offset; `.nb-main` already pads the bottom for it.
* Un-ported pages: while no `PageHeader` is mounted, the shell shows a fallback title and
  wraps the page in a frosted `.is-legacy` panel (legacy colours re-mapped for dark looks).
  **As soon as your page renders `PageHeader` the fallback title and panel disappear**,
  so a ported page owns its full layout. Render `PageHeader` in every state of the page
  (loading, empty, error) to avoid the legacy panel flashing in.
* The roadmap slot in the sidebar/dock shows `Tasks` while `roadmap` is locked for
  students in `lib/routes.js`; it switches to Roadmap by itself once `roadmap` opens.
* Naseeb Mind is the nav label of page key `find_personality`; the page title still comes from `PAGE_META`.

## Primitives (`ui.jsx`)

`icon` props take a lucide component (`icon={Bell}`) or a ready element.

### `PageHeader({ title, subtitle, actions, className, headingId })`
`<header.nb-page-header>` with an `h1`. `title` may be a node (the greeting
`Good morning, <b>Name</b>`). `actions` = node(s), usually a `BlueButton`, right-aligned
(wraps under the title on mobile). Mounting it hides the shell's fallback header.

### `HeaderTools({ children })`
Portals `children` into the shell's top-right row (before search / language / theme).
Used by the dashboard for its "Customize" button. Render it anywhere in your page.

### `SectionTitle({ children, action, as = 'h2', className })`
Bold in-page section heading ("My activity") with an optional right-side action.

### `KpiRow({ children, columns, className, label })` and `KpiTile`
`KpiRow` is a grid of `columns` (default 4; 2 columns <=820px). 
`KpiTile({ icon, value, unit, label, onClick, href, tone = 0, className, actionLabel, loading })`:
blue gradient tile; `value` big number, `unit` small suffix ("min"), `label`.
With `onClick` it is a `<button>` (or `<a>` with `href`) showing the round arrow; give it
`actionLabel` as the accessible name when `label` alone is not enough. `tone` 0-3 picks the
gradient (use `tone={index}` to alternate). In the dark looks tones 0-1 are dark surfaces and 2-3 the blue accent.

### `GlassCard({ title, icon, action, footer, children, tone = 'glass', as = 'section', headingLevel = 'h3', className, ...rest })`
Card with header (icon chip + title + `action` node on the right), body and optional
`footer` node (left text + `CardLink` is the usual pattern, `footer` is a flex row with
`space-between`). `tone`: `glass` (frosted), `solid` (white / dark surface), `hero`
(navy gradient with white text). Extra props (`id`, `data-*`, `onClick`) go to the element.

### `CardLink({ children, onClick, href })`
"View all >" link-button for footers.

### `PillTabs({ tabs, value, onChange, label, idPrefix = 'nb', className })`
`tabs = [{ key, label, count? }]`. `role="tablist"`, roving tabindex, Arrow/Home/End keys.
`onChange(key)` is called on click and on arrow keys. Pair the panel with
`role="tabpanel" aria-labelledby={tabId(idPrefix, activeKey)}` (`tabId` is exported).
`label` is the accessible name of the group.

### `Chip({ variant = 'default', icon, children, className })`
Variants: `default | days | overdue | ok | warn | gold | new`.
`DaysChip({ days })`: number of whole days left -> "N days left" (plural aware), `0` -> "Due today",
negative -> "Overdue" (red). Returns `null` for a missing number.

### `BlueButton({ variant = 'primary', size = 'md', icon, iconRight, arrow, href, children, ...rest })`
`variant`: `primary` (blue gradient pill) or `ghost` (frosted). `size="sm"` is the 36px button.
`arrow` appends the arrow-right icon. Renders `<a>` when `href` is given, else `<button type="button">`
(pass `type="submit"` explicitly for forms). All other props (`onClick`, `disabled`, `aria-*`) are forwarded.

### `EmptyState({ icon, title, text, action, className })`
Big blue icon tile, title, text and an `action` node (usually a `BlueButton`).

### `DateTile({ day, month, hot })`
52px day/month badge used by deadline, program and notification rows (`hot` = navy fill).

### `Avatar({ name, src, size = 40, className })`
Initials on a blue tile, or the image when `src` is given (use the existing photo helpers for `src`).

### `ShellContext` / `useContext`
Internal: lets `PageHeader` tell the shell it drew a heading. Do not use directly.

## Controls (`controls.jsx`) and theme (`theme.js`)

* `LanguagePicker({ language, onChange, variant = 'menu' | 'segmented' })` and
  `ThemePicker({ variant = 'menu' | 'toggle' })` are the shell's header controls (also used by the sign-in page).
* `useBlueTheme()` -> `{ mode: 'light'|'tinted'|'night', reading, setMode, setReading, toggleDark }`,
  persisted in `localStorage['naseeb-edu-blue-theme-v1']` (per browser, not per account).
  The old `hooks/useTheme.js` is untouched (counselors/others stay light).

## Translation modules (one per agent, already registered in `i18n.js`)

`translations/blueDashboard.js`, `blueCenter.js`, `blueMeetings.js`, `blueCatalog.js`
export `BLUE_*_TRANSLATIONS = { 'English key': ['Uzbek', 'Russian'] }`; `blueShell.js` is the shell /
primitives / sign-in set. Keys defined in an earlier module (e.g. `ui.js`) can be reused without repeating.
`tests/translationCoverage.test.mjs` fails on any literal `t('...')` with a missing uz or ru entry.

## Fonts and assets

Mona Sans comes from `@fontsource-variable/mona-sans` (self-hosted by Vite; CSP `font-src 'self'` is fine).
It has no Cyrillic glyphs: Russian falls back to the system UI font in the stack.
The backdrop is `assets/backdrop.webp` (hashed by Vite, `img-src 'self'`). The brand logo is
`/brand/naseeb-logo-navy.png` (light) / `naseeb-logo-white.png` (dark looks).
