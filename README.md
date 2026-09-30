# Athena Knowledge Portal

Athena runs on a DigitalOcean VPS with Django, SQLite, Gunicorn, and Caddy.
The Spanish reader keeps its existing Docsify routes. Published articles can be public or require an account. Existing articles remain private by default.

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
2. Enter the title. The title creates the address automatically. Open **Detalles** to enter the summary, author, and optional comma-separated tags.
3. Write Markdown in the editor or choose **Importar Markdown** from **Más opciones**. Use a UTF-8 `.md` file (up to 1 MiB). No metadata header is required.
4. In **Detalles**, optionally attach a PDF (up to 25 MiB). PDF-only articles are also supported.
5. Save as a draft for review. Set **Acceso público** to **Público** only when the article, its images, and its attached PDFs are suitable for anyone to read. **Con cuenta** is the default.
6. Enable **Publicado** when ready. Drafts stay restricted for both access settings.

On desktop, the editor shows Markdown and a live reader preview side by side. On mobile, use the **Markdown** and **Vista previa** tabs.
The **Detalles** dialog contains files, publication, and access settings. Select **Guardar** to save all changes.
A Markdown import replaces the editor text. After the import, you can edit the text before saving; saving keeps those edits. Wait until the import or image upload finishes before saving.

Changes appear in the library and search on the next page load; no build or redeploy is required.
Open an article to edit, replace or remove its PDF, unpublish it, or delete it.
**Ver en el sitio** previews saved drafts for editors. Existing article addresses cannot be changed.
Jeiser Vargas remains the editorial reviewer.
The database is now the source of truth for articles, accounts, keys, PDFs, and the download list.

## Public library

Visitors can use the home page, Guías, Herramientas, Actualizaciones, and search without signing in.
These pages include only published public articles. Titles, tags, excerpts, and counts for private articles and download records are excluded.
Signed-in readers see all published articles; existing article editors can preview drafts and set article access.
The REST API still requires a bearer key. Use the boolean `is_public` field to change article access with the existing edit permission and ETag checks.

Images, attached PDFs, and generated PDF exports follow the article access setting. Returning an article to **Con cuenta**, unpublishing it, or deleting it blocks subsequent anonymous requests, including cached PDF exports. A shared image stays public while another public published article uses it.
Previously downloaded copies cannot be recalled.
Search-engine indexing stays disabled through `robots.txt` and `X-Robots-Tag`; this is separate from public access.
The existing reader URLs remain valid. Sign-in returns to the selected article; account changes refresh open portal tabs.

PDF exports are cached under `/var/lib/athena/pdf-cache/`, outside public file serving and backups.
PDF links and cache keys use `ATHENA_PUBLIC_ORIGIN` (default: `https://athena.moratechnology.com`), never the request's Host header. Set it to your local preview URL when testing PDF links locally.
The single VPS permits one PDF render at a time, with a 30-second wall-clock timeout, 25 seconds of CPU, 768 MiB address-space limit, and 25 MiB output limit.
Busy or failed exports return 503 with `Retry-After: 10`. An unchanged article reuses its PDF; changed content replaces the prior cached version.
This cache can be deleted while the service is stopped; the next request regenerates it.

## Downloads

Approved files are stored on the VPS and only signed-in users can download them. OneDrive is no longer used for downloads.
The reader's **Descargas** page lists them in sections: Framework, Paquetes, Ejercicios, and Versiones anteriores (collapsed). The former Archivo page redirects there.

1. Open **Administración → Descargas → Añadir**.
2. Enter a title, choose the section, and select the file. The original file name is kept. Optionally add a short note.
3. Save. Athena records the size and SHA-256 checksum. Clear **Publicado** to hide a file without deleting it.

Deleting a download also deletes its file. Uploads of up to 512 MB pass the proxy on `/admin/` and `/api/`; agents can use the API (see [API.md](API.md)).
Files are in `/var/lib/athena/media/downloads/`. To load a folder tree once, copy it to the VPS and run:

```sh
sudo sh -c 'set -a; . /etc/athena/athena.env; cd /opt/athena && .venv/bin/python server/manage.py import_downloads /path/to/folder && chown -R athena:athena /var/lib/athena'
```

Files at the top level go to Framework; the `packages`, `ejercicios`, and `versiones anteriores` folders go to their sections. Other folders are reported and ignored.
The command skips files whose address already exists, so it is safe to run again. Two files with the same name import only once.

