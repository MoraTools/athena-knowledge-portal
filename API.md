# Athena REST API

Base URL: `https://athena.moratechnology.com/api/v1`
OpenAPI: [schema](https://athena.moratechnology.com/api/openapi.json)

## Authentication and scopes

Send `Authorization: Bearer YOUR_KEY` on every API request. Browser cookies are not accepted.
An administrator creates keys at `/admin/athena/apikey/`; the raw key is shown once.
Keys expire after 90 days by default. Deletion revokes a key immediately.
A disabled/deleted owner or a password reset also invalidates their keys.

| Scope | Access |
| --- | --- |
| `read` | Read published articles and their PDFs |
| `articles` | Article operations allowed by the owner's Django permissions |
| `admin` | Article operations plus user management, if the owner is a superuser |

A scope never grants more authority than its owner has. A key owned by an ordinary reader cannot publish articles.

## Endpoints

| Method | Path | Result |
| --- | --- | --- |
| GET | `/articles/?q=recorder&kind=guide&offset=0&limit=50` | Search/list articles; maximum page size 100 |
| POST | `/articles/` | Create an article, draft by default |
| GET | `/articles/{slug}/` | Read article, body, metadata, and version `ETag` |
| PATCH | `/articles/{slug}/` | Edit fields or change `published`; requires `If-Match` |
| DELETE | `/articles/{slug}/` | Remove article and PDF; requires `If-Match` |
| POST | `/articles/{slug}/markdown/` | Replace body from multipart field `file`; requires `If-Match` |
| POST | `/articles/{slug}/pdf/` | Attach or replace PDF from multipart field `file`; requires `If-Match` |
| GET | `/articles/{slug}/pdf/` | Download PDF |
| GET, POST | `/users/` | List or create users; admin scope only |
| GET, PATCH, DELETE | `/users/{id}/` | Read, rename, reset password, deactivate, promote, or remove user |

Dates use `YYYY-MM-DD`. Types: `guide`, `page`, `tool`, `announcement`, `release`.
Tags are an array of strings. Tools require `status`: `stable`, `alpha`, or `coming-soon`.
Article slugs remain fixed after creation. Optional fields: `url` (HTTPS), `download_file`.
Uploads accept UTF-8 `.md` up to 1 MiB and `.pdf` up to 25 MiB.
Create a draft with a short body before uploading attachments through the API.

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

Create a user with `username` and a password of at least 12 characters.
PATCH user fields `username`, `password`, `email`, `first_name`, `last_name`, `active`, or `admin`.
Setting `admin: true` also enables staff access. The acting administrator cannot delete or demote their own account.

## Errors

Errors are JSON under `error`: 400 invalid input, 401 invalid key, 403 insufficient permission,
404 missing resource, 409 duplicate record, 412 missing/stale ETag, 405 unsupported method.
A stale ETag means another edit was saved. Read the latest article before retrying; do not overwrite blindly.
