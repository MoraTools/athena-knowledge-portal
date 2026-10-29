# Athena design system

## Scope

The reader, the account pages and the Django admin use the suite theme A, One gold, in a light and a dark theme, with the interface in Spanish (default) and English. In the admin, Athena's own strings switch language; Django's built-in strings stay Spanish.
Mi cuenta is a reader page (`/#/account`, served as `/account.md`); the password pages use the same rail and widths. Only sign-in is a standalone centred page. Administration keeps Django's native forms and lists, restyled by one control system in `server/athena/static/athena/admin.css`; the user directory (`admin/auth/user/`) uses a semantic roster table and inspector on the same tokens.
Signed-in admin pages start with a 52px command row: the breadcrumbs on the left and the two toggles at the far right (`header.admin-command`; Django's `#header` stays only on sign-in). The rule under the row sits on the breadcrumbs' `nav`, so it spans the row also where a page has no breadcrumbs. The article editor puts the toggles at the end of its own header row. Admin sign-in shows the toggles at the top right of the window.
The directory starts with its own Usuarios task heading and omits breadcrumbs and the duplicate global title.

## Tokens

`src/assets/suite-tokens.css` holds the suite A tokens, the same names and values as the theme kit, on `:root[data-theme="dark"]` and `:root[data-theme="light"]`, with a `prefers-color-scheme` fallback when no `data-theme` is set. Colour literals exist only in these token blocks.

| Role | Tokens |
| --- | --- |
| Grounds | `--rail`, `--bg`, `--surface`, `--surface-raised`, `--surface-strong`, `--field-bg` |
| Lines | `--border`, `--border-strong` |
| Text | `--text`, `--text-muted`, `--text-subtle` |
| Gold | `--accent` (fills), `--accent-hover`, `--accent-edge`, `--accent-text` (gold text and links), `--on-accent` (text on gold), `--focus` |
| States | `--ok`, `--warn`, `--crit`, `--crit-text`, `--info` |
| Statue | `--seal-athena-gain`, `--seal-filter`, `--seal-blend` (light: `brightness(1.25) invert(1)`, multiply) |

Reader aliases (`--surface-2`, `--muted`, `--quiet`, `--line`, `--line-strong`, `--accent-soft`) map onto these tokens for older rules and the shared rail. Gold text always uses `--accent-text`; `--accent` is for fills and rules. Flat surfaces with 1px borders and 4px corners; no shadows at rest.

## Spacing

One scale, defined in `src/assets/suite-tokens.css` and used by the reader and the admin. Use a step, not a new number.

| Token | Value | Use |
| --- | --- | --- |
| `--space-1` | `8px` | Label to control, meta line to title, heading 3 bottom margin |
| `--space-2` | `16px` | Gaps in card lists and grids, H1 and H2 bottom margins, mobile side padding, admin form-row vertical padding |
| `--space-3` | `24px` | Card and panel padding, fieldset inset, submit rows, account column side padding, reader page padding |
| `--space-4` | `32px` | Section gaps, H2 and H3 top margins, admin page padding, Actualizaciones card padding and post gap |
| `--space-5` | `48px` | Reader page bottom padding, hero bottom margin |

A card's padding is the only space at its edges: its first child has no top margin and its last child no bottom margin.
A list of cards gets its gap from the grid, never from card margins. The last block of a page has no bottom margin.

## Type

Fonts are local woff2 files with their OFL 1.1 notices in `src/fonts/LICENSE.md`.

| Role | Font | Use |
| --- | --- | --- |
| Interface | Inter 4.001 | Body, controls, rail items, cards, h3 (18px/24px 650) |
| Display | Cormorant 4.000 | The wordmark (22px, uppercase by style), the home heading, page and article h1 (40px/46px) and h2 (30px/36px), the command-bar title (26px). Never below 22px. |
| Mono | `Consolas, "Cascadia Mono", ui-monospace, "SF Mono", Menlo, "DejaVu Sans Mono", monospace` | Code, labels (11px uppercase 0.06em 600), chips and tags (10px uppercase 0.04em) |

Article prose is 17px/1.65 with a 70ch measure. Buttons are Inter 13px 600 in sentence case.

Admin body text is Inter 14px/1.5, inputs and table cells 13px; help text is 12px in subtle text. Admin page titles (the Django `h1`, Usuarios, the directory inspector heading, the editor's details dialog) use Cormorant 26px/32px; the editor's title field and preview headings use the reader sizes. The admin sign-in header shows ATHENA in the wordmark voice and "Administración" in the label voice.
Admin labels, fieldset and table headers, breadcrumbs and panel heads use the label voice (mono 11px uppercase 0.06em 600); pills are the kit chip (mono 10px uppercase 0.04em); dates and counts use mono 13px with tabular figures.

## Layout

One width rule for the reader, the account pages and the admin: `--content-max` is 1320px (reader and admin `:root`).
Content starts at the left content edge beside the portal rail and fills the space up to `--content-max`. Above a 1600px viewport it is centred in the space beside the rail, which stays fixed on the left.
The reader reserves the rail width once on `div#main`. Docsify's `.content` stays in normal flow without its theme's sidebar offset or transform. `div#main` is the named `reader` container, so component layouts use the width that remains beside the rail.
Prose, cards, timelines, grids, tables and the downloads catalog all fill the content width; only `--content-max` (1320px, centred above 1600px) bounds them.
`.library-grid` uses `repeat(auto-fill, minmax(min(100%, 320px), 1fr))`, so cards fill available columns and fit containers narrower than 320px.
No page scrolls horizontally from 320px to 2560px; a table that is too wide scrolls inside its own container. Long titles, tags, and filenames wrap. Grid children can shrink within their column.
Reader tables use `--surface` rows, `--surface-raised` headers in the label voice, and 1px `--border` rules below cells. Cells align at the top with 8px vertical and 12px side padding; code identifiers stay on one line. Callouts and blockquotes are surface panels with a 1px border.
In sortable reader tables, a column with body text longer than 60 characters has a 32ch minimum width. Long descriptions wrap inside the table's local scroll area; short tables keep their natural widths.
`.markdown-section` pads `--space-3 --space-3 --space-5`; at 768px and below `--space-3 --space-2 --space-4`.
When the available reader container is at least 900px wide, article headings appear in a 216px sticky right-hand page tree. The article and tree share one grid and the page gutters. Below that width, the same native details tree appears above the article and starts closed. Its toggle stays available in both layouts. A width change restores the default only when the tree changes between the side and inline layouts; reader choices stay within the same layout.
At reader widths of 900px and below, the home hero and account panels stack. At 600px and below, portal cards, search results, filter controls, and catalog entries use one column. The feed keeps each date above its post at this width, so the date column does not reduce the reading space.
Guías and Descargas share one filter panel (`library-controls`): a search field and a select, 44px high, with a live result count.
Actualizaciones cards pad `--space-4` (`--space-3` at a reader width of 600px and below), with the meta line above a 2rem title and a 17px/1.6 summary. In the date-column layout, the badge is centred on the first line of the title.

Mi cuenta shows the username, a role and last-session line, then Sesión and Mis claves de API side by side (1:2) above a 900px reader width and stacked below; administrators also get an Administración row of shortcuts.
The password pages pad like `.markdown-section`; their form is at most 40rem wide.
Sign-in uses a centred 650px column padded `--space-4 --space-3`; headings leave `--space-2` below.
Inputs and buttons are 32px high with a 4px radius.

Admin pages use the named `admin-page` container, which measures the width beside the rail. They pad `--space-4` (`--space-3` at 1024px and below; `--space-2` sides at 767px and below); fieldsets and form rows inset `--space-3`; table cells use the kit's 8px vertical and 12px side padding, also in the row-control column.
`#content` follows the width rule. Change forms use the full width: aligned textareas fill the row beside the 180px label column.
When the changelist area is narrower than 1200px (a container query, so the rail's width counts), the filter moves under the table with its groups side by side.
Admin forms retain Django's responsive layout. Flex rows wrap and child containers use zero minimum width. At an available admin width of 1000px and below, recent actions stack below the dashboard. Object tools move below the title at 900px and below; aligned labels stack above their fields at 720px and below.
At 767px and below, `body .aligned .form-row > div` uses `width: 100%; max-width: 100%`.
Preserve this override; Django's default viewport-based width can extend beyond the available space when scrollbars are present.
Admin form controls are 32px high (44px at 760px and below and for a coarse pointer).
The article editor shows Markdown and its preview side by side above an available 900px width. At 900px and below, its existing Markdown and preview tabs select the pane. Toolbar, pane, and dialog headers wrap; read-only values, errors, and filenames wrap within the form.
API key creation fills the content width and its actions wrap. Standalone sign-in aligns the wordmark and form within the same 650px column.
The directory keeps the 1320px cap and full 256px rail. Its wide grid divides the roster and inspector 1.55:1, with a 360px minimum inspector width. At a content-container width of 1140px and below, the two sections stack.
The roster table has a 620px minimum width and scrolls inside its own container. A scroll cue appears only when the roster interior is below 620px wide.
Roster cells have no vertical padding. Username and header links have a 40px minimum height (44px for a coarse pointer), so one-line rows measure 41px on desktop. Keep the thin row rules, existing text size, pills, status marks, selection, and focus outlines.

## Navigation

The reader and the admin share one portal rail: markup in `src/index.html` and `admin/portal_sidebar.html`, styles in `src/assets/rail.css`, behavior in `src/assets/rail.js`.
Its links come from `sidebar_markdown()`: groups Biblioteca, Participar, Cuenta (Mi cuenta, `/#/account`), and Administración (staff only). In the admin, the model pages follow the Administración links. On `/accounts/` pages Mi cuenta is current.
The rail carries the Athena wordmark (title case in the source, uppercase by style) above KNOWLEDGE PORTAL. Hiding the rail does not add an admin header. Admin sign-in keeps the ATHENA link and "Administración" section label; the password pages keep the sign-in header's wordmark.
The rail provides site navigation and API para agentes. Mi cuenta keeps Cambiar contraseña and Cerrar sesión; logout uses a CSRF-protected POST form.
Each item is a 20px line icon and an Inter 13px 500 label on a 40px row (44px for a coarse pointer); group labels are mono 11px uppercase in subtle text. The current page has gold text, a raised fill and a 2px gold edge on the left.

| State | Rail | Behavior |
| --- | --- | --- |
| Expanded | 256px | Group labels, icons and labels; the reader search form sits above the groups. |
| Compact | 72px | Icons only. Group labels fade out and thin rules separate the groups. A tooltip names the item on hover or focus. The current item is a filled tile. The wordmark shrinks to its A, and the search becomes an icon that expands the rail and focuses the field. |
| Hidden | 0 | The rail slides away; the menu button in the command bar brings it back (the admin keeps its floating button). |

The control at the bottom of the rail switches Contraer and Expandir; its chevron turns. Keys: `]` toggles compact, `[` toggles hidden; both are ignored inside form fields.
One 360ms `cubic-bezier(.2, .8, .2, 1)` transition moves the rail width, the page offset, the labels, and the chevron; reduced motion removes it.
The state is kept in `localStorage` (`athena.rail`), so the choice carries between the reader and the admin.
At 1024px and below the rail is an overlay drawer that starts closed and is never stored: the command-bar menu button (the floating button in the admin) opens it, and Escape, a followed link, or a tap outside closes it.
On the directory at 1024px and below, `.rail-reveal` occupies a normal-flow row above the content, so it cannot cover fields. The shared overlay opening and closing behavior stays the same.

## Command bar and preferences

The reader has a 52px sticky command bar: the menu button (when the rail is hidden or a drawer), the crumb and the Cormorant page title from the route, the access label on the home, then two icon toggles at the far right. Account pages and sign-in show the same toggles at the top right.
The language toggle uses the Lucide languages icon; the theme toggle shows a sun in dark and a moon in light. Labels follow the current language.
`src/assets/boot.js` runs blocking in `<head>` before the stylesheets and sets `data-theme` and `lang` from `suite.athena.theme` and `suite.athena.lang`, else from the browser (default language Spanish). A toggle back to the browser value removes the key; with no key, system changes apply live. While English loads, the body stays hidden until the first translation pass (1.5 s fallback).
`src/assets/suite-i18n.js` translates interface text by its exact Spanish source after each Docsify render; article prose under `/content/` stays Spanish. Dates in `time[datetime]` use `Intl` in the current language. Theme changes animate colours for 160ms, none under reduced motion.

## Controls and states

Use native inputs, selects, date and calendar controls, file uploads, and Django validation messages.
The article Markdown textarea supports pasted PNG/JPEG/WebP images and a secondary **Insertar imagen** button below the field.
Keep its native text behavior. Image insertion preserves selected text; progress and upload errors appear beside the button with a live status.
Save controls stay disabled during upload. The helper wraps below the textarea on narrow screens and uses the existing control and spacing tokens.
Keep visible labels, skip links, focus outlines, and reduced-motion support.
Focus outlines are 2px `--focus` with a 2px offset everywhere, the admin included.
Most reader surfaces are square. Reader and account controls are 32px high (44px for a coarse pointer), 4px radius, 1px `--border-strong` border. Admin controls follow the same rule.
Primary buttons (default submit, Añadir, Guardar) are `--accent` with `--on-accent` text and an `--accent-edge` border; hover is `--accent-hover`. Secondary buttons (other submits, Historial and the other object tools, Buscar, Cancelar) are `--surface` with `--text` and a `--border-strong` border; hover raises the fill. Danger buttons (Eliminar) have a `--crit` border, `--crit-text` and a 10% `--crit` fill. Disabled controls are 50% opacity.
Changelists end with an unlabeled controls column of 28px square icon links (44px for a coarse pointer; Ver or Descargar, Editar, Eliminar) in the secondary style, Eliminar in the danger colors; `title` and `aria-label` name each one. The column stays pinned to the right edge when the table scrolls. Eliminar opens Django's confirmation page. Existing Django header sorting stays native.
Django's action select is hidden. Checking rows shows a sticky bar above the table (count, Eliminar seleccionados, Cancelar; 28px buttons) that runs `delete_selected` through the hidden action form, so the confirmation page still protects it (`static/athena/admin-list.js`).
Selects use the kit's drawn chevron in muted text; checkboxes and radios are 16px with the gold accent. Changelist booleans render as chips (gold for true, dashed subtle for false), never icons.
Admin colours come only from the suite tokens: `admin.css` maps Django's own variables (`--body-bg`, `--primary`, `--link-fg` and the rest) onto them in one block, so Django's widgets follow both themes, and adds only tints built with `color-mix()`. `admin/base_site.html` loads `boot.js` and the tokens in Django's `dark-mode-vars` block (the first head block; only Django's `base.css` link precedes it), which also drops Django's `theme.js` and `dark_mode.css`. The directory and editor stylesheets consume the tokens and define none. The shared rail stylesheet defines only its own sizes and timing (`--rail-*`) and reads the suite tokens, so the rail looks the same in the reader and the admin.

Ordinary reader tables, including account API keys, API reference tables, and simple article tables, receive native header buttons after rendering. Buttons have a 40px minimum height (44px for a coarse pointer), drawn direction indicators, and `aria-sort`. The initial author or server order stays until a header is selected; each header alternates ascending and descending order. Text sorting uses numeric-aware Spanish comparison. Explicit ISO values or `time[datetime]` provide date order; account expiry cells carry ISO values. Sorting moves the existing rows and keeps links, forms, and the footer. Setup runs once per table. Merged cells, multiple header rows, nested tables, presentation tables, interactive headers, and `data-sortable="false"` tables retain their existing behavior.

The directory roster has Usuario, Acceso, Estado, and Sesión columns. Actual accounts start in ascending username order. All four headers are native GET links that alternate ascending and descending order, with drawn direction indicators and `aria-sort`. Equal roles, statuses, and session dates keep stable username order; accounts with no session date stay last in both date orders. Username links select the inspector; the selected row has an `--accent-edge` outline and a gold tint. Role and active status stay separate. Sesión shows the actual `last_login` date and time, or `nunca`.
Search uses a native GET form and a live filter; both ignore case and accents. Usernames, full names, and email values are searchable. Full names also appear in username tooltips.
Native search, selection, new user navigation, and saving retain the submitted search and sort parameters. Header links retain the current selection; the live filter also updates their search query.
The inspector uses native role radios and an active checkbox. The administrator role shows Permisos de edición; hiding that area does not reset checked values. Native field and form errors stay visible, including edit-area errors.
When editing is permitted, one full-width gold Guardar button is the primary action. Manual password reset, API keys, and individual deletion use quieter links with 20px line icons and thin separators; the separators are horizontal on mobile. Native deletion confirmation and self/last-admin protections remain.
Email is disabled; an empty field shows `No disponible`. The short visible help is "Servicio de correo no configurado." The full existing reason remains in the tooltip and accessible help. Existing email values stay; new email values are not saved.

## Boundaries

Spanish is the source and default interface language; English comes from `suite-i18n.js`. Keep the Athena wordmark, the suite fonts above, and the current article routes.
Use only the two suite A themes; do not add preview variants or a custom form framework. Keep editor content inside its mobile container.

## Public access states

The reader and rail use the same design for visitors and signed-in users. Visitors see Biblioteca and Ingresar; protected downloads, account controls, and admin controls appear only with the existing permissions.
A muted inline notice identifies the public library and provides an Ingresar link. Empty sections use plain text; unavailable articles use the generic “Artículo no disponible” view without disclosing private metadata.
The article editor separates Estado (Borrador/Publicado) from Acceso (Con cuenta/Público). The native access select explains that public access includes images and PDF files; the article list uses the existing text pills.
