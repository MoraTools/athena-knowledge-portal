---
version: 1
slug: "tes-admin-athena-article-change-form-html-a26103cd"
primary_target: "server/athena/templates/admin/athena/article/change_form.html"
related_targets: ["server/athena/static/athena/article-editor.css","server/athena/static/athena/article-editor.js"]
---

# Article editor

Mode: Operate. Staff write Markdown and inspect the reader output. Keep every article setting, import, upload, permission, and save operation. Publication and anonymous access are separate.

## Direction contract

THESIS: A Split desk puts writing and reader output in the first viewport. Settings stay in a native details dialog.

OWN-WORLD: Keep Athena's black surfaces, gold primary action, thin rules, established fonts, and native inputs. Staff use the portal at a desk in normal room light.

STORY: The editor sees the current publication and access state, writes Markdown, inspects the result, and saves explicitly.

FIRST VIEWPORT: A compact 72px rail and quiet header sit above a full-width title. Balanced source and preview panes fill the remaining height. Guardar is the single gold action at the top right. The image helper spans both panes in a shared footer.

FORM: Split desk, option 2. Seed 7c06db1d. Approved comp: .impeccable/mocks/decision/editor-split.png. Comp text defects are corrected; native textarea wrapping has no misleading line numbers.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Release acceptance

On 2026-09-29, after viewing the finished editor and the disclosed comparison limits, the user requested: "commit push and deploy to the vps". This accepts the displayed version, including the native 44px controls and established Athena colors. Independent review found no material UI defect. The automated hero comparison scored 81%; its control checks remain open. No automatic check was forced or reported as passed.

## Article Details addition, 2026-10-13

THESIS: A compact centered details dialog uses Información, Publicación, and Archivos tabs. Keep the approved Split desk editor.

OWN-WORLD: Use existing Athena dark surfaces, fonts, thin rules, native fields, and 44px controls. The active tab has a gold underline. No raster asset is needed.

STORY: Staff edit metadata, publication, access, and files. Cerrar keeps pending edits. Guardar cambios saves the whole article. Existing errors and permissions control what is shown.

FIRST VIEWPORT: Información opens first. A title sits above three tabs and a quiet status strip. Resumen spans the dialog. Autor and Tipo share a row. Etiquetas, the quiet Dirección, and the retained Campos de herramienta group follow. Cerrar is in the footer only, beside the single visible gold Guardar cambios action. The dialog is at most 576px wide. At narrow widths the fields stack and the body scrolls while the footer stays visible.

FORM: Option 1, Por pestañas. The explicit answer is `.impeccable/questions/a9bcecfa.answer.json` (`optionId: tabs`, `buildPath: comp`). Approved comp: `.impeccable/mocks/decision/article-details-20261013-concepts/option-1-tabs.png`. Details concept seed: `cfa5c67f`. Existing editor seed: `7c06db1d`. The comp's article text, gutters, and abbreviated background controls are illustrative. Keep current field values, help, errors, tool fields, upload limits, image insertion, stable URLs, and permission checks. When the dialog closes, the editor's top save action remains available.

FINISH: Independent finish review: Ship within Article Details scope. The validation focus and dialog compactness findings are resolved. The existing DESIGN.md covers this extension. No raster assets ship. The native plates phase still needs its separate review receipt; no gate was forced.

Final evidence: `.impeccable/review/article-details-20261013/layout-checks.json` records 18 passing tab and viewport checks at widths 320, 390, 1264, 1280, 1440, and 1586px. Every case has a visible footer and no horizontal overflow. `focus-confirmation.json` records title-error focus and return to Detalles after a normal close. The final desktop dialog is 576 × 796.9px, including the retained tool group. Full-comp (51%) and dialog-only (72%) comparison scores remain advisory; sample content, pinned fonts, and crop bounds differ. See the final evidence and limits in `.impeccable/decisions/article-details-20261013-concepts/implementation-record.md`.
