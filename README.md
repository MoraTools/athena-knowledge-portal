# Athena Knowledge Portal

Athena runs on a DigitalOcean VPS with Django, SQLite, Gunicorn, and Caddy.
The Spanish reader keeps its existing Docsify routes. All knowledge content requires a user account.

## Production

- Site: https://athena.moratechnology.com
- Admin: https://athena.moratechnology.com/admin/
- Droplet: `600852697`, NYC3, 1 vCPU, 2 GiB RAM, 50 GiB disk, $12/month base price.
- IPv4: `159.203.121.42`
- DNS: create an `A` record named `athena` with that address at the existing DNS provider.
- Caddy obtains and renews HTTPS certificates after DNS resolves to the VPS.
- Do not change the parent domain's nameservers or other records.

## Users

In **Administración → Usuarios**, add, rename, deactivate, or delete users. Open a user to reset their password.
Ordinary active users can read published articles. Administrators can manage users and content.
The user directory shows every account on the left and the selected account on the right. Choose **Administrador** or **Lector** under *Acceso*; **Activa** controls whether the account can sign in.
The current administrator cannot remove their own administrative access.
Password changes invalidate other sessions and the user's API keys. Disabling or deleting a user blocks both browser and API access.
There is no public registration or email password-reset service. Users contact an administrator for recovery.

Initial production credentials are saved outside Git in `.secrets/production-admin.txt` and on the VPS in `/etc/athena/initial-admin.txt`.
Sign in and change the initial password. Credentials are not written to deployment output.

## Articles

1. Open **Administración → Artículos → Añadir**.
2. Enter title, summary, author, and optional comma-separated tags. The title creates the address automatically.
3. Write Markdown in the editor or upload a `.md` file (up to 1 MiB). No metadata header is required.
4. Optionally attach a PDF (up to 25 MiB). PDF-only articles are also supported.
5. Save as a draft for review. Enable **Publicado** when ready.

Changes appear in the library and search on the next page load; no build or redeploy is required.
Open an article to edit, replace or remove its PDF, unpublish it, or delete it.
**Ver en el sitio** previews saved drafts for editors. Existing article addresses cannot be changed.
Jeiser Vargas remains the editorial reviewer. OneDrive remains the location for approved package downloads.
The database is now the source of truth for articles, accounts, keys, and PDFs.

## Agent REST API

See [API.md](API.md). The importable OpenAPI schema is available at `/api/openapi.json`.
Create a key in **Administración → Claves de API**. Select an owner, scope, and expiry.
Copy the key when shown; it is stored only as a hash. Delete it to revoke access.
Use a dedicated account for an agent so password resets and access changes do not affect unrelated integrations.

## Local development

Requires Python 3.12+ and Node.js for preparing the reader assets.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci --ignore-scripts
npm run build
export ATHENA_SECRET_KEY='replace-with-a-random-local-secret'
export ATHENA_DEBUG=1
.venv/bin/python server/manage.py migrate
.venv/bin/python server/manage.py import_portal
.venv/bin/python server/manage.py createsuperuser
.venv/bin/python server/manage.py runserver 127.0.0.1:8765
npm test
```

`dist/` contains the approved migration input and package-link pages. It is intentionally private and excluded from Git.
Restore it from `.secrets/athena-vps-release.tar.gz` or the VPS before the first build on a fresh checkout.
`import_portal` is transactional and skips existing slugs. It does not overwrite edits or republish deleted content during normal operation.
Do not rerun it after deleting imported articles: migration input still contains those old records.
The original Windows build remains available as `npm run build:legacy`; it is not the production publishing workflow.
Cloudflare deployment scripts and `ALLOWLIST.md` describe the former hosting setup.

## Deployment and backup

The application is installed at `/opt/athena`. Its database and PDFs are in `/var/lib/athena/athena.sqlite3`.
Production secrets are in `/etc/athena/athena.env` (root only). The service runs as the unprivileged `athena` user.
Only SSH, HTTP, and HTTPS are open. Gunicorn listens on loopback.

The initial deployment uses `deploy/cloud-init.yaml`, then runs `deploy/install.sh` after copying the release to `/opt/athena`.
For updates, back up first, copy the changed code, install pinned requirements, migrate, collect static files, and restart `athena`.
**Do not run `import_portal` on routine updates.** Preserve `/var/lib/athena` and `/etc/athena`.

```sh
systemctl status athena caddy
journalctl -u athena -n 50 --no-pager
systemctl start athena-backup
systemctl list-timers athena-backup.timer
```

A daily timer creates verified SQLite backups in `/var/backups/athena` and retains 14 days.
PDFs are inside the database, so a backup includes both article data and attachments.
Backups on the same VPS do not cover VPS loss. An initial backup is also copied to this workstation's private `.secrets/` directory.
No paid DigitalOcean backup or other paid add-on is enabled.
For disaster recovery, retain a separate copy of the database, the release bundle, and `/etc/athena/athena.env`.
Stop `athena` before restoring a database, set its owner to `athena:athena`, then restart and test sign-in and article/PDF access.
