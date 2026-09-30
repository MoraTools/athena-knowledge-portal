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
| POST | `/article-images/` | Stage an image from multipart field `file`; returns `id`, `url`, `markdown`, `content_type`, `size`, `width`, `height`, `sha256` |
| GET | `/article-images/{id}/` | Read image bytes with the current key's article access |
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
Article images can be uploaded before the first article save. Use an `articles` or `admin` key whose owner has
`add_article` or `change_article`. Send only the `file` field. The image endpoint does not change an article or its ETag.
Use the returned `markdown` in a new article body, an article PATCH, or a Markdown upload. These saves check that each image still exists.
The upload validates actual PNG, JPEG, WebP, or GIF bytes, with a maximum of 10 MiB and 20 million pixels. GIF can be static or animated, with at most 2000 frames and 2000 million processed pixels (canvas width × height × frame count). Reduce the frame count or resolution if a GIF exceeds these limits. Animated PNG and WebP are rejected.
Files use generated names. PNG, JPEG, and WebP are re-encoded without their original metadata. GIF rendering blocks, frame timing, transparency, disposal, and loop settings are preserved. Every GIF frame is decoded in sequence by a separate worker limited to 10 CPU seconds, 12 elapsed seconds, and 512 MiB of memory. Comments, other application metadata, and data after the GIF trailer are removed. Unsupported rendering extensions are rejected. PDF exports use the first GIF frame.
The returned browser `url` inherits the access of articles that use the image. Use the API GET route to read bytes with a bearer key.
Read-only keys see published references. Editors with an edit-capable key also see draft references.
An image with no saved reference is visible only to its uploader while that account can still edit articles.
Other authors can reuse an image only after an article they can read uses it. A public article makes its referenced images public.
Unused images have a 24-hour grace period before cleanup. If an image is no longer available, upload it again before saving.
Download sections: `framework`, `packages`, `exercises`, `previous`. Uploads are published at once and keep the original file name.
The proxy accepts up to 512 MB on `/api/`. Each result has `size`, `sha256`, and `url`; the `url` works only in a signed-in browser session.

## Examples

Store a key in the calling agent's secret store or in `ATHENA_API_KEY`. Do not put keys in articles or Git.

```sh
curl --fail-with-body https://athena.moratechnology.com/api/v1/article-images/ \
  -H "Authorization: Bearer $ATHENA_API_KEY" -F 'file=@illustration.png'
```

Insert the returned `markdown` in the article's `body`. For an existing article, send its current `ETag` in `If-Match` when saving.

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

## Public article access

Article responses include `is_public`. New articles default to `false`; PATCH accepts only a JSON boolean.
Set `published: true` and `is_public: true` to permit anonymous reading through the existing reader URL, image URLs, and PDF routes.
Setting only `is_public` does not publish a draft. `is_public: false` requires a user account again.
All `/api/v1/articles/` operations still require a bearer key. Existing scopes, user edit permissions, and ETags still apply.
A read-only key cannot change public access or read drafts, even when its owner is an editor.
Package downloads remain restricted to signed-in users. Search-engine indexing remains disabled.
