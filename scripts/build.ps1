[CmdletBinding()]
param(
    [string]$Source = 'C:\Users\superuser\OneDrive\dev\framework',
    [switch]$IgnoreLinks
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Athena builds require PowerShell 7 (pwsh) so UTF-8 text is decoded correctly.' }

$project = Split-Path $PSScriptRoot -Parent
$dist = Join-Path $project 'dist'
$sourceRoot = (Resolve-Path -LiteralPath $Source).Path.TrimEnd('\')
$docsRoot = Join-Path $sourceRoot 'docs'
$pdfLimit = 25MB
if (-not (Test-Path -LiteralPath $docsRoot -PathType Container)) { throw "The source has no docs folder: $docsRoot" }
if (-not $dist.StartsWith($project, [StringComparison]::OrdinalIgnoreCase)) { throw 'The output directory is outside the project.' }
if (Test-Path -LiteralPath $dist) { Remove-Item -LiteralPath $dist -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dist, (Join-Path $dist 'content'), (Join-Path $dist 'vendor'), (Join-Path $dist 'fonts'), (Join-Path $dist 'assets'), (Join-Path $dist 'pdf') | Out-Null

Copy-Item -LiteralPath (Join-Path $project 'src\index.html'), (Join-Path $project 'src\styles.css'), (Join-Path $project 'src\config.js'), (Join-Path $project 'src\app.js'), (Join-Path $project 'src\request-access.html'), (Join-Path $project 'src\_headers') -Destination $dist
Copy-Item -LiteralPath (Join-Path $project 'node_modules\docsify\lib\docsify.min.js') -Destination (Join-Path $dist 'vendor\docsify.min.js')
Copy-Item -LiteralPath (Join-Path $project 'node_modules\dompurify\dist\purify.min.js') -Destination (Join-Path $dist 'vendor\purify.min.js')
Copy-Item -LiteralPath (Join-Path $project 'node_modules\docsify\lib\themes\vue.css') -Destination (Join-Path $dist 'vendor\vue.css')
$themePath = Join-Path $dist 'vendor\vue.css'
$themeCss = [IO.File]::ReadAllText($themePath, [Text.Encoding]::UTF8).Replace('#34495e', '#ffb900').Replace('#2c3e50', '#fff')
[IO.File]::WriteAllText($themePath, $themeCss, [Text.UTF8Encoding]::new($false))
$themeVersion = (Get-FileHash -LiteralPath $themePath -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
$siteIndexPath = Join-Path $dist 'index.html'; $siteIndexHtml = [IO.File]::ReadAllText($siteIndexPath, [Text.Encoding]::UTF8).Replace('/vendor/vue.css"', "/vendor/vue.css?v=$themeVersion`"")
[IO.File]::WriteAllText($siteIndexPath, $siteIndexHtml, [Text.UTF8Encoding]::new($false))
Copy-Item -Path (Join-Path $project 'src\fonts\*') -Destination (Join-Path $dist 'fonts')
Copy-Item -Path (Join-Path $project 'src\assets\*') -Destination (Join-Path $dist 'assets')

function Write-Utf8([string]$Path, [string]$Value) { [IO.File]::WriteAllText($Path, $Value, [Text.UTF8Encoding]::new($false)) }

function ConvertTo-SearchText([string]$Markdown) {
    $text = [regex]::Replace($Markdown, '(?ms)<!--.*?-->', ' ')
    $text = [regex]::Replace($text, '(?ms)```[^\r\n]*\r?\n(.*?)```', '$1')
    $text = [regex]::Replace($text, '!\[([^\]]*)\]\([^)]+\)', '$1')
    $text = [regex]::Replace($text, '\[([^\]]+)\]\([^)]+\)', '$1')
    $text = [regex]::Replace($text, '<[^>]+>', ' ')
    $text = [regex]::Replace($text, '(?m)^\s{0,3}#{1,6}\s+', '')
    $text = [regex]::Replace($text, '(?m)^\s*(?:>\s*|[-+]\s+|\d+\.\s+)', '')
    $text = $text -replace '[`*_~]', ''
    return [regex]::Replace([Net.WebUtility]::HtmlDecode($text), '\s+', ' ').Trim()
}

function Get-SearchHeadings([string]$Markdown) {
    $matches = [regex]::Matches($Markdown, '(?m)^\s{0,3}(#{2,6})\s+(.+?)\s*#*\s*$')
    $headings = [Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $matches.Count; $index++) {
        $match = $matches[$index]
        $contentStart = $match.Index + $match.Length
        $contentEnd = if ($index + 1 -lt $matches.Count) { $matches[$index + 1].Index } else { $Markdown.Length }
        $headings.Add([pscustomobject]@{
            level = $match.Groups[1].Value.Length
            title = ConvertTo-SearchText $match.Groups[2].Value
            text = ConvertTo-SearchText $Markdown.Substring($contentStart, $contentEnd - $contentStart)
        })
    }
    return @($headings)
}
function Get-Slug([string]$Value) {
    $normalized = $Value.Normalize([Text.NormalizationForm]::FormD)
    $letters = -join ($normalized.ToCharArray() | Where-Object { [Globalization.CharUnicodeInfo]::GetUnicodeCategory($_) -ne [Globalization.UnicodeCategory]::NonSpacingMark })
    $slug = ($letters.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
    if (-not $slug) { throw "Text cannot produce a route: $Value" }
    return $slug
}
function Get-LinkKey([string]$RelativePath, [string]$Prefix = '') {
    $name = if ($Prefix) { Split-Path $RelativePath -Leaf } else { [IO.Path]::GetFileNameWithoutExtension($RelativePath) }
    $slug = Get-Slug $name
    if ($slug.Length -gt 42) { $slug = $slug.Substring(0, 42).TrimEnd('-') }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes("$Prefix$($RelativePath.ToLowerInvariant())")
        $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').Substring(0, 8).ToLowerInvariant()
    } finally { $sha.Dispose() }
    return "$Prefix$slug-$hash"
}
function Get-Section([string]$RelativePath) {
    if ($RelativePath.StartsWith('packages\', [StringComparison]::OrdinalIgnoreCase)) { return 'Paquetes' }
    if ($RelativePath.StartsWith('ejercicios\', [StringComparison]::OrdinalIgnoreCase)) { return 'Ejercicios' }
    if ($RelativePath.StartsWith('versiones anteriores\', [StringComparison]::OrdinalIgnoreCase)) { return 'Archivo' }
    return 'Framework'
}
function Format-Size([long]$Bytes) {
    if ($Bytes -ge 1GB) { return ('{0:N2} GB' -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return ('{0:N1} MB' -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return ('{0:N1} KB' -f ($Bytes / 1KB)) }
    return "$Bytes B"
}
function Html([object]$Value) { return [Net.WebUtility]::HtmlEncode([string]$Value) }

$sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -File -Recurse | Sort-Object FullName)
$approvedExtensions = @('.zip', '.jar', '.exe')
$downloadFiles = @($sourceFiles | Where-Object { $_.Extension.ToLowerInvariant() -in $approvedExtensions })
$configured = @{}
$secretFile = Join-Path $project '.secrets\onedrive-links.json'
if (-not $IgnoreLinks -and (Test-Path -LiteralPath $secretFile)) {
    $secretObject = Get-Content -LiteralPath $secretFile -Raw -Encoding utf8 | ConvertFrom-Json
    foreach ($property in $secretObject.PSObject.Properties) {
        $url = [uri]$property.Value
        if ($url.Scheme -ne 'https' -or $url.Host.ToLowerInvariant() -notin '1drv.ms', 'onedrive.live.com') { throw "Invalid OneDrive URL for catalog key: $($property.Name)" }
        $configured[$property.Name] = $url.AbsoluteUri
    }
}
$catalog = foreach ($file in $downloadFiles) {
    $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')
    $folderPath = Split-Path $relative -Parent
    $linkKind = if ($folderPath) { 'folder' } else { 'file' }
    $linkKey = if ($folderPath) { Get-LinkKey $folderPath 'folder-' } else { Get-LinkKey $relative }
    $downloadUrl = if ($configured.ContainsKey($linkKey)) { $configured[$linkKey] } else { $null }
    [pscustomobject]@{
        key = Get-LinkKey $relative; linkKey = $linkKey; linkKind = $linkKind; folderPath = $folderPath
        name = $file.Name; section = Get-Section $relative; relativePath = $relative; bytes = $file.Length
        size = Format-Size $file.Length; available = [bool]$downloadUrl; downloadUrl = $downloadUrl
    }
}
$approvedKeys = @($catalog | ForEach-Object linkKey | Sort-Object -Unique)
$unknownKeys = @($configured.Keys | Where-Object { $_ -notin $approvedKeys })
if ($unknownKeys) { throw "The private whitelist contains unknown or unapproved keys: $($unknownKeys -join ', ')" }
$configuredTargets = @($configured.Keys | Where-Object { $_ -in $approvedKeys })
$catalog | Select-Object key, linkKey, linkKind, folderPath, name, section, relativePath, bytes, size, available | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $dist 'catalog.json') -Encoding utf8

$allowedKinds = @('page', 'guide', 'tool', 'announcement', 'release')
$allowedStatuses = @('stable', 'alpha', 'coming-soon')
$metadataPattern = '\A(?:\uFEFF)?<!--\s*athena:\s*(\{[^\r\n]+\})\s*-->'
$markdownFiles = @(Get-ChildItem -LiteralPath $docsRoot -Filter '*.md' -File -Recurse | Sort-Object FullName)
$pdfFiles = @(Get-ChildItem -LiteralPath $docsRoot -Filter '*.pdf' -File -Recurse | Sort-Object FullName)
$oversizedPdfs = @($pdfFiles | Where-Object Length -ge $pdfLimit)
if ($oversizedPdfs) { throw "PDF files must be smaller than 25 MiB: $($oversizedPdfs.FullName -join ', ')" }

$content = foreach ($file in $markdownFiles) {
    $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')
    $raw = Get-Content -LiteralPath $file.FullName -Raw -Encoding utf8
    $match = [regex]::Match($raw, $metadataPattern)
    if (-not $match.Success) { throw "Markdown metadata must be the first line: $relative" }
    try { $metadata = $match.Groups[1].Value | ConvertFrom-Json }
    catch { throw "Invalid Athena metadata JSON in $relative`: $($_.Exception.Message)" }
    foreach ($required in 'kind', 'date', 'author', 'summary', 'tags', 'slug') {
        if ($required -notin $metadata.PSObject.Properties.Name) { throw "Missing metadata field '$required' in $relative" }
    }
    if ([string]$metadata.kind -notin $allowedKinds) { throw "Unknown content kind '$($metadata.kind)' in $relative" }
    $parsedDate = [datetime]::MinValue
    if (-not [datetime]::TryParseExact([string]$metadata.date, 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$parsedDate)) { throw "Invalid metadata date '$($metadata.date)' in $relative" }
    foreach ($requiredText in 'author', 'summary', 'slug') {
        if ([string]::IsNullOrWhiteSpace([string]$metadata.$requiredText)) { throw "Empty metadata field '$requiredText' in $relative" }
    }
    $slug = [string]$metadata.slug
    if ($slug -cnotmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$') { throw "Invalid metadata slug '$slug' in $relative" }
    if ($metadata.tags -isnot [array]) { throw "Metadata tags must be an array of non-empty strings in $relative" }
    $tags = @($metadata.tags)
    if (@($tags | Where-Object { $_ -isnot [string] -or [string]::IsNullOrWhiteSpace($_) }).Count) { throw "Metadata tags must be an array of non-empty strings in $relative" }
    $status = [string]$metadata.status
    if ($status -and $status -notin $allowedStatuses) { throw "Unknown tool status '$status' in $relative" }
    if ($metadata.kind -eq 'tool' -and -not $status) { throw "Tool metadata requires a status in $relative" }
    if ($metadata.kind -ne 'tool' -and $status) { throw "Only tools can declare a status in $relative" }
    if ($metadata.url) {
        $uri = $null
        if (-not [uri]::TryCreate([string]$metadata.url, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'https') { throw "Tool URL must use HTTPS in $relative" }
    }
    if ($metadata.downloadFile -and -not ($downloadFiles.Name -contains [string]$metadata.downloadFile)) { throw "Declared download '$($metadata.downloadFile)' does not exist for $relative" }
    $body = $raw.Substring($match.Length).TrimStart("`r", "`n")
    $heading = [regex]::Match($body, '(?m)^#\s+(.+?)\s*$')
    if (-not $heading.Success) { throw "Markdown requires one level-one title: $relative" }
    $bodyWithoutTitle = [regex]::Replace($body, '\A\s*#\s+[^\r\n]+\r?\n*', '')
    $pdfSource = $null
    if ($metadata.pdf) {
        $pdfSource = [IO.Path]::GetFullPath((Join-Path $file.DirectoryName ([string]$metadata.pdf)))
        $pdfRelative = [IO.Path]::GetRelativePath($docsRoot, $pdfSource)
        $escapesDocs = [IO.Path]::IsPathRooted($pdfRelative) -or $pdfRelative -eq '..' -or $pdfRelative.StartsWith("..$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::Ordinal) -or $pdfRelative.StartsWith("..$([IO.Path]::AltDirectorySeparatorChar)", [StringComparison]::Ordinal)
        if ($escapesDocs -or -not [IO.Path]::GetExtension($pdfSource).Equals('.pdf', [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $pdfSource -PathType Leaf)) { throw "Declared PDF '$($metadata.pdf)' does not exist below docs for $relative" }
    } else {
        $sameName = @($pdfFiles | Where-Object { $_.BaseName -eq $file.BaseName })
        if ($sameName.Count -gt 1) { throw "More than one PDF matches $relative" }
        if ($sameName.Count -eq 1) { $pdfSource = $sameName[0].FullName }
    }
    [pscustomobject]@{
        Source = $relative; MetadataLine = $match.Value.Trim(); Kind = [string]$metadata.kind; Date = $parsedDate
        DateText = [string]$metadata.date; Author = [string]$metadata.author; Summary = [string]$metadata.summary
        Tags = $tags; Slug = $slug; Status = $status; Url = [string]$metadata.url; DownloadFile = [string]$metadata.downloadFile
        Title = $heading.Groups[1].Value; Body = $bodyWithoutTitle; PdfSource = $pdfSource; PdfRoute = $null
    }
}
$duplicateSlugs = @($content | Group-Object Slug | Where-Object Count -gt 1)
if ($duplicateSlugs) { throw "Duplicate metadata slugs: $($duplicateSlugs.Name -join ', ')" }
$duplicatePdfs = @($content | Where-Object PdfSource | Group-Object PdfSource | Where-Object Count -gt 1)
if ($duplicatePdfs) { throw "A PDF is associated with more than one Markdown file: $($duplicatePdfs.Name -join ', ')" }

$pdfRecords = [Collections.Generic.List[object]]::new()
foreach ($pdf in $pdfFiles) {
    $article = $content | Where-Object { $_.PdfSource -eq $pdf.FullName } | Select-Object -First 1
    $slug = if ($article) { $article.Slug } else { Get-Slug $pdf.BaseName }
    $route = "/pdf/$slug.pdf"
    if ($pdfRecords.Route -contains $route) { throw "Two PDFs produce the same route: $route" }
    Copy-Item -LiteralPath $pdf.FullName -Destination (Join-Path $dist "pdf\$slug.pdf")
    $record = [pscustomobject]@{ Source = $pdf.FullName; Relative = $pdf.FullName.Substring($sourceRoot.Length).TrimStart('\'); Name = $pdf.Name; Title = $pdf.BaseName; Route = $route; Bytes = $pdf.Length; Article = $article }
    $pdfRecords.Add($record)
    if ($article) { $article.PdfRoute = $route }
}
foreach ($article in $content) {
    $sourceNote = "<p class=`"source-note`">Fuente canónica: <code>$(Html $article.Source)</code></p>"
    $pdfLink = if ($article.PdfRoute) { "<p><a class=`"pdf-link`" href=`"$($article.PdfRoute)`" target=`"_blank`" rel=`"noreferrer`">Abrir PDF original</a></p>" } else { '' }
    $page = "$($article.MetadataLine)`n# $($article.Title)`n`n$sourceNote`n`n$pdfLink`n`n$($article.Body.Trim())`n"
    Write-Utf8 (Join-Path $dist "content\$($article.Slug).md") $page
}

function New-CatalogPage([string]$Title, [string]$Intro, [object[]]$Items) {
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add("# $Title"); $lines.Add(''); $lines.Add($Intro); $lines.Add(''); $lines.Add('<div class="catalog-list">')
    foreach ($group in $Items | Group-Object folderPath) {
        if ($group.Name) {
            $folderItems = @($group.Group); $folderName = Html (Split-Path $group.Name -Leaf); $folderPath = Html $group.Name
            $countLabel = if ($folderItems.Count -eq 1) { '1 archivo' } else { "$($folderItems.Count) archivos" }
            $lines.Add('<article class="catalog-item">'); $lines.Add("<div><strong>$folderName</strong><small>$countLabel</small><code>$folderPath</code><ul class=`"folder-files`">")
            foreach ($item in $folderItems) { $lines.Add("<li><span>$(Html $item.name)</span><small>$($item.size)</small></li>") }
            $lines.Add('</ul></div>'); $linkedItem = $folderItems | Where-Object available | Select-Object -First 1
            if ($linkedItem) { $lines.Add("<a class=`"download-link`" href=`"$(Html $linkedItem.downloadUrl)`" target=`"_blank`" rel=`"nofollow noreferrer`" referrerpolicy=`"no-referrer`">Abrir carpeta</a>") }
            else { $lines.Add('<span class="download-pending">Pendiente</span>') }
            $lines.Add('</article>'); continue
        }
        foreach ($item in $group.Group) {
            $lines.Add('<article class="catalog-item">'); $lines.Add("<div><strong>$(Html $item.name)</strong><small>$($item.size)</small><code>$(Html $item.relativePath)</code></div>")
            if ($item.available) { $lines.Add("<a class=`"download-link`" href=`"$(Html $item.downloadUrl)`" target=`"_blank`" rel=`"nofollow noreferrer`" referrerpolicy=`"no-referrer`">Abrir archivo</a>") }
            else { $lines.Add('<span class="download-pending">Pendiente</span>') }
            $lines.Add('</article>')
        }
    }
    $lines.Add('</div>'); return $lines -join "`n"
}
$catalogPages = [ordered]@{
    'framework.md' = @{ Title = 'Framework'; Intro = 'La versión actual del Core Framework.'; Section = 'Framework' }
    'packages.md' = @{ Title = 'Paquetes'; Intro = 'Paquetes adicionales usados por los bots.'; Section = 'Paquetes' }
    'exercises.md' = @{ Title = 'Ejercicios'; Intro = 'Material práctico y datos de ejemplo.'; Section = 'Ejercicios' }
    'archive.md' = @{ Title = 'Archivo'; Intro = 'Versiones anteriores. Use la versión actual salvo que necesite reproducir un ambiente histórico.'; Section = 'Archivo' }
    'downloads.md' = @{ Title = 'Descargas'; Intro = 'Archivos aprobados disponibles mediante las carpetas compartidas de OneDrive.'; Section = $null }
}
foreach ($page in $catalogPages.GetEnumerator()) {
    $items = if ($page.Value.Section) { @($catalog | Where-Object section -eq $page.Value.Section) } else { @($catalog) }
    Write-Utf8 (Join-Path $dist $page.Key) (New-CatalogPage $page.Value.Title $page.Value.Intro $items)
}

$guideLines = [Collections.Generic.List[string]]::new()
$guideLines.Add('# Guías'); $guideLines.Add(''); $guideLines.Add('Encuentre documentos por texto o por etiqueta. Todos los resultados están disponibles sin paginación.'); $guideLines.Add('')
$guideLines.Add('<div class="library-controls"><label>Buscar guías<input id="guide-filter" type="search" placeholder="Título, autor o tema" autocomplete="off"></label><label>Etiqueta<select id="guide-tag"><option value="">Todas</option>')
$unmatchedPdfs = @($pdfRecords | Where-Object { -not $_.Article })
$allGuideTags = @($content | Where-Object Kind -eq 'guide' | ForEach-Object Tags)
if ($unmatchedPdfs.Count) { $allGuideTags += 'PDF' }
$allGuideTags = @($allGuideTags | Sort-Object -Unique)
foreach ($tag in $allGuideTags) { $guideLines.Add("<option value=`"$(Html $tag)`">$(Html $tag)</option>") }
$guideLines.Add('</select></label><p id="guide-count" class="result-count" aria-live="polite"></p></div>'); $guideLines.Add('<div class="library-grid guide-library">')
foreach ($guide in $content | Where-Object Kind -eq 'guide' | Sort-Object Title) {
    $search = Html "$($guide.Title) $($guide.Author) $($guide.Summary) $($guide.Tags -join ' ')"; $tags = Html ($guide.Tags -join '|')
    $tagMarkup = (@($guide.Tags | ForEach-Object { "<span>$(Html $_)</span>" })) -join ''
    $pdfMarkup = if ($guide.PdfRoute) { "<a class=`"pdf-link`" href=`"$($guide.PdfRoute)`" target=`"_blank`" rel=`"noreferrer`">Abrir PDF original</a>" } else { '' }
    $guideLines.Add("<article class=`"library-card`" data-search=`"$search`" data-tags=`"$tags`"><p class=`"card-kicker`">$($guide.DateText) · $(Html $guide.Author)</p><h2><a href=`"#/content/$($guide.Slug)`">$(Html $guide.Title)</a></h2><p>$(Html $guide.Summary)</p><p class=`"tag-list`">$tagMarkup</p>$pdfMarkup</article>")
}
foreach ($pdf in $unmatchedPdfs | Sort-Object Title) {
    $guideLines.Add("<article class=`"library-card`" data-search=`"$(Html "$($pdf.Title) PDF")`" data-tags=`"PDF`"><p class=`"card-kicker`">Documento PDF · $(Format-Size $pdf.Bytes)</p><h2><a href=`"$($pdf.Route)`" target=`"_blank`" rel=`"noreferrer`">$(Html $pdf.Title)</a></h2><p>Documento original disponible en el visor PDF del navegador.</p><p class=`"tag-list`"><span>PDF</span></p></article>")
}
$guideLines.Add('</div><p class="library-empty" hidden>No hay guías que coincidan con estos filtros.</p>')
Write-Utf8 (Join-Path $dist 'guides.md') ($guideLines -join "`n")

$statusLabels = @{ stable = 'Estable'; alpha = 'Alfa'; 'coming-soon' = 'Próximamente' }
$toolLines = [Collections.Generic.List[string]]::new(); $toolLines.Add('# Herramientas'); $toolLines.Add(''); $toolLines.Add('Perfiles, estado actual, documentación y descargas aprobadas para las herramientas del equipo.'); $toolLines.Add(''); $toolLines.Add('<div class="library-grid">')
foreach ($tool in $content | Where-Object Kind -eq 'tool' | Sort-Object Title) {
    $external = if ($tool.Url) { "<a href=`"$(Html $tool.Url)`" target=`"_blank`" rel=`"noreferrer`">Sitio oficial</a>" } else { '' }
    $download = if ($tool.DownloadFile) { '<a href="#/packages">Descarga aprobada</a>' } else { '' }; $separator = if ($external -and $download) { '<span aria-hidden="true"> · </span>' } else { '' }
    $toolLines.Add("<article class=`"library-card tool-card`"><p class=`"status status-$($tool.Status)`">$($statusLabels[$tool.Status])</p><h2><a href=`"#/content/$($tool.Slug)`">$(Html $tool.Title)</a></h2><p>$(Html $tool.Summary)</p><p>$external$separator$download</p></article>")
}
$toolLines.Add('</div>'); Write-Utf8 (Join-Path $dist 'tools.md') ($toolLines -join "`n")

$updateLines = [Collections.Generic.List[string]]::new(); $updateLines.Add('# Actualizaciones'); $updateLines.Add(''); $updateLines.Add('Nuevas guías, versiones y anuncios en orden cronológico.'); $updateLines.Add(''); $updateLines.Add('<div class="updates-feed">')
$updates = @($content | Where-Object Kind -in 'guide', 'announcement', 'release' | Sort-Object Date, Title -Descending)
foreach ($update in $updates) {
    $kindLabel = switch ($update.Kind) { guide { 'Nueva guía' } announcement { 'Anuncio' } release { 'Versión' } }
    $updateLines.Add("<article class=`"update-item`"><p class=`"card-kicker`">$($update.DateText) · $kindLabel</p><h2><a href=`"#/content/$($update.Slug)`">$(Html $update.Title)</a></h2><p>$(Html $update.Summary)</p></article>")
}
$updateLines.Add('</div>'); Write-Utf8 (Join-Path $dist 'updates.md') ($updateLines -join "`n")

$searchIndex = [Collections.Generic.List[object]]::new()
foreach ($article in $content) {
    $searchIndex.Add([pscustomobject][ordered]@{
        kind = $article.Kind
        title = $article.Title
        summary = $article.Summary
        author = $article.Author
        date = $article.DateText
        tags = @($article.Tags)
        route = "#/content/$($article.Slug)"
        pdf = $article.PdfRoute
        text = ConvertTo-SearchText $article.Body
        headings = @(Get-SearchHeadings $article.Body)
    })
}
foreach ($pdf in $unmatchedPdfs) {
    $searchIndex.Add([pscustomobject][ordered]@{
        kind = 'pdf'
        title = $pdf.Title
        summary = 'Documento original disponible en el visor PDF del navegador.'
        author = ''
        date = ''
        tags = @('PDF')
        route = $pdf.Route
        pdf = $pdf.Route
        text = ''
        headings = @()
    })
}
foreach ($item in @($catalog)) {
    $catalogRoute = switch ($item.section) {
        'Framework' { '#/framework' }
        'Paquetes' { '#/packages' }
        'Ejercicios' { '#/exercises' }
        'Archivo' { '#/archive' }
        default { '#/downloads' }
    }
    $searchIndex.Add([pscustomobject][ordered]@{
        kind = 'download'
        title = $item.name
        summary = "Archivo aprobado de $($item.size) en $($item.section)."
        author = ''
        date = ''
        tags = @($item.section, [IO.Path]::GetExtension($item.name).TrimStart('.').ToUpperInvariant())
        route = $catalogRoute
        pdf = $null
        text = "$($item.relativePath) $($item.folderPath)"
        headings = @()
    })
}
$searchJson = ConvertTo-Json -InputObject @($searchIndex) -Depth 5
Write-Utf8 (Join-Path $dist 'search-index.json') $searchJson

$searchPage = @'
# Buscar en Athena

<div class="search-page">
  <div id="search-page-slot" aria-label="Buscar en Athena"></div>
  <div class="search-toolbar">
    <label for="athena-search-type">Tipo de contenido</label>
    <select id="athena-search-type">
      <option value="">Todo</option>
      <option value="guide">Guías</option>
      <option value="tool">Herramientas</option>
      <option value="update">Actualizaciones</option>
      <option value="download">Descargas</option>
      <option value="pdf">PDF</option>
    </select>
  </div>
  <p id="search-result-count" class="search-result-count" aria-live="polite"></p>
  <div id="search-results" class="search-results" aria-live="polite"></div>
</div>
'@
Write-Utf8 (Join-Path $dist 'search.md') $searchPage

$homePage = @'
<section class="hero">
  <div class="hero-copy">
    <p class="eyebrow">Automation Anywhere</p>
    <h1>Athena</h1>
    <p>Centro de conocimiento, herramientas y feed de actualizaciones para desarrolladores.</p>
    <div id="home-search-slot" aria-label="Buscar en Athena"></div>
  </div>
  <img src="/assets/athena-dither-2.webp" alt="" width="900" height="900">
</section>

## Explorar

<div class="portal-grid">
  <a class="portal-card" href="#/guides"><span>Guías</span><p>Busque por texto o etiqueta en la biblioteca permanente.</p></a>
  <a class="portal-card" href="#/updates"><span>Actualizaciones</span><p>Consulte guías nuevas, versiones y anuncios.</p></a>
  <a class="portal-card" href="#/tools"><span>Herramientas</span><p>Revise estado, límites, documentación y descargas.</p></a>
  <a class="portal-card" href="#/downloads"><span>Descargas</span><p>Abra las carpetas aprobadas de OneDrive.</p></a>
</div>

<div class="contribute-note"><p>¿Documentó una solución que el equipo puede volver a usar?</p><a href="#/content/contributing">Cómo contribuir</a></div>
'@
Write-Utf8 (Join-Path $dist 'README.md') $homePage
$sidebar = @'
- [Inicio](/)
- [Guías](/guides.md)
- [Actualizaciones](/updates.md)
- [Herramientas](/tools.md)
- [Descargas](/downloads.md)
- [Contribuir](/content/contributing.md)
- [Archivo](/archive.md)
'@
Write-Utf8 (Join-Path $dist '_sidebar.md') $sidebar

$largeOutput = @(Get-ChildItem -LiteralPath $dist -File -Recurse | Where-Object Length -ge $pdfLimit)
if ($largeOutput) { throw "Pages output contains a file of 25 MiB or more: $($largeOutput.FullName -join ', ')" }
$publicFiles = Get-ChildItem -LiteralPath $dist -File -Recurse; $publicTextFiles = @($publicFiles | Where-Object Extension -in '.css', '.html', '.js', '.json', '.md')
$mojibakePattern = '[\u00C2\u00C3][\u0080-\u00BF]|\u00E2\u20AC.|\uFFFD'; $badEncoding = @($publicTextFiles | Where-Object { [regex]::IsMatch([IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8), $mojibakePattern) })
if ($badEncoding) { throw "Generated text contains mojibake: $($badEncoding.FullName -join ', ')" }
if ($publicTextFiles | Select-String -Pattern '#34495e|#2c3e50' -ErrorAction SilentlyContinue) { throw 'A deprecated low-contrast color remains in the public output.' }
$downloadPage = [IO.File]::ReadAllText((Join-Path $dist 'downloads.md'), [Text.Encoding]::UTF8); $downloadAnchorCount = [regex]::Matches($downloadPage, '<a class="download-link" href="https://(?:1drv\.ms|onedrive\.live\.com)/').Count
if ($downloadAnchorCount -ne $configuredTargets.Count) { throw 'The generated download whitelist does not match the approved catalog targets.' }
if (Select-String -LiteralPath (Join-Path $dist 'catalog.json') -Pattern '1drv\.ms|onedrive\.live\.com' -ErrorAction SilentlyContinue) { throw 'OneDrive URLs must not be written into catalog.json.' }
if (Select-String -LiteralPath (Join-Path $dist 'search-index.json') -Pattern '1drv\.ms|onedrive\.live\.com' -ErrorAction SilentlyContinue) { throw 'OneDrive URLs must not be written into search-index.json.' }
if ($searchIndex.Count -ne ($content.Count + $unmatchedPdfs.Count + @($catalog).Count)) { throw 'The generated search index is incomplete.' }
if ((Get-ChildItem -LiteralPath (Join-Path $dist 'content') -Filter '*.md').Count -ne $content.Count) { throw 'Not every Markdown document produced a content route.' }
Write-Host "Built Athena with $(@($content | Where-Object Kind -eq 'guide').Count) guides, $(@($content | Where-Object Kind -eq 'tool').Count) tools, $($pdfRecords.Count) PDFs, and $($configuredTargets.Count) configured OneDrive links."
