# Athena Knowledge Portal

Portal estático en español para guías, actualizaciones, herramientas y descargas de Automation Anywhere. Los documentos canónicos y los archivos de descarga viven en `C:\Users\superuser\OneDrive\dev\framework`.

## Publicar

```powershell
npm install
.\deploy.ps1
```

El build valida los documentos, crea `dist\` y publica solo archivos estáticos en Cloudflare Pages. No usa base de datos, CMS, Pages Functions, Workers ni R2. El costo permitido de Cloudflare es USD 0.

## Agregar o actualizar contenido

Guarde cada Markdown debajo de `C:\Users\superuser\OneDrive\dev\framework\docs`. La primera línea debe contener metadatos JSON en este formato:

```html
<!-- athena: {"kind":"guide","date":"2026-08-19","author":"Jeiser Vargas","summary":"Descripción breve","tags":["Recorder","Web"],"slug":"ejemplo"} -->
```

Valores de `kind`: `page`, `guide`, `tool`, `announcement` y `release`. Los perfiles de herramientas también usan `status` con `stable`, `alpha` o `coming-soon`. `url` y `downloadFile` son opcionales. Una guía puede usar `pdf` para asociar el archivo original.

Para agregar un documento:

1. Cree el Markdown con los metadatos y un título `#`.
2. Guárdelo en `docs`, `docs\tools` o `docs\updates`.
3. Ejecute `npm run build`.
4. Revise el resultado y ejecute `.\deploy.ps1`.

Para actualizarlo, edite el mismo archivo y vuelva a publicar. No cambie `slug` si debe conservar la URL. OneDrive conserva la copia de respaldo; `dist\` es un resultado regenerable.

Los PDF menores de 25 MiB se copian al sitio y se abren en otra pestaña. Un PDF con el mismo nombre que un Markdown se asocia automáticamente. También puede declarar otro nombre con `pdf`. Un PDF sin Markdown aparece como guía independiente.

## Descargas de OneDrive

Para crear o actualizar los enlaces aprobados:

```powershell
.\scripts\sync-onedrive-links.ps1
.\deploy.ps1
```

Para rotarlos:

```powershell
.\scripts\sync-onedrive-links.ps1 -Rotate
.\deploy.ps1
```

El script agrupa `.zip`, `.jar` y `.exe` por carpeta y mantiene la lista privada en `.secrets\onedrive-links.json`. No imprima ni confirme ese archivo en Git. Nunca comparta la raíz `framework`, porque contiene documentos que no forman parte de las descargas.

## Acceso

La URL pública canónica es `/request-access` y no depende de archivos protegidos. Cloudflare Access debe estar habilitado y verificado para proteger producción y las vistas previas mediante una lista de direcciones IP. La excepción pública debe cubrir `/request-access` y `/request-access.html`. La guía explica cómo solicitar acceso sin publicar el número de WhatsApp.

Use [ALLOWLIST.md](ALLOWLIST.md) to add, remove, or rotate an approved public IP with the Cloudflare MCP. The runbook requires identifiers such as `office` and `jeiser-vargas` without storing real addresses in Git.

## Impeccable

Impeccable está instalado solo en este proyecto. Verifique la instalación con:

```powershell
npx -y impeccable check --providers=codex --scope=project
```

## Navegación por página

Athena crea automáticamente el índice lateral **En esta página** con los títulos `#`, `##` y `###` de cada documento. Use esos niveles en orden y no mantenga un índice manual.

## Búsqueda

El build crea `search-index.json` y la ruta `#/search` a partir de los metadatos, títulos, secciones y texto de los documentos aprobados. Los documentos futuros quedan incluidos automáticamente; no mantenga una lista de rutas ni un índice manual.
