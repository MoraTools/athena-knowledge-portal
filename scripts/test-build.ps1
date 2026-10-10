[CmdletBinding()]
param([int]$GuideCount = 120)

$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$build = Join-Path $PSScriptRoot 'build.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) "athena-build-$([guid]::NewGuid().ToString('N'))"

function New-Source([string]$Name) {
    $root = Join-Path $testRoot $Name
    New-Item -ItemType Directory -Path (Join-Path $root 'docs') -Force | Out-Null
    return $root
}

function Write-Guide([string]$Root, [string]$Name, [string]$Metadata, [string]$Title = 'Test guide') {
    $markdown = "<!-- athena: $Metadata -->`n# $Title`n`nSearchable UTF-8 content: Guía de implementación.`n"
    $markdown += "`n## Test section`n`n### Test detail`n`n#### Hidden depth`n"
    [IO.File]::WriteAllText((Join-Path $Root "docs\$Name.md"), $markdown, [Text.UTF8Encoding]::new($false))
}

function Assert-BuildFails([string]$Root, [string]$Expected) {
    try {
        & $build -Source $Root -IgnoreLinks | Out-Null
    } catch {
        if ($_.Exception.Message -notlike "*$Expected*") { throw "Expected '$Expected', got: $($_.Exception.Message)" }
        return
    }
    throw "Build unexpectedly passed; expected: $Expected"
}

New-Item -ItemType Directory -Path $testRoot | Out-Null

