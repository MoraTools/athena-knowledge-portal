# Athena design system

## Scope

Preserve the existing Spanish knowledge reader and its black-and-gold identity.
Mi cuenta is a reader page (`/#/account`, served as `/account.md`); the password pages use the same rail and widths. Only sign-in is a standalone centred page. Administration keeps Django's native forms and lists, restyled by one control system in `server/athena/static/athena/admin.css`; the user directory (`admin/auth/user/`) uses a semantic roster table and inspector on the same tokens.
Ordinary authenticated admin pages omit the top `#header` and start with breadcrumbs and content.
The directory starts with its own Usuarios task heading and omits breadcrumbs and the duplicate global title.

## Tokens

| Token | Value |
| --- | --- |
| Background | `#000` |
| Surface | `#101010` |
| Secondary surface | `#191919` |
| Text | `#fff` |
| Muted text | `#d0d0d0` |
| Accent | `#ffb900` |
| Soft accent | `#ffcf40` |
| Code | `#ffe08a` |
| Line | `#2a2a2a` |
| Strong line (control border) | `#666` |
| Quiet text | `#8f8f8f` |
| Gold ink (text on gold) | `#1a1400` |
| Error text | `#ffb8ac` |

Gold marks links, primary actions, and active navigation. Dark tones separate sections without decorative shadows.

## Spacing

One scale, defined in `src/styles.css` `:root` and mirrored in `admin.css` `:root`. Use a step, not a new number.

| Token | Value | Use |
| --- | --- | --- |
| `--space-1` | `.5rem` | Label to control, meta line to title, heading 3 bottom margin |
| `--space-2` | `1rem` | Gaps in card lists and grids, H1 and H2 bottom margins, mobile side padding, admin form-row vertical padding |
| `--space-3` | `1.5rem` | Card and panel padding, fieldset inset, submit rows, account column side padding, reader page padding |
| `--space-4` | `2rem` | Section gaps, H2 and H3 top margins, admin page padding, Actualizaciones card padding and post gap |
| `--space-5` | `3rem` | Reader page bottom padding, hero bottom margin |

A card's padding is the only space at its edges: its first child has no top margin and its last child no bottom margin.
A list of cards gets its gap from the grid, never from card margins. The last block of a page has no bottom margin.

## Type

The reader declares Sigurd Variable and Rules Variable first, with locally served Cormorant and Archivo Narrow as fallbacks.
Courier Prime is locally served for code and compact labels. Reader body text is 18px with 1.55 line height.
Reader headings use the serif display stack. Page headings scale from 2.2rem to 4rem based on the available reader width. Home's Athena heading scales from 3rem to 6rem.
Admin body and inputs use Archivo Narrow at 16px/1.5; help text is 14px in quiet text. Page titles use Cormorant at 34px, weight 500.
The admin sign-in header shows ATHENA in the display voice and "Administración" in the label voice.
Admin labels, fieldset and table headers, breadcrumbs, pills, meta, and dates use Courier Prime at 13px, uppercase, 0.06em tracking, in muted or quiet text.
Button text is Archivo Narrow 700 at 13px, uppercase, 0.04em tracking.
The directory has local display-size overrides: Usuarios is 47px/56px; the inspector heading is 44px/1.2. At 767px and below, these become 40px/48px and 36px/1.2. Its roster headers use Archivo Narrow at 14px, weight 500.

## Layout

One width rule for the reader, the account pages and the admin: `--content-max` is 1320px (reader and admin `:root`).
Content starts at the left content edge beside the portal rail and fills the space up to `--content-max`. Above a 1600px viewport it is centred in the space beside the rail, which stays fixed on the left.
The reader reserves the rail width once on `div#main`. Docsify's `.content` stays in normal flow without its theme's sidebar offset or transform. `div#main` is the named `reader` container, so component layouts use the width that remains beside the rail.
Prose, cards, timelines, grids, tables and the downloads catalog all fill the content width; only `--content-max` (1320px, centred above 1600px) bounds them.
`.library-grid` uses `repeat(auto-fill, minmax(min(100%, 320px), 1fr))`, so cards fill available columns and fit containers narrower than 320px.
No page scrolls horizontally from 320px to 2560px; a table that is too wide scrolls inside its own container. Long titles, tags, and filenames wrap. Grid children can shrink within their column.
Reader tables use Surface for rows, Secondary surface for headers, and 1px Line rules below cells. Cells align at the top with 4px vertical and 16px side padding; code identifiers stay on one line.
In sortable reader tables, a column with body text longer than 60 characters has a 32ch minimum width. Long descriptions wrap inside the table's local scroll area; short tables keep their natural widths.
`.markdown-section` pads `--space-3 --space-3 --space-5`; at 768px and below `--space-3 --space-2 --space-4`.
When the available reader container is at least 1200px wide, article headings appear in a 216px sticky right-hand page tree. The article and tree share one grid and the page gutters. Below that width, the same native details tree appears above the article and starts closed. Its toggle stays available in both layouts. A width change restores the default only when the tree changes between the side and inline layouts; reader choices stay within the same layout.
At reader widths of 900px and below, the home hero and account panels stack. At 600px and below, portal cards, search results, filter controls, and catalog entries use one column. The feed keeps each date above its post at this width, so the date column does not reduce the reading space.
Guías and Descargas share one filter panel (`library-controls`): a search field and a select, 44px high, with a live result count.
Actualizaciones cards pad `--space-4` (`--space-3` at a reader width of 600px and below), with the meta line above a 2rem title and a 17px/1.6 summary. In the date-column layout, the badge is centred on the first line of the title.

