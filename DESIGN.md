# Athena design system

## Scope

Preserve the existing Spanish knowledge reader and its black-and-gold identity.
Account screens use the same fonts and colors. Administration keeps Django's native forms and lists, restyled by one control system in `server/athena/static/athena/admin.css`; the user directory (`admin/auth/user/`) is a single list-plus-panel screen on the same tokens.

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
| Strong line (control border) | `#555` |
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
| `--space-3` | `1.5rem` | Card and panel padding, fieldset inset, submit rows, account column side padding, mobile top padding |
| `--space-4` | `2rem` | Section gaps, H2 and H3 top margins, reader and admin page padding, Actualizaciones card padding and post gap |
| `--space-5` | `3rem` | Reader page bottom padding, hero bottom margin |

A card's padding is the only space at its edges: its first child has no top margin and its last child no bottom margin.
A list of cards gets its gap from the grid, never from card margins. The last block of a page has no bottom margin.

## Type

The reader declares Sigurd Variable and Rules Variable first, with locally served Cormorant and Archivo Narrow as fallbacks.
Courier Prime is locally served for code and compact labels. Reader body text is 18px with 1.55 line height.
Reader headings use the serif display stack. Account headings scale from 2.6rem to 4rem.
Admin body and inputs use Archivo Narrow at 16px/1.5; help text is 14px in quiet text. The ATHENA heading uses Cormorant at 30px; page titles use Cormorant at 34px, weight 500.
Admin labels, fieldset and table headers, breadcrumbs, pills, meta, and dates use Courier Prime at 13px, uppercase, 0.06em tracking, in muted or quiet text.
Button text is Archivo Narrow 700 at 13px, uppercase, 0.04em tracking.

## Layout

Reader content has a 1080px maximum width; prose is limited to 72ch. The page starts after the portal rail (see Navigation).
`.markdown-section` pads `--space-4 --space-4 --space-5`; at 768px and below `--space-3 --space-2 --space-4`.
At 1200px and above, article headings appear in a fixed right-hand page tree.
At 768px and below, reader grids, search results, controls, and catalog entries use one column.
Guías and Descargas share one filter panel (`library-controls`): a search field and a select, 44px high, with a live result count.
Actualizaciones cards pad `--space-4` (`--space-3` at 768px and below), with the meta line above a 2rem title, a 17px/1.6 summary at 62ch, and the date badge centred on the first line of the title.

Accounts use a centered 650px maximum-width column padded `--space-4 --space-3`; headings leave `--space-2` below.
Inputs and buttons follow the admin control system: 44px high, 4px radius.

Admin pages pad `--space-4` (`--space-3` at 1024px and below; `--space-2` sides at 767px and below); fieldsets and form rows inset `--space-3`; table modules keep their 16px cell inset.
Admin forms retain Django's responsive layout. Flex rows wrap and child containers use zero minimum width.
At 767px and below, `body .aligned .form-row > div` uses `width: 100%; max-width: 100%`.
Preserve this override; Django's default viewport-based width can extend beyond the available space when scrollbars are present.
Admin controls are 44px high; the header toolbar buttons are 40px at 767px and below.

## Navigation

The reader and the admin share one portal rail: markup in `src/index.html` and `admin/portal_sidebar.html`, styles in `src/assets/rail.css`, behavior in `src/assets/rail.js`.
Its links come from `sidebar_markdown()`: groups Biblioteca, Participar, Cuenta, and Administración (staff only). In the admin, the model pages follow the Administración links.
Each item is a 20px line icon and an uppercase Archivo Narrow 13px label on a 40px row; group labels are gold Courier Prime 11px with 0.18em tracking. The current page is gold with a 2px right bar.

| State | Rail | Behavior |
| --- | --- | --- |
| Expanded | 280px | Group labels, icons and labels; the reader search form sits above the groups. |
| Compact | 72px | Icons only. Group labels fade out and thin rules separate the groups. A tooltip names the item on hover or focus. The current item is a filled tile. The wordmark shrinks to its A, and the search becomes an icon that expands the rail and focuses the field. |
| Hidden | 0 | The rail slides away; a floating menu button at the bottom left brings it back. |

The control at the bottom of the rail switches Contraer and Expandir; its chevron turns. Keys: `]` toggles compact, `[` toggles hidden; both are ignored inside form fields.
One 360ms `cubic-bezier(.2, .8, .2, 1)` transition moves the rail width, the page offset, the labels, and the chevron; reduced motion removes it.
The state is kept in `localStorage` (`athena.rail`), so the choice carries between the reader and the admin.
At 768px and below the rail is an overlay drawer that starts closed and is never stored: the bottom-left menu button opens it, and Escape, a followed link, or a tap outside closes it.

## Controls and states

Use native inputs, selects, file uploads, and Django validation messages.
Keep visible labels, skip links, focus outlines, and reduced-motion support.
Account and reader focus outlines are 3px gold; admin outlines use soft gold.
Most reader surfaces are square. Admin and account controls share one shape: 44px high, 4px radius, 1px `#555` border; buttons pad 0 16px and inputs 0 12px.
Primary buttons (default submit, Añadir, Guardar) are gold with gold-ink text; hover is soft gold. Secondary buttons (other submits, Historial and the other object tools, header tools, Buscar, Ir, Cancelar) are transparent with soft-gold text; hover turns the border gold. Danger buttons (Eliminar) are transparent with `#6b3a33` border and error text. Disabled controls are 50% opacity.
Selects use a gold chevron; checkboxes and radios are 18px with a gold accent. Changelist booleans render as text pills (gold border for true, dashed quiet border for false), never icons.
All admin colors, fonts, spacing, and control sizes are custom properties in `admin.css`; the directory stylesheet consumes them and defines none. The shared rail stylesheet defines only its own sizes and timing (`--rail-*`) and reads the page tokens.

## Boundaries

Preserve Spanish interface copy, the ATHENA wordmark, the existing fonts, and the current article routes.
Do not add a second theme or a custom form framework. Keep editor content inside its mobile container.
