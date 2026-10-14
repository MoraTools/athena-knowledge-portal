---
version: 1
slug: "guides-library"
primary_target: "server/athena/templates/library.md"
related_targets: ["src/app.js", "src/styles.css"]
---

# Guías library

Mode: Read. Route: `/#/guides`.

## Direction contract

THESIS: Readers find guides in topic groups made from the current tags.

OWN-WORLD: Use Athena's existing black and gold, font stacks, portal rail, spacing, native controls, and focus rules. This is an extension of the current reader identity.

STORY: Search title, author, summary, or tags. Select an exact tag. Use Por temas to open a matching guide from its tag group.

FIRST VIEWPORT: Keep the current Guías header, permitted Nuevo artículo action, search and tag controls, and unique result count. Por temas is the sole view, with a topic jump row and full-width guide rows.

FORM: The current user decision is to remove the view selector and use only Por temas. Keep the current header, search, and exact tag selector. The three new header concepts are unselected and are not implemented. Application code defines the working interface.

QUALITY CONTRACT: Keep current metadata, article routes, access rules, keyboard controls, readable text, and topic navigation. Preserve the current Athena tokens. Review the actual interface on desktop and mobile.

## Decision history and scope

The user initially approved options 4 and 2 on 2026-10-13: "ok implement option 4 and option 2 now". The `1.9.3` decision replaces that two-view layout with Por temas only.

- Prior index, option 4: `.impeccable/mocks/decision/guides-20261013-five/option-4-index.png`.
- Topic layout, option 2: `.impeccable/mocks/decision/guides-20261013-five/option-2-topics.png`.
- Initial selection record: `.impeccable/decisions/guides-20261013-five/selection.json`.

This work uses application code and native browser controls. It does not start or complete an Impeccable build phase. The existing article-details build state and build history belong to separate work.

The shared card-grid and filter-panel descriptions in `DESIGN.md` predate this guides layout. This surface brief defines the Guías override. The root design document, tokens, other surfaces, and build records stay intact.

## Layout and token use

Use the existing `--bg`, `--surface`, `--surface-2`, `--text`, `--muted`, `--accent`, `--accent-soft`, `--line`, and `--line-strong` colors. Use the current `--font-display`, `--font-ui`, `--font-mono`, `--space-*`, and `--content-max` tokens.

Guide titles are white at rest, with no underline. Hover and focus use gold and an underline. Rows use dark surfaces and one bottom rule per guide. The guides do not use a card grid.

Topic rows use 8px vertical and 16px horizontal padding. Each guide has one wrapping footer for tags, status, and optional actions. Action targets remain at least 44px high. Tags use muted text and transparent backgrounds. Status colors stay the same.

On devices with a fine pointer and hover support, hovering a row adds a soft gold fill. Rows also use this fill with `:has(:focus-visible)`. The `color-mix()` blend uses 12% `--accent` with `--surface`. Rows use the normal cursor. The row has no click action or selection state; its links remain the actions.

Topic rows show the title, summary, tags, optional status and links, author, and date. The summary shows up to two lines. The full summary remains in the rendered content.

At a reader width of 600px and below, filter controls and topic metadata stack. Long titles and tags wrap. The page must not scroll horizontally.

## Typography (1.9.3)

Topic rows retain the current type roles. `src/styles.css` is the current type authority. Metadata uses muted text and aligns at the top of the row. Keep these scoped rules stronger than Docsify's paragraph styles.

| Role | Font | Size | Weight | Line height |
| --- | --- | --- | --- | --- |
| Guide title | `--font-ui` | 18px | 700 | 1.3 |
| Summary | `--font-ui` | 16px | 400 | 1.4 |
| Author and date | `--font-ui` | 14px | 400 | 1.4 |
| Actions | `--font-ui` | 14px | 700 | 1.4 |
| Tags | `--font-mono` | 12px | 400 | 1.4 |
| Status | `--font-mono` | 12px | 700 | 1.4 |
| Topic heading | `--font-display` | 28px | 700 | 1.15 |

## Behavior and data contract

