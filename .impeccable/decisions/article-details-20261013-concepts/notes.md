The user approved option 1, Por pestañas, on 2026-10-13. The saved answer is `.impeccable/questions/a9bcecfa.answer.json` (`optionId: tabs`, `buildPath: comp`). Details concept seed: `cfa5c67f`. Existing editor seed: `7c06db1d`. The other two options remain unapproved.

All article content and Borrador / Con cuenta values are illustrative. The reference title has a text-selection highlight; this is not brand decoration.

Whole-article save behavior is retained: Guardar cambios saves Markdown, article details, publication/access values, and attachments together. Cerrar retains pending edits in the editor. The concepts do not add autosave or scheduled publication.

Field coverage: article title stays in the main editor. Resumen, Autor, Tipo, Etiquetas, and the immutable Dirección are visible in each concept. Publicación contains Estado, Acceso, Fecha, and read-only Última modificación; tabs or accordions can reveal these in options 1 and 2. Archivos contains secondary Importar Markdown and Adjuntar PDF controls, Solo PDF, and the current upload limits (.md 1 MiB, PDF 25 MiB). Existing file information and removal controls appear when a file is present. Markdown image paste and Insertar imagen remain available in the editor; the panel concept reduces the visible editor area but does not remove these controls. The ordinary Guía concept images omit tool fields. The final build retains Estado herramienta, URL, and descarga in the native Campos de herramienta group. It opens for Tipo Herramienta or an error; staff can also open it for a Guía without losing stored values.

Option 1, Por pestañas: short groups preserve editor width; publication and files require another click.
Option 2, Panel lateral: details stay beside the Markdown editor; the preview has less width. On narrow screens the panel becomes full width.
Option 3, Ficha compacta: frequent metadata, publication, access, and files are visible together; the dialog is denser. On narrow screens its columns stack.

The exact original and repair prompts are stored beside each final image. The final images were made with the built-in image_gen tool. These are bitmap design previews, not working or accessibility-tested interfaces. Small generated copy and editor gutters are illustrative and are not a decision to change the editor. Fields not visible in a selected tab or closed accordion remain part of the form.

At the concept stage, no source files, article data, live database, or deployment files were changed. The earlier directory build history was preserved before the Article Details build started.

The Article Details build starts from this approved comp. The earlier directory build is preserved at `.impeccable/build-history/admin-directory-before-article-details-20261013T101920Z/`, with a verified file-hash record. The existing `editor-before-directory-20261007/` history remains in place. This addition keeps the approved split editor and all current form behavior.

Final implementation: the header holds the title only. Cerrar is in the footer beside Guardar cambios. The native dialog uses the existing Athena tokens, fonts, and 44px controls. Its body scrolls while the footer stays visible. Independent finish review: Ship within Article Details scope, with validation focus and compactness findings resolved. No raster assets ship. Final checks and comparison limits are in `implementation-record.md`. The separate native plates review receipt is still absent. Deployment is pending.
