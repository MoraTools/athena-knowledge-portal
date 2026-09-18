# Athena design system

## Scope

Preserve the existing Spanish knowledge reader and its black-and-gold identity.
Account screens use the same fonts and colors. Administration uses Django's native forms, lists, and controls.

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
| Admin background | `#080808` |
| Admin border | `#555` |
| Error text | `#ffb8ac` |

Gold marks links, primary actions, and active navigation. Dark tones separate sections without decorative shadows.

## Type

The reader declares Sigurd Variable and Rules Variable first, with locally served Cormorant and Archivo Narrow as fallbacks.
Courier Prime is locally served for code and compact labels. Reader body text is 18px with 1.55 line height.
Reader headings use the serif display stack. Account headings scale from 2.6rem to 4rem.
Admin body and inputs use Archivo Narrow at 16px; the ATHENA heading uses Cormorant at 30px.

## Layout

Reader content has a 1080px maximum width; prose is limited to 72ch. The sidebar is 280px wide.
At 1200px and above, article headings appear in a fixed right-hand page tree.
At 768px and below, reader grids, search results, controls, and catalog entries use one column.

Accounts use a centered 650px maximum-width column with 1.5rem side padding.
Inputs and buttons have a minimum height of 48px.

Admin forms retain Django's responsive layout. Flex rows wrap and child containers use zero minimum width.
At 767px and below, `body .aligned .form-row > div` uses `width: 100%; max-width: 100%`.
Preserve this override; Django's default viewport-based width can extend beyond the available space when scrollbars are present.
Admin buttons have a minimum height of 44px.

## Controls and states

Use native inputs, selects, file uploads, and Django validation messages.
Keep visible labels, skip links, focus outlines, and reduced-motion support.
Account and reader focus outlines are 3px gold; admin outlines use soft gold.
Most reader surfaces are square. Preserve Django's native control shapes.

## Boundaries

Preserve Spanish interface copy, the ATHENA wordmark, the existing fonts, and the current article routes.
Do not add a second theme or a custom form framework. Keep editor content inside its mobile container.