## Sign-in protection

Five failed sign-ins within 15 minutes, for the same username or from the same address, lock sign-in for 15 minutes.
Each further lockout within a day doubles the wait (30, 60 minutes, and so on, up to 24 hours).
The sign-in page shows the remaining wait. A successful sign-in clears the failure count; lockout history expires after 24 quiet hours.
This applies to `/accounts/login/` and `/admin/login/`. An administrator cannot unlock an account early from the admin.

## Article images

In an article's Markdown field, paste a clipboard image or select **Insertar imagen**. This works before the first save.
The image is inserted before any selected text. You can continue to write during upload. Save controls wait until the upload finishes.
If an upload fails, the editor retains your text and shows an error. Normal text paste keeps its native behavior.
Use PNG, JPEG, WebP, or GIF, up to 10 MiB and 20 million pixels. GIF can be static or animated.
GIF limits are 2000 frames and 2000 million processed pixels (canvas width × height × frame count). Reduce the frame count or resolution if a GIF exceeds these limits. Animated PNG and WebP are rejected.
The server checks the actual image bytes and uses a generated name. PNG, JPEG, and WebP are re-encoded without their original metadata.
GIF image blocks, frame timing, transparency, disposal, and loop settings are preserved. A separate worker decodes each frame in sequence, without storing all frames in memory. Validation is limited to 10 CPU seconds, 12 elapsed seconds, and 512 MiB of worker memory. Comments, other application metadata, and data after the GIF trailer are removed. Unsupported rendering extensions are rejected.

Images are private files in `MEDIA_ROOT/article-images/`. Django serves them through `/article-images/{uuid}/`.
A public published article makes its images public; a private published article requires an active account.
Editors can see images in drafts. Only the uploader can preview an image with no saved reference, while that account can still edit articles.
Shared images follow any readable article that uses them. Removing the uploader does not remove saved article images.
The reader plays animated GIFs. PDF exports use the first GIF frame. The bounded PDF worker receives only this article's image IDs and content hashes.

The daily `athena-image-gc.timer` removes unused managed images after a 24-hour grace period.
Cleanup checks all saved bodies, including drafts, shared images, inline/reference Markdown, HTML image sources, and local absolute URLs.
After the last reference is removed, a new 24-hour grace period starts. Backups, downloads, and PDF attachments are outside cleanup's scope.
An interrupted upload can leave an orphan file; cleanup removes only generated orphan names in the managed-image directory after 24 hours.

```sh
.venv/bin/python server/manage.py collect_article_images --dry-run
systemctl list-timers athena-image-gc.timer
journalctl -u athena-image-gc.service -n 50 --no-pager
```

`--dry-run` lists removal candidates without changing files or metadata. Article saves and cleanup use the same SQLite write transaction.
File deletion starts only after its metadata deletion commits. A stale article save rejects a missing image instead of saving a broken reference.

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

`dist/` contains the approved migration input and the reader's static pages. It is intentionally private and excluded from Git.
Restore it from `.secrets/athena-vps-release.tar.gz` or the VPS before the first build on a fresh checkout.
`import_portal` is transactional and skips existing slugs. It does not overwrite edits or republish deleted content during normal operation.
Do not rerun it after deleting imported articles: migration input still contains those old records.
The original Windows build remains available as `npm run build:legacy`; it is not the production publishing workflow.
Cloudflare deployment scripts and `ALLOWLIST.md` describe the former hosting setup.

## Deployment and backup

The application is installed at `/opt/athena`. Its database and PDFs are in `/var/lib/athena/athena.sqlite3`; download files are in `/var/lib/athena/media/`.
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
The same run mirrors all private media, including downloads and article images, to `/var/backups/athena/media/` with `rsync -a --delete`. The mirror has no history: a removed file leaves the mirror on the next run.
Backups on the same VPS do not cover VPS loss. An initial backup is also copied to this workstation's private `.secrets/` directory.
No paid DigitalOcean backup or other paid add-on is enabled.
For disaster recovery, retain a separate copy of the database, the download files, the release bundle, and `/etc/athena/athena.env`.
Stop `athena` before restoring a database, set its owner to `athena:athena`, then restart and test sign-in and article/PDF access.
To restore downloads, copy `/var/backups/athena/media/` back to `/var/lib/athena/media/` with the same owner.