Mi cuenta shows the username, a role and last-session line, then Sesión and Mis claves de API side by side (1:2) above a 900px reader width and stacked below; administrators also get an Administración row of shortcuts.
The password pages pad like `.markdown-section`; their form is at most 40rem wide.
Sign-in uses a centred 650px column padded `--space-4 --space-3`; headings leave `--space-2` below.
Inputs and buttons follow the admin control system: 44px high, 4px radius.

Admin pages use the named `admin-page` container, which measures the width beside the rail. They pad `--space-4` (`--space-3` at 1024px and below; `--space-2` sides at 767px and below); fieldsets and form rows inset `--space-3`; ordinary table body cells use 4px vertical and 16px side padding. Row-control cells use 4px vertical and 12px side padding.
`#content` follows the width rule. Change forms use the full width: aligned textareas fill the row beside the 180px label column.
When the changelist area is narrower than 1200px (a container query, so the rail's width counts), the filter moves under the table with its groups side by side.
Admin forms retain Django's responsive layout. Flex rows wrap and child containers use zero minimum width. At an available admin width of 1000px and below, recent actions stack below the dashboard. Object tools move below the title at 900px and below; aligned labels stack above their fields at 720px and below.
At 767px and below, `body .aligned .form-row > div` uses `width: 100%; max-width: 100%`.
Preserve this override; Django's default viewport-based width can extend beyond the available space when scrollbars are present.
Admin form controls are 44px high.
The article editor shows Markdown and its preview side by side above an available 900px width. At 900px and below, its existing Markdown and preview tabs select the pane. Toolbar, pane, and dialog headers wrap; read-only values, errors, and filenames wrap within the form.
API key creation fills the content width and its actions wrap. Standalone sign-in aligns the wordmark and form within the same 650px column.
The directory keeps the 1320px cap and full 280px rail. Its wide grid divides the roster and inspector 1.55:1, with a 360px minimum inspector width. At a content-container width of 1140px and below, the two sections stack.
The roster table has a 620px minimum width and scrolls inside its own container. A scroll cue appears only when the roster interior is below 620px wide.
Roster cells have no vertical padding. Username and header links have a 40px minimum height (44px for a coarse pointer). Roster rows with one line measure 41px on desktop and 45px for a coarse pointer. Keep the thin row rules, existing text size, pills, status marks, selection, and focus outlines.

## Navigation

The reader and the admin share one portal rail: markup in `src/index.html` and `admin/portal_sidebar.html`, styles in `src/assets/rail.css`, behavior in `src/assets/rail.js`.
Its links come from `sidebar_markdown()`: groups Biblioteca, Participar, Cuenta (Mi cuenta, `/#/account`), and Administración (staff only). In the admin, the model pages follow the Administración links. On `/accounts/` pages Mi cuenta is current.
The rail carries the ATHENA wordmark. Hiding the rail does not add an admin header. Admin sign-in keeps the ATHENA link and "Administración" section label; the password pages keep the sign-in header's wordmark.
The rail provides site navigation and API para agentes. Mi cuenta keeps Cambiar contraseña and Cerrar sesión; logout uses a CSRF-protected POST form.
Each item is a 20px line icon and an uppercase Archivo Narrow 13px label on a 40px row (44px for a coarse pointer); group labels are gold Courier Prime 11px with 0.18em tracking. The current page is gold with a 2px right bar.

| State | Rail | Behavior |
| --- | --- | --- |
| Expanded | 280px | Group labels, icons and labels; the reader search form sits above the groups. |
| Compact | 72px | Icons only. Group labels fade out and thin rules separate the groups. A tooltip names the item on hover or focus. The current item is a filled tile. The wordmark shrinks to its A, and the search becomes an icon that expands the rail and focuses the field. |
| Hidden | 0 | The rail slides away; a floating menu button at the bottom left brings it back. |

The control at the bottom of the rail switches Contraer and Expandir; its chevron turns. Keys: `]` toggles compact, `[` toggles hidden; both are ignored inside form fields.
One 360ms `cubic-bezier(.2, .8, .2, 1)` transition moves the rail width, the page offset, the labels, and the chevron; reduced motion removes it.
The state is kept in `localStorage` (`athena.rail`), so the choice carries between the reader and the admin.
At 1024px and below the rail is an overlay drawer that starts closed and is never stored: the bottom-left menu button opens it, and Escape, a followed link, or a tap outside closes it.
On the directory at 1024px and below, `.rail-reveal` occupies a normal-flow row above the content, so it cannot cover fields. The shared overlay opening and closing behavior stays the same.

## Controls and states

Use native inputs, selects, date and calendar controls, file uploads, and Django validation messages.
The article Markdown textarea supports pasted PNG/JPEG/WebP images and a secondary **Insertar imagen** button below the field.
Keep its native text behavior. Image insertion preserves selected text; progress and upload errors appear beside the button with a live status.
Save controls stay disabled during upload. The helper wraps below the textarea on narrow screens and uses the existing control and spacing tokens.
Keep visible labels, skip links, focus outlines, and reduced-motion support.
Account and reader focus outlines are 3px gold; admin outlines use soft gold.
Most reader surfaces are square. Admin and account controls share one shape: 44px high, 4px radius, 1px `#666` border; buttons pad 0 16px and inputs 0 12px.
Primary buttons (default submit, Añadir, Guardar) are gold with gold-ink text; hover is soft gold. Secondary buttons (other submits, Historial and the other object tools, Buscar, Cancelar) are transparent with soft-gold text; hover turns the border gold. Danger buttons (Eliminar) are transparent with `#6b3a33` border and error text. Disabled controls are 50% opacity.
Changelists end with an unlabeled controls column of 36px square icon links (44px for a coarse pointer; Ver or Descargar, Editar, Eliminar) in the secondary style, Eliminar in the danger colors; `title` and `aria-label` name each one. Regular rows with one line and these controls measure 45px. The column stays pinned to the right edge when the table scrolls. Eliminar opens Django's confirmation page. Existing Django header sorting stays native.
Django's action select is hidden. Checking rows shows a sticky bar above the table (count, Eliminar seleccionados, Cancelar; 36px buttons) that runs `delete_selected` through the hidden action form, so the confirmation page still protects it (`static/athena/admin-list.js`).
Selects use a gold chevron; checkboxes and radios are 18px with a gold accent. Changelist booleans render as text pills (gold border for true, dashed quiet border for false), never icons.
All admin colors, fonts, spacing, and control sizes are custom properties in `admin.css`; the directory stylesheet consumes them and defines none. The shared rail stylesheet defines only its own sizes and timing (`--rail-*`) and reads the page tokens.

Ordinary reader tables, including account API keys, API reference tables, and simple article tables, receive native header buttons after rendering. Buttons have a 40px minimum height (44px for a coarse pointer), drawn direction indicators, and `aria-sort`. The initial author or server order stays until a header is selected; each header alternates ascending and descending order. Text sorting uses numeric-aware Spanish comparison. Explicit ISO values or `time[datetime]` provide date order; account expiry cells carry ISO values. Sorting moves the existing rows and keeps links, forms, and the footer. Setup runs once per table. Merged cells, multiple header rows, nested tables, presentation tables, interactive headers, and `data-sortable="false"` tables retain their existing behavior.

The directory roster has Usuario, Acceso, Estado, and Sesión columns. Actual accounts start in ascending username order. All four headers are native GET links that alternate ascending and descending order, with drawn direction indicators and `aria-sort`. Equal roles, statuses, and session dates keep stable username order; accounts with no session date stay last in both date orders. Username links select the inspector; the selected row has a gold outline and dark gold fill. Role and active status stay separate. Sesión shows the actual `last_login` date and time, or `nunca`.
Search uses a native GET form and a live filter; both ignore case and accents. Usernames, full names, and email values are searchable. Full names also appear in username tooltips.
Native search, selection, new user navigation, and saving retain the submitted search and sort parameters. Header links retain the current selection; the live filter also updates their search query.
The inspector uses native role radios and an active checkbox. The administrator role shows Permisos de edición; hiding that area does not reset checked values. Native field and form errors stay visible, including edit-area errors.
When editing is permitted, one full-width gold Guardar button is the primary action. Manual password reset, API keys, and individual deletion use quieter links with 20px line icons and thin separators; the separators are horizontal on mobile. Native deletion confirmation and self/last-admin protections remain.
Email is disabled; an empty field shows `No disponible`. The short visible help is "Servicio de correo no configurado." The full existing reason remains in the tooltip and accessible help. Existing email values stay; new email values are not saved.

## Boundaries

Preserve Spanish interface copy, the ATHENA wordmark, the existing fonts, and the current article routes.
Do not add a second theme or a custom form framework. Keep editor content inside its mobile container.

## Public access states

The reader and rail use the same design for visitors and signed-in users. Visitors see Biblioteca and Ingresar; protected downloads, account controls, and admin controls appear only with the existing permissions.
A muted inline notice identifies the public library and provides an Ingresar link. Empty sections use plain text; unavailable articles use the generic “Artículo no disponible” view without disclosing private metadata.
The article editor separates Estado (Borrador/Publicado) from Acceso (Con cuenta/Público). The native access select explains that public access includes images and PDF files; the article list uses the existing text pills.
