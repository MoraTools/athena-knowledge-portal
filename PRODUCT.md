# Athena Knowledge Portal

## Product

Athena is a curated internal knowledge portal for Automation Anywhere team members. It publishes practical guides, tools, updates, downloads, and source PDFs in one searchable place.

The portal is Spanish-first. Project collaboration and implementation notes can remain in English.

## Audience and goals

- Help team members find reliable operational knowledge quickly.
- Keep useful documentation easy to read, share, and contribute.
- Support a library of 100 to 500 guides without turning navigation into a long directory.
- Keep Jeiser Vargas as the editorial reviewer for contributed documents.

## Content model

Markdown remains the authored content format. The VPS database is the source of truth for articles and attached PDFs. Athena supports pages, guides, tools, announcements, releases, downloads, and PDF-only guide records. OneDrive retains approved package downloads; imported documents are managed in Athena.

Existing article routes must remain stable.

## Technical constraints

- Docsify reader served by Django on a DigitalOcean VPS in NYC3; $12/month base Droplet budget.
- Cloudflare cost ceiling: USD 0.
- No Workers, Functions, R2, or metered Cloudflare feature. Django and SQLite provide accounts, article management, and REST access on the VPS.
- Prefer native browser features and existing project code over new dependencies.
- Article lists and indexes are generated from published database records at request time. Existing approved package catalogs are preserved.
- Search and filtering run in the browser using the authenticated search index.
- Admins can add/remove users, rename accounts, reset passwords, edit/upload Markdown and PDFs, and publish drafts.
- Agents use scoped, expiring bearer keys and the documented REST API.

## Experience principles

- Search is the primary way to enter the library.
- Preserve Athena's incumbent visual system and improve it through clear hierarchy, strong text contrast, and restrained interaction.
- Prefer readable text and generous spacing over decorative borders or dense controls.
- Desktop and mobile experiences must remain keyboard accessible.

## Search decisions

- Replace the Docsify dropdown results with a dedicated, shareable route such as `#/search?q=recorder`.
- Search all Athena content: guides, tools, updates, downloads, and PDF-only entries.
- Each result shows its title, content type, summary, author, date, tags, best matching excerpt, and a direct link to the matching section when available.
- Results update while the user types and the query stays synchronized with the URL.
- Include one simple content-type filter.
- Matching is case-insensitive and accent-insensitive.
- Do not add typo correction or fuzzy matching until real usage shows it is necessary.
