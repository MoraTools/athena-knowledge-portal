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

## Compact table refinement (2026-10-07)

User requirement: Use slim, normal table rows to show more users. Make headers clickable for ordering. Apply the same changes wherever the existing tables support them.
This direct request replaces the approved mock's tall roster rows. The approved table and inspector concept and its provenance above remain current.

- Directory cells have zero vertical padding. Username and header links have a 40px minimum height (44px for a coarse pointer). Rows with one line measure 41px, previously 77px; rows for a coarse pointer measure 45px. Form controls remain 44px high. Keep the existing fonts, pills, status marks, thin row rules, selected row, and focus outlines.
- All four headers use native GET links with drawn direction indicators and `aria-sort`. The server accepts only `username`, `role`, `status`, and `session`, with `asc` or `desc`. Equal values keep stable username order. Accounts with no `last_login` stay last in either session order.
- Native search, user selection, new user navigation, and saving retain submitted search and sort parameters. Header links retain the current selection. Live filtering updates the header links' `q` parameter before navigation.
- Shared Django lists keep their native sorting. Normal body and row-control cells have 4px vertical padding; 36px row icons give measured 45px regular rows and grow to 44px for a coarse pointer. Forms, date controls, and calendars keep native behavior.
- Ordinary reader tables use 4px vertical cell padding and native sortable header buttons with a 40px minimum height (44px for a coarse pointer). Initial author or server order stays until a header is selected. Sorting uses numeric-aware Spanish text comparison and explicit ISO or `time[datetime]` dates; account expiry cells carry ISO values. Existing row, link, and form nodes and table footers remain. Setup runs once per rendered table. Merged cells, multiple header rows, nested or presentation tables, interactive headers, and `data-sortable="false"` tables keep their existing behavior.
- Reader columns with body text longer than 60 characters receive `data-long-text` and a 32ch minimum width. Long descriptions wrap readably in the local table scroll area; short tables keep their natural widths.

Source evidence: `server/athena/admin.py`, `server/athena/templates/admin/auth/user/directory.html`, `server/athena/static/athena/admin-directory.css`, `server/athena/static/athena/admin-directory.js`, `server/athena/static/athena/admin.css`, `src/styles.css`, `src/app.js`, and `server/athena/templates/account.md`.
Finish review: The mobile description width repair received a `ship` verdict. The earlier review matched the other requested table behavior. This records the compact table refinement review.
