# Guías: comparación de cinco estructuras

These are concept images for a user decision. They do not approve or implement an application change.

## Scope and source

- Surface: Guías, Read mode, inside the current Athena identity.
- Sources: PRODUCT.md, DESIGN.md, server/athena/templates/library.md, src/app.js filterGuides, src/styles.css, the supplied Guías screenshot, and the parent's read-only catalog query.
- Existing palette: #000000, #101010, #191919, #ffffff, #d0d0d0, #ffb900.
- Keep Athena's serif headings, narrow sans-serif body, compact monospaced labels, and current portal rail.
- Seed: 838efd9d. Candidate order: compact table; tag rail; list with metadata preview; compact cards; expandable rows; tag groups; search-led results.
- The seed dealt candidates 5, 6, and 3. The user asked for five options. Candidates 1 and 4 complete this board.
- Display order: expandable rows; tag groups; list with metadata preview; compact table; compact cards. All five cards have equal visual salience.

## Field and behavior parity

All options retain title, summary, author, date, current tags, and the link to the existing article. Summary placement and visible length vary by option. The preview option shows metadata and summary only, with no invented article body.

Keep the guide query across title, author, summary, and tags; exact tag filtering; result count; and empty results. The portal rail's global search remains distinct from the Guías filter. Do not add AI search, favorites, new status fields, or personalization.

Nuevo artículo depends on the existing add_article permission. Anonymous readers see published public articles. Signed-in readers can also see published private articles. Keep access filtering before the page renders. Preserve existing optional status, PDF, official-site, and approved-download links where the actual guide has those fields. Do not infer those fields from titles.

Por temas uses the existing tags. It adds no taxonomy. One guide can occur in several sections. A future implementation must count unique guide records in the result count.

## Responsive intent

- Lista desplegable: full-width rows wrap; an open summary stays below its title.
- Por temas: sections and rows use one column on narrow screens; long tags wrap.
- Lista con ficha: the two panes stack below the existing content-width threshold; the summary stays next to its selected guide.
- Índice compacto: narrow screens use the current local table scroll pattern; no page-wide horizontal scroll.
- Tarjetas compactas: columns reduce with the available content width and reach one column on narrow screens.
- Search and tag controls stack on narrow screens. Visible labels, keyboard controls, focus outlines, and 44px touch controls remain required.

## Write boundary

The board files are in .impeccable/decisions/guides-20261013-five/. Its images are in .impeccable/mocks/decision/guides-20261013-five/. Do not change application source, current build state, build history, other decisions, or published content. Do not start or reset a build phase. The selected concept still needs an implementation request.

## Preview review

All five 1586 × 992 images were inspected. Their prompt sidecars remain unapproved, and the provenance scan found no missing prompts. These are desktop composition previews, not tested interfaces. The generated index image omits the Helios row's two tags; a selected implementation must retain both. All existing metadata and conditional actions remain required, including content outside the pictured viewport.
