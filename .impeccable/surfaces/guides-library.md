---
version: 1
slug: "guides-library"
primary_target: "server/athena/templates/library.md"
related_targets: ["src/app.js", "src/styles.css"]
---

# Guías library

Mode: Read. Route: `/#/guides`.

## Direction contract

THESIS: Readers can compare guides in a compact index or find them in groups made from the current tags.

OWN-WORLD: Use Athena's existing black and gold, font stacks, portal rail, spacing, native controls, and focus rules. This is an extension of the current reader identity.

STORY: Search title, author, summary, or tags. Select an exact tag. Compare the matching guides in Índice compacto, or use Por temas to open a guide from its tag group.

FIRST VIEWPORT: Show Guías, the permitted Nuevo artículo action, search and tag controls, the unique result count, and both view buttons. The default is Índice compacto. The table has Guía, Autor, and Fecha columns. Por temas has a topic jump row and full-width guide rows.

FORM: The user approved options 4 and 2 on 2026-10-13: "ok implement option 4 and option 2 now". Application code defines the working interface. The selected images guide its layout.

QUALITY CONTRACT: Keep current metadata, article routes, access rules, keyboard controls, readable text, and local table scrolling. Preserve the current Athena tokens. Review the actual interface on desktop and mobile.

## Selected previews and scope

- Default, option 4: `.impeccable/mocks/decision/guides-20261013-five/option-4-index.png`.
- Selectable view, option 2: `.impeccable/mocks/decision/guides-20261013-five/option-2-topics.png`.
- Selection record: `.impeccable/decisions/guides-20261013-five/selection.json`.

This work uses application code and native browser controls. It does not start or complete an Impeccable build phase. The existing article-details build state and build history belong to separate work.

The shared card-grid and filter-panel descriptions in `DESIGN.md` predate this guides layout. This surface brief defines the Guías override. The root design document, tokens, other surfaces, and build records stay intact.

## Layout and token use

Use the existing `--bg`, `--surface`, `--surface-2`, `--text`, `--muted`, `--accent`, `--accent-soft`, `--line`, and `--line-strong` colors. Use the current `--font-display`, `--font-ui`, `--font-mono`, `--space-*`, and `--content-max` tokens.

Guide titles are white at rest. Hover and focus use soft gold. The active view button uses gold. Rows use thin rules and dark surfaces. The guides do not use a card grid.

The index places the title, summary, tags, and optional links in Guía. Its column widths are 62%, 24%, and 14%. The summary shows one line in the index and up to two lines in topic rows. The full summary remains in the rendered content.

At a reader width of 600px and below, filter controls and topic metadata stack. The index table has a 640px minimum width and scrolls within its own region. Below a guide-library width of 640px, show `Deslice la tabla para ver autor y fecha.` with its direction icon. Keep the scroll region focusable. Long titles and tags wrap. The page must not scroll horizontally.

## Behavior and data contract

Keep all supplied titles, summaries, authors, dates, tags, optional status, and permitted PDF, official-site, and approved-download links. Keep both Helios and Seguridad tags even though option 4 omits them in its image.

The server supplies published records that the reader can access. Visitors see public records. Signed-in readers can also see private records. Drafts stay excluded. Nuevo artículo uses the existing `add_article` permission. Download actions retain the existing sign-in rule.

Search and tag matching ignore case and accents. Tag matching is exact after normalization. The live count counts unique guide records, including when a guide appears in more than one topic. Empty results show the existing Spanish message.

The index starts in server date order. Each of its three headers uses the shared reader sorter with ascending and descending order and `aria-sort`. Keep the original rows and links.

Por temas uses only the current tags, plus Sin etiqueta for untagged records. Build its copies on first use from the published rows supplied to this reader. A `WeakMap` holds state for the current library node. Filters control both views and hide empty groups. Topic links move to the relevant heading. Browser storage saves only the view choice in `athena.guides.view`. Search and tag values do not persist across route entry. The views also work when storage is unavailable.

## Recorded verification

Implementation verification passed: 123 Django tests, four Node suites, and eight backup tests. After the scroll-cue CSS correction, focused Django and reader-integration checks passed. Browser checks covered filters, header sorting, roles, route re-entry, draft exclusion, unique topic counts, and page overflow. The detector returned `[]` for the scoped targets.

The independent reviewer first returned `fix` for guide title color and the mobile scroll cue. Both fixes then received `ship`. This verdict covers those two repairs.

Final captures are in `.impeccable/review/guides-20261013/`:

- `index-desktop-final.jpg` and `topics-desktop-final.jpg`: 1586 × 992.
- `index-mobile-final.jpg` and `topics-mobile-final.jpg`: 390 × 844.
- `index-320-final.jpg`: 320 × 740.

No dependency or runtime image was added. The application version is `1.9.0`; the API contract stays at `1.6.0`. This record does not claim that native Impeccable build gates passed.