try {
    $scale = New-Source 'scale'
    foreach ($number in 1..$GuideCount) {
        $slug = 'guide-{0:d3}' -f $number
        $metadata = "{`"kind`":`"guide`",`"date`":`"2026-08-19`",`"author`":`"Scale Test`",`"summary`":`"Synthetic guide $number`",`"tags`": [`"Test`"],`"slug`":`"$slug`"}"
        Write-Guide $scale $slug $metadata "Synthetic guide $number"
    }
    [IO.File]::WriteAllText((Join-Path $scale 'package.jar'), 'test', [Text.Encoding]::ASCII)
    [IO.File]::WriteAllBytes((Join-Path $scale 'docs\reference.pdf'), [Text.Encoding]::ASCII.GetBytes("%PDF-1.4`n%%EOF"))

    & $build -Source $scale -IgnoreLinks | Out-Null
    $dist = Join-Path $project 'dist'
    $contentCount = @(Get-ChildItem -LiteralPath (Join-Path $dist 'content') -Filter '*.md').Count
    $guides = [IO.File]::ReadAllText((Join-Path $dist 'guides.md'), [Text.Encoding]::UTF8)
    $config = [IO.File]::ReadAllText((Join-Path $dist 'config.js'), [Text.Encoding]::UTF8)
    $catalog = [IO.File]::ReadAllText((Join-Path $dist 'catalog.json'), [Text.Encoding]::UTF8)
    $searchPage = [IO.File]::ReadAllText((Join-Path $dist 'search.md'), [Text.Encoding]::UTF8)
    $searchIndexJson = [IO.File]::ReadAllText((Join-Path $dist 'search-index.json'), [Text.Encoding]::UTF8)
    $searchIndex = @($searchIndexJson | ConvertFrom-Json)
    $indexHtml = [IO.File]::ReadAllText((Join-Path $dist 'index.html'), [Text.Encoding]::UTF8)
    $firstGuide = [IO.File]::ReadAllText((Join-Path $dist 'content\guide-001.md'), [Text.Encoding]::UTF8)
    $appScript = [IO.File]::ReadAllText((Join-Path $dist 'app.js'), [Text.Encoding]::UTF8)
    $styles = [IO.File]::ReadAllText((Join-Path $dist 'styles.css'), [Text.Encoding]::UTF8)
    if ($contentCount -ne $GuideCount) { throw "Expected $GuideCount content routes, found $contentCount." }
    if ([regex]::Matches($guides, 'class="library-card"').Count -ne ($GuideCount + 1)) { throw 'The Guides card count is incorrect.' }
    if ($config -match 'ATHENA_SEARCH_PATHS|namespace:\s*''athena-v3''') { throw 'The retired Docsify search configuration remains.' }
    if ($indexHtml -match 'vendor/search\.min\.js' -or $indexHtml -notmatch 'id="athena-search"') { throw 'The Athena-owned search form is not configured correctly.' }
    if ($indexHtml -notmatch '/vendor/vue\.css\?v=[0-9a-f]{12}') { throw 'The immutable Docsify theme URL is not content-versioned.' }
    if ($searchPage -notmatch 'id="search-page-slot"' -or $searchPage -notmatch 'id="search-results"') { throw 'The dedicated search route is incomplete.' }
    if ($searchIndex.Count -ne ($GuideCount + 2)) { throw "Expected $($GuideCount + 2) search records, found $($searchIndex.Count)." }
    $indexedGuide = $searchIndex | Where-Object title -eq 'Synthetic guide 1' | Select-Object -First 1
    if (-not $indexedGuide -or $indexedGuide.route -ne '#/content/guide-001' -or @($indexedGuide.headings).Count -ne 4 -or (@($indexedGuide.headings.level) -join ',') -ne '1,2,3,4') { throw 'Guide search metadata or heading sections are incomplete.' }
    $sidebar = [IO.File]::ReadAllText((Join-Path $dist '_sidebar.md'), [Text.Encoding]::UTF8)
    if ([regex]::Matches($sidebar, '(?m)^  - \[').Count -ne 7 -or $sidebar -notmatch '(?m)^- Biblioteca\r?$' -or $sidebar -notmatch '(?m)^- Participar\r?$') { throw 'The grouped portal rail is incomplete.' }
    $runtime = [IO.File]::ReadAllText((Join-Path $dist 'vendor\docsify.min.js'), [Text.Encoding]::UTF8)
    if ($runtime -notmatch 'Docsify v5\.0\.0') { throw 'The installed Docsify v5 runtime was not shipped.' }
    if (-not ($searchIndex | Where-Object kind -eq 'pdf') -or -not ($searchIndex | Where-Object kind -eq 'download')) { throw 'PDF and download search records are missing.' }
    if ($guides -notmatch '<option value="PDF">PDF</option>' -or $guides -notmatch 'data-tags="PDF"') { throw 'Unmatched PDFs must have a selectable PDF tag.' }
    if (-not (Test-Path -LiteralPath (Join-Path $dist 'content\guide-001.md'))) { throw 'An existing guide route was not preserved.' }
    if ($firstGuide -notmatch 'Guía de implementación' -or $firstGuide -match 'GuÃ') { throw 'UTF-8 guide text was not preserved.' }
    if ($catalog -match '1drv\.ms|onedrive\.live\.com') { throw 'Private OneDrive links entered catalog.json.' }
    if ($searchIndexJson -match '1drv\.ms|onedrive\.live\.com') { throw 'Private OneDrive links entered search-index.json.' }
    if ($firstGuide -notmatch '## Test section' -or $firstGuide -notmatch '### Test detail') { throw 'Nested guide headings were not preserved.' }
    if ($appScript -notmatch 'h1\[id\],h2\[id\],h3\[id\]' -or $styles -notmatch '\.page-tree') { throw 'Automatic page-tree assets are missing.' }
    if ($appScript -notmatch "fetch\('/search-index\.json'\)" -or $appScript -notmatch 'replaceSearchUrl' -or $styles -notmatch '\.search-result') { throw 'Dedicated search assets are missing.' }

    $scalar = New-Source 'scalar-tags'
    Write-Guide $scalar 'scalar' '{"kind":"guide","date":"2026-08-19","author":"Test","summary":"Test","tags":"Test","slug":"scalar"}'
    Assert-BuildFails $scalar 'Metadata tags must be an array'

    $escaped = New-Source 'escaped-pdf'
    [IO.File]::WriteAllBytes((Join-Path $escaped 'outside.pdf'), [Text.Encoding]::ASCII.GetBytes('%PDF-1.4'))
    Write-Guide $escaped 'escaped' '{"kind":"guide","date":"2026-08-19","author":"Test","summary":"Test","tags":[],"slug":"escaped","pdf":"../outside.pdf"}'
    Assert-BuildFails $escaped 'does not exist below docs'

    $missing = New-Source 'missing-pdf'
    Write-Guide $missing 'missing' '{"kind":"guide","date":"2026-08-19","author":"Test","summary":"Test","tags":[],"slug":"missing","pdf":"missing.pdf"}'
    Assert-BuildFails $missing 'does not exist below docs'

    $oversized = New-Source 'oversized-pdf'
    $stream = [IO.File]::Create((Join-Path $oversized 'docs\large.pdf'))
    try { $stream.SetLength(25MB) } finally { $stream.Dispose() }
    Assert-BuildFails $oversized 'PDF files must be smaller than 25 MiB'

    & node (Join-Path $PSScriptRoot 'test-search.mjs')
    if ($LASTEXITCODE -ne 0) { throw 'Search logic checks failed.' }
    Write-Host "Build checks passed with $GuideCount guides and metadata, search, PDF, UTF-8, route, tag, and link regressions."
} finally {
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $cleanupRelative = [IO.Path]::GetRelativePath($resolvedTemp, $resolvedTestRoot)
    $escapesTemp = [IO.Path]::IsPathRooted($cleanupRelative) -or $cleanupRelative -eq '..' -or $cleanupRelative.StartsWith("..$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::Ordinal) -or $cleanupRelative.StartsWith("..$([IO.Path]::AltDirectorySeparatorChar)", [StringComparison]::Ordinal)
    if ($escapesTemp) { throw 'Refusing to remove a test directory outside the system temp directory.' }
    if (Test-Path -LiteralPath $resolvedTestRoot) { Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force }
}
