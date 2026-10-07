---
version: 1
slug: "templates-admin-auth-user-directory-html-aa4188d8"
primary_target: "server/athena/templates/admin/auth/user/directory.html"
related_targets: ["server/athena/static/athena/admin-directory.css","server/athena/static/athena/admin-directory.js"]
---

# User directory

Mode: Operate. Users choose an account and manage its profile and access.

Approved concept: `.impeccable/mocks/decision/admin-directory-20261007/roster-inspector.png`.
Approval: user selected option 1 on 2026-10-07.

## Direction contract

THESIS: A comparison table and an inspector make user management one task.

OWN-WORLD: Keep Athena's existing black, neutral surfaces, gold selection and primary action, serif headings, narrow sans controls, and Courier metadata. Reuse the full current rail.

STORY: Search the roster, select a user, inspect profile and access, and save. Username/password management and account protections remain.

FIRST VIEWPORT: The rail stays left. Usuarios, search, and Nuevo usuario sit above a table with Usuario, Acceso, Estado, and Sesión. The selected account's form occupies the right inspector. One gold Guardar anchors the inspector; secondary account actions stay quiet.

FORM: Table split, grounded candidate 7, surface seed 1ef8a187. User approved the first dealt visual concept. On small screens the roster and inspector stack; tables scroll locally when needed.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Translation constraints

The sample users are illustrative. Use actual server data. Keep the current sidebar links; the mock abbreviates them. Preserve native form validation, the role and edit areas, the active flag, username changes, manual password reset, API-key links, individual delete, and self/last-admin safeguards. Email remains disabled with its current explanation. No new account permissions or new bulk actions.