Keep all supplied titles, summaries, authors, dates, tags, optional status, and permitted PDF, official-site, and approved-download links. Keep both Helios and Seguridad tags even though option 4 omits them in its image.

The server supplies published records that the reader can access. Visitors see public records. Signed-in readers can also see private records. Drafts stay excluded. Nuevo artículo uses the existing `add_article` permission. Download actions retain the existing sign-in rule.

Search and tag matching ignore case and accents. Tag matching is exact after normalization. The live count counts unique guide records, including when a guide appears in more than one topic. Empty results show the existing Spanish message.

Source records are hidden semantic `article.guide-row` entries in `#guide-source`. Topic groups use these published, access-filtered records. Keep the original metadata and links. The compact index, table scroll hint, view selector, and view storage are removed.

Por temas uses only the current tags, plus Sin etiqueta for untagged records. Build topic rows from the source records. A `WeakMap` holds state for the current library node. Filters hide nonmatching rows and empty groups. Topic links move to the relevant heading. Search and tag values do not persist across route entry.

## Current verification (1.9.3)

The full test suite passed: 123 Django tests, four Node suites, and eight backup tests. Independent source review found no material defects. Browser checks confirmed topic initialization, absent view controls, combined search and exact tag filtering, empty results, unique counts, route re-entry, and public access. Desktop and 390px captures passed visual review with no page overflow. The scoped detector returned `[]`. Evidence is in `.impeccable/review/topics-only-20261013/`. The application version is `1.9.3`; the API contract stays at `1.6.0`. Physical devices were not tested. This record does not claim that native Impeccable build gates passed.

## Verification history (1.9.2)

The full `npm test` run passed: 123 Django tests, four Node suites, and eight backup tests. Actual pointer hover was checked on index and topic rows. Keyboard focus, 44px action targets, and no page overflow at widths of 390px and 320px were verified. Touch emulation confirmed that hover color stays off for a coarse pointer. Muted text has 9.72:1 contrast on the highlighted row. The scoped detector returned `[]`. Independent finish review returned `ship` for this table polish. Physical devices were not tested.

Evidence is in `.impeccable/review/guides-polish-20261013/`: `checks.json`, `index-desktop.jpg`, `index-hover.jpg`, `index-focus.jpg`, `topics-desktop.jpg`, `topics-hover.jpg`, `topics-mobile.jpg`, and `index-320.jpg`.

For `1.9.2`, the application version was `1.9.2` and the API contract stayed at `1.6.0`. Search, filtering, sorting, topic groups, links, and access rules stayed intact. This record does not claim that native Impeccable build gates passed.

## Verification history (1.9.1)

For the `1.9.1` type repair, computed styles matched the type roles in both views. Actions retained a 44px minimum height. No page overflow was found at viewport widths of 1920px, 390px, and 320px. The existing reader-integration check passed. The scoped scans before and after the repair returned `[]`; manual review found the type differences and the Docsify paragraph override. The fresh finish review returned `ship` for this typography repair. Physical devices and actual browser zoom were not verified.

Evidence is in `.impeccable/review/guides-type-20261013/`: `computed.json`, `index-desktop.jpg`, `topics-desktop.jpg`, `index-mobile.jpg`, `topics-mobile.jpg`, and `index-320.jpg`.

## Verification history (1.9.0)

For the `1.9.0` implementation, verification passed: 123 Django tests, four Node suites, and eight backup tests. After the scroll-cue CSS correction, focused Django and reader-integration checks passed. Browser checks covered filters, header sorting, roles, route re-entry, draft exclusion, unique topic counts, and page overflow. The detector returned `[]` for the scoped targets. These full-suite results were not repeated for `1.9.1`.

The independent reviewer first returned `fix` for guide title color and the mobile scroll cue. Both fixes then received `ship`. This verdict covers those two repairs.

The `1.9.0` final captures are in `.impeccable/review/guides-20261013/`:

- `index-desktop-final.jpg` and `topics-desktop-final.jpg`: 1586 × 992.
- `index-mobile-final.jpg` and `topics-mobile-final.jpg`: 390 × 844.
- `index-320-final.jpg`: 320 × 740.

No dependency or runtime image was added for `1.9.0`.
