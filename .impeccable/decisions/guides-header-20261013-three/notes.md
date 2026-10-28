# Guides header: three concepts

These images support a header choice. They do not approve or implement an application change.

## Scope and source

- Surface: the Guías header only, in Read mode.
- Sources: PRODUCT.md, DESIGN.md, the supplied header image, and the existing 13-guide snapshot in guides-20261013-five/sharedcontent.json.
- Keep the current Athena colors, serif Guías title, narrow sans-serif controls, and portal rail.
- All three cards have the same size and visual weight. No card is the recommended option.
- This is a narrow header request. It does not require a new visual-world seed.

## Shared content and behavior

Each concept keeps Guías, Buscar guías, the placeholder Título, autor, resumen o etiqueta, the native Etiqueta select with Todas, one 13 resultados count, Índice compacto, Por temas, and Nuevo artículo.

The guide-local search matches title, author, summary, and tags. The tag select keeps exact matching. It stays separate from the rail search. The active view in the shared snapshot is Por temas.

Nuevo artículo uses the existing add_article permission. Keep the current public and signed-in access rules. Do not change authentication or expose restricted guide records.

Keep all content below the header, including the table and topic views, fields, article routes, links, conditional actions, and empty results. Add no features or claims. Do not repeat the result count.

## Three compositions

1. Barra única: put all header controls in one compact horizontal desktop band. This saves height. On a laptop, the controls may need a second line.
2. Búsqueda protagonista: put the compact title and create action above a wide search field. Put the tag and view controls quietly below. Search is easy to find, but the header uses more height.
3. Vistas como pestañas: use underlined Índice compacto and Por temas tabs in the title line or the main top navigation line. Put search and the tag select in a compact line below. The view choice is clear, but tabs can compete with the title.

Each image uses the same content and frame. The image paths are the three comp slots in options.json. The parent supplies and reviews the images.

## Responsive intent

Controls can wrap or stack with the available reader width. Keep visible labels, keyboard access, focus outlines, native input and select behavior, and 44px touch controls. Do not cause page-wide horizontal scroll. The existing table keeps its own scroll area.

## Write boundary

Only options.json, notes.md, and sharedcontent.json in this decision directory belong to this task. Do not change application source, the previous decision, the current build state, build history, or published content. Do not start or reset a build phase.

The board uses comp with no build-path toggle, no canon card, no reroll, and steering enabled. The selected concept still needs an implementation request.

## Checks and limits

The board data must contain three distinct card ids and the exact comp paths. Its shared snapshot must contain 13 guides and one header result count. The local preview server must return the board page.

The images and browser layout are reviewed by the parent after the image slots are filled. These are design previews, not tested interfaces.

## Completed preview review

All three 1942 × 809 images were opened and checked. All header controls, one result count, and the active Por temas state are present. The provenance scan found three rasters and no missing prompts. The comparison page loaded all three images.

Option 1 saves the most header height. Option 2 gives search the most emphasis and uses more vertical space. Option 3 joins view tabs to the heading; its count appears below the filter line. The guide rows in these images provide context only. A chosen implementation must retain the current row content, actions, type scale, and hover behavior.

These are unapproved ImageGen concepts. The exact prompts are saved beside the images and collected in prompts.json. No application source or production state changed. Responsive behavior and interactions have not been implemented or tested.
