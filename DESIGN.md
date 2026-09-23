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

## Type

The reader declares Sigurd Variable and Rules Variable first, with locally served Cormorant and Archivo Narrow as fallbacks.
Courier Prime is locally served for code and compact labels. Reader body text is 18px with 1.55 line height.
Reader headings use the serif display stack. Account headings scale from 2.6rem to 4rem.
Admin body and inputs use Archivo Narrow at 16px/1.5; help text is 14px in quiet text. The ATHENA heading uses Cormorant at 30px; page titles use Cormorant at 34px, weight 500.
Admin labels, fieldset and table headers, breadcrumbs, pills, meta, and dates use Courier Prime at 13px, uppercase, 0.06em tracking, in muted or quiet text.
Button text is Archivo Narrow 700 at 13px, uppercase, 0.04em tracking.

## Layout

Reader content has a 1080px maximum width; prose is limited to 72ch. The sidebar is 280px wide.
At 1200px and above, article headings appear in a fixed right-hand page tree.
At 768px and below, reader grids, search results, controls, and catalog entries use one column.

Accounts use a centered 650px maximum-width column with 1.5rem side padding.
Inputs and buttons follow the admin control system: 44px high, 4px radius.

Admin forms retain Django's responsive layout. Flex rows wrap and child containers use zero minimum width.
At 767px and below, `body .aligned .form-row > div` uses `width: 100%; max-width: 100%`.
Preserve this override; Django's default viewport-based width can extend beyond the available space when scrollbars are present.
Admin controls are 44px high; the header toolbar buttons are 40px at 767px and below.

## Controls and states

Use native inputs, selects, file uploads, and Django validation messages.
Keep visible labels, skip links, focus outlines, and reduced-motion support.
Account and reader focus outlines are 3px gold; admin outlines use soft gold.
Most reader surfaces are square. Admin and account controls share one shape: 44px high, 4px radius, 1px `#555` border; buttons pad 0 16px and inputs 0 12px.
Primary buttons (default submit, Añadir, Guardar) are gold with gold-ink text; hover is soft gold. Secondary buttons (other submits, Historial and the other object tools, header tools, Buscar, Ir, Cancelar) are transparent with soft-gold text; hover turns the border gold. Danger buttons (Eliminar) are transparent with `#6b3a33` border and error text. Disabled controls are 50% opacity.
Selects use a gold chevron; checkboxes and radios are 18px with a gold accent. Changelist booleans render as text pills (gold border for true, dashed quiet border for false), never icons.
All admin colors, fonts, and control sizes are custom properties in `admin.css`; the sidebar and directory stylesheets consume them and define none.

## Boundaries

Preserve Spanish interface copy, the ATHENA wordmark, the existing fonts, and the current article routes.
Do not add a second theme or a custom form framework. Keep editor content inside its mobile container.
