# Athena REST API

Base URL: `https://athena.moratechnology.com/api/v1`
OpenAPI: [schema](https://athena.moratechnology.com/api/openapi.json) · This guide: `GET /api/docs/` (no key needed)

## Quick start

1. An administrator creates a key in the admin at `/admin/athena/apikey/add/`. For full access, select scope `admin` and an owner who is an administrator. The raw key is shown once.
2. Store the key: `export ATHENA_API_KEY=athena_...`
3. Check the key:

   ```sh
   curl --fail-with-body https://athena.moratechnology.com/api/v1/me/ \
     -H "Authorization: Bearer $ATHENA_API_KEY"
   ```

   A good answer is `200` with the owner, the key, and what the key can do:
   `{"user": {"username": "...", "is_superuser": true, ...}, "key": {"scope": "admin", "expires_at": "...", ...}, "can": {"read_articles": true, "write_articles": true, "manage_downloads": true, "manage_users": true}}`.
   A `false` value in `can` means the endpoint answers `403` for this key.
4. Then use the article, download, and user endpoints below. `GET /api/v1/` lists every route and its methods without a key.

### Common failures

- **Missing `v1` or a wrong path**, for example `/api/users/`: every route starts with `/api/v1/` and ends with `/`.
  An unknown path under `/api/` answers `404` with `{"error": "Not found. See /api/docs/."}`.
- **`401` with a key that worked before**: a password change or reset of the key's owner invalidates all of that owner's keys,
  as do an expired key and a disabled or deleted owner. Create a new key.

## Authentication and scopes

Send `Authorization: Bearer YOUR_KEY` on every API request. Browser cookies are not accepted.
An administrator creates keys at `/admin/athena/apikey/`; the raw key is shown once.
Keys expire after 90 days by default. Deletion revokes a key immediately.
A disabled/deleted owner or a password reset also invalidates their keys.

| Scope | Access |
| --- | --- |
| `read` | Read published articles, their PDFs, and the published download list |
| `articles` | Article and download operations allowed by the owner's Django permissions |
| `admin` | Article and download operations plus user management, if the owner is a superuser |

A scope never grants more authority than its owner has. A key owned by an ordinary reader cannot publish articles.

## Endpoints

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/` or `/api/v1/` (full path) | Index: every route with its methods; no key needed |
| GET | `/api/docs/` (full path) | This guide as Markdown; no key needed |
| GET | `/me/` | The key's owner, scope, expiry, and `can` map of allowed operations |
| GET | `/articles/?q=recorder&kind=guide&offset=0&limit=50` | Search/list articles; maximum page size 100 |
| POST | `/articles/` | Create an article, draft by default |
| GET | `/articles/{slug}/` | Read article, body, metadata, and version `ETag` |
| PATCH | `/articles/{slug}/` | Edit fields or change `published`; requires `If-Match` |
| DELETE | `/articles/{slug}/` | Remove article and PDF; requires `If-Match` |
| POST | `/articles/{slug}/markdown/` | Replace body from multipart field `file`; requires `If-Match` |
| POST | `/articles/{slug}/pdf/` | Attach or replace PDF from multipart field `file`; requires `If-Match` |
| GET | `/articles/{slug}/pdf/` | Download PDF |
| GET | `/downloads/` | List downloads; `read` sees published files only |
| POST | `/downloads/` | Upload a file from multipart fields `title`, `section`, `file`, optional `note` |
| DELETE | `/downloads/{slug}/` | Remove a download and its stored file |
| GET, POST | `/users/` | List or create users; admin scope only |
| GET, PATCH, DELETE | `/users/{id}/` | Read, rename, reset password, deactivate, promote, or remove user |

Dates use `YYYY-MM-DD`. Types: `guide`, `page`, `tool`, `announcement`, `release`.
Tags are an array of strings. Tools require `status`: `stable`, `alpha`, or `coming-soon`.
Article slugs remain fixed after creation. Optional fields: `url` (HTTPS), `download_file`, `pdf_only`.
`pdf_only` (boolean, default `false`) means the attached PDF is the whole article: the reader then shows
the PDF viewer only and no "Exportar PDF" button. Articles send and return it like `published`.
Uploads accept UTF-8 `.md` up to 1 MiB and `.pdf` up to 25 MiB.
Create a draft with a short body before uploading attachments through the API.
Download sections: `framework`, `packages`, `exercises`, `previous`. Uploads are published at once and keep the original file name.
The proxy accepts up to 512 MB on `/api/`. Each result has `size`, `sha256`, and `url`; the `url` works only in a signed-in browser session.

## Examples

Store a key in the calling agent's secret store or in `ATHENA_API_KEY`. Do not put keys in articles or Git.

```sh
curl --fail-with-body https://athena.moratechnology.com/api/v1/articles/ \
  -H "Authorization: Bearer $ATHENA_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"slug":"recorder-guide","title":"Recorder guide","summary":"Capture steps","author":"Jeiser Vargas","body":"# Recorder guide\n\nSteps to review.","tags":["Recorder"],"published":false}'
```

To update, first GET the article and copy its exact `ETag` response header, including quotation marks, to `ATHENA_ETAG`:

```sh
curl --fail-with-body -i https://athena.moratechnology.com/api/v1/articles/recorder-guide/ \
  -H "Authorization: Bearer $ATHENA_API_KEY"

curl --fail-with-body -X PATCH https://athena.moratechnology.com/api/v1/articles/recorder-guide/ \
  -H "Authorization: Bearer $ATHENA_API_KEY" \
  -H "If-Match: $ATHENA_ETAG" \
  -H 'Content-Type: application/json' --data '{"published":true}'
```

The response returns a new ETag. Use that value for the next edit or upload.

```sh
curl --fail-with-body https://athena.moratechnology.com/api/v1/articles/recorder-guide/pdf/ \
  -H "Authorization: Bearer $ATHENA_API_KEY" \
  -H "If-Match: $ATHENA_ETAG" -F 'file=@guide.pdf'
```

```sh
curl --fail-with-body https://athena.moratechnology.com/api/v1/downloads/ \
  -H "Authorization: Bearer $ATHENA_API_KEY" \
  -F 'title=Framework 2026-07' -F 'section=framework' -F 'file=@Export.CORE_FRAMEWORK.zip'
```

Create a user with `username` and a password of at least 12 characters.
PATCH user fields `username`, `password`, `email`, `first_name`, `last_name`, `active`, or `admin`.
Setting `admin: true` also enables staff access. The acting administrator cannot delete or demote their own account.

## Errors

Errors are JSON under `error`: 400 invalid input, 401 invalid key, 403 insufficient permission,
404 missing resource or unknown path, 409 duplicate record, 412 missing/stale ETag, 405 unsupported method.
A stale ETag means another edit was saved. Read the latest article before retrying; do not overwrite blindly.
