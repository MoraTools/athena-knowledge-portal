# Article Details tabs, 2026-10-13

The user approved option 1, `tabs`, with `buildPath: comp`. The answer is `.impeccable/questions/a9bcecfa.answer.json`. Details concept seed: `cfa5c67f`. Existing editor seed: `7c06db1d`. The editor surface brief has this addition. The earlier Split desk contract and release acceptance stay in place.

## Preservation

The full directory build was copied to `.impeccable/build-history/admin-directory-before-article-details-20261013T101920Z/` before the supported `build-phase start --reset`. All eight original files match the hashes in `preservation.json`. The earlier `editor-before-directory-20261007/` history stays in place. Stale directory scaffold and font proofs were removed from the current build after their archive hashes were checked.

The approved image is unchanged. File SHA-256: `9dc813f97f5b7b0587440fc3f04db04426d7c8242525504c8e38f0e70360516e`. Its sidecar now records the explicit approval. No source or deployment file was changed by this record task.

## Measurement

The full comp is 1586 × 992. `.impeccable/build/regions.json` and `.impeccable/build/spec.json` contain 47 native regions and no raster regions. All 20 text-measurement commands completed; 19 regions have pixel measurements. The single-glyph compact A wordmark has no type fingerprint and stays unchanged. The second map inspection has no errors or partial masks. It reports three background coverage hints (`B0`, `A2`, `A4`). These hints are not proof of missing controls.

The dialog bounds in the full comp are `x: 506, y: 123, w: 577, h: 757`. Its native field inset is 27px. Main fields span 523px. The Autor and Tipo inputs each span 246px. Controls are 44px high, except the Resumen textarea (74px) and the comp close icon (34px). The implemented close control must retain the existing 44px hit target.

The separate dialog comparison is reference evidence. `.impeccable/review/article-details-20261013/dialog-reference.png` is the exact `details-dialog` crop, made with the native crop command at scale 1. It does not replace the approved comp and must not ship as an asset. The measured dialog-only spec is `.impeccable/review/article-details-20261013/dialog-comparison/.impeccable/build/spec.json`. Its 25 native regions and 10 text measurements have no map errors, partial masks, or uncovered-ink hints.

The dialog title has a measured 23.9px cap height. `font-match` ranked the existing `Cormorant:500` candidate at 34px. The engine selected `Cardo:400` at 31px. Keep the pinned existing font. The native rank result stays unchanged as evidence. The full-comp gate selected the sample preview heading as its lead; its rank result is comparison data, not a change to the editor.

## Scope and state

The final native dialog uses Información, Publicación, and Archivos tabs. Información opens first. It keeps current values, help, errors, permissions, tool fields, upload limits, stable URLs, image insertion, and whole-article save behavior. The header holds the title only. Cerrar keeps pending edits and is in the footer only, beside the single visible gold Guardar cambios action. The editor save remains available after the dialog closes. Campos de herramienta stays in the form, opens for tool articles or errors, and keeps values for other article types. Generated background text, gutters, and control abbreviations are sample content.

`.impeccable/build/state.json` is the current native state (`sessionId: article-details-20261013-tabs`). The spec phase passed. The plates phase stays open. Its material gate says `no plates owed`, but `advance` exits 2 because the separate plan and asset review receipt is absent. The prior explicit tabs approval does not satisfy that tool receipt. No gate was forced, no review session was created, and no receipt was written or submitted. `.impeccable/review/components.json` is only the native plan packet: 0 assets, 1 plan item, 46 code regions, and no flags. The parent continues under the existing user authorization and will report this external-tool limit.

## Final evidence

Independent finish review: Ship within Article Details scope. The validation focus and dialog compactness findings are resolved. The final desktop dialog is 576 × 796.9px, including the retained tool group. Its body scrolls when needed and the footer stays visible.

The parent verified these checks:

- Before the final fixes: 120 Django tests, four Node suites, and eight backup tests passed. After the JavaScript and CSS fixes: the focused Node suite and four ArticleEditor Django tests passed.
- `layout-checks.json` records 18 passing cases: all three tabs at 320 × 640, 390 × 844, 1264 × 720, 1280 × 720, 1440 × 900, and 1586 × 992. Every case fits the dialog, keeps the footer visible, and has no page, dialog, or body horizontal overflow.
- Browser checks covered whole-article saving, read-only permissions, the no-JavaScript fallback, error focus and tab selection, Cerrar and keyboard focus return, ArrowLeft, and Home. `focus-confirmation.json` confirms that a missing title closes the dialog and focuses `id_title`; a normal close returns focus to Detalles.
- `detector.json` has no findings. Final captures are `comp-size.jpg`, `dialog-actual.jpg`, `info-1440.jpg`, `info-1280.jpg`, `info-1264.jpg`, `info-390.jpg`, `info-320.jpg`, and `files-320.jpg` under `.impeccable/review/article-details-20261013/`.

The final source and captures use the existing Athena colors, fonts, spacing, native controls, and responsive rules. This is a local extension. `DESIGN.md` is unchanged. `.impeccable/design.json` is absent and was not created. No raster asset ships.

## Limits and pending state

The final full-comp comparison scored 51%; the dialog-only comparison scored 72% (`drift`). The parent inspected the side-by-side and the three worst dialog pairs. These are advisory scores, not passing gates or proof of missing controls. The full comp uses sample background content and a different editor layout. The dialog comparison top-aligns and crops the 796.9px actual capture to the 757px reference height, so its save-action pair is blank. The full actual capture and all 18 footer checks show that action. The live fixture says Publicado where the sample says Borrador. The Tipo select is present; its native border and pinned font differ from the generated comp. Logs and pairs are under `.impeccable/review/article-details-20261013/` (`full-diff.log`, `dialog-diff.log`, and `diff/dialog/side-by-side.png`).

The native plates phase still needs its separate plan and asset review receipt. `build-phase finish --disposition ship` was refused because plates and subsequent phases remain open. The manual finish review does not supply that receipt or close those phases. No gate or receipt was forced or fabricated. Deployment is pending. This documentation task did not run new application tests or deployment checks; it checked the final source, saved evidence, and desktop and narrow-screen captures.
