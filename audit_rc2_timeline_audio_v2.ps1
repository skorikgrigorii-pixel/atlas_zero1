param(
    [string]$ProjectRoot = (Get-Location).Path,
    [string]$ProjectId = "hogueras"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path $ProjectRoot).Path
$Timeline = Join-Path $Root "workspace\exports\$ProjectId\rc2\timeline\timeline.json"
$State = Join-Path $Root "workspace\exports\$ProjectId\rc2\production_state.json"
$OutDir = Join-Path $Root "workspace\audits\rc2_timeline_audio_audit_v2"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if (-not (Test-Path $Timeline)) {
    throw "Timeline not found: $Timeline"
}

$sourceRoots = @(
    (Join-Path $Root "src"),
    (Join-Path $Root "tools"),
    (Join-Path $Root "scripts"),
    (Join-Path $Root "tests")
) | Where-Object { Test-Path $_ }

$codeFiles = foreach ($sr in $sourceRoots) {
    Get-ChildItem $sr -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".py", ".ps1", ".json", ".yaml", ".yml", ".toml") }
}

$searchTerms = @(
    "timeline.json",
    "timeline",
    "write_text",
    "json.dump",
    "json.dumps",
    "render_preview_rc2",
    "phase4_av_master_rc2",
    "visual_master_rc2",
    "production_state",
    "ffmpeg",
    "concat",
    "filter_complex",
    "amix",
    "amerge",
    "atrim",
    "asetpts",
    "acrossfade",
    "afade",
    "volume",
    "anullsrc",
    "map",
    "shortest",
    "stream_loop",
    "audio",
    "music",
    "voice",
    "sound",
    "sfx",
    "clip",
    "asset",
    "selector",
    "selection",
    "reuse",
    "duplicate",
    "dedup",
    "recent",
    "history"
)

$hits = New-Object System.Collections.Generic.List[object]

foreach ($file in $codeFiles) {
    try {
        $lines = Get-Content -LiteralPath $file.FullName -Encoding UTF8
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = [string]$lines[$i]
            foreach ($term in $searchTerms) {
                if ($line.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $hits.Add([pscustomobject]@{
                        File = $file.FullName.Substring($Root.Length + 1)
                        Line = $i + 1
                        Term = $term
                        Text = $line.Trim()
                    })
                }
            }
        }
    } catch {}
}

$ranked = $hits |
    Group-Object File |
    ForEach-Object {
        [pscustomobject]@{
            File = $_.Name
            Hits = $_.Count
            Terms = ($_.Group.Term | Sort-Object -Unique) -join ", "
        }
    } |
    Sort-Object Hits -Descending

$timelineObj = Get-Content -LiteralPath $Timeline -Raw -Encoding UTF8 | ConvertFrom-Json -Depth 100

$mediaRefs = New-Object System.Collections.Generic.List[object]
$scalarRefs = New-Object System.Collections.Generic.List[object]

function Walk($node, [string]$path) {
    if ($null -eq $node) { return }

    if ($node -is [pscustomobject]) {
        foreach ($p in $node.PSObject.Properties) {
            Walk $p.Value "$path.$($p.Name)"
        }
        return
    }

    if (($node -is [System.Collections.IEnumerable]) -and -not ($node -is [string])) {
        $idx = 0
        foreach ($item in $node) {
            Walk $item "$path[$idx]"
            $idx++
        }
        return
    }

    if ($node -is [string]) {
        $scalarRefs.Add([pscustomobject]@{ Path = $path; Value = $node })
        if ($node -match '(?i)\.(mp4|mov|mkv|avi|webm|jpg|jpeg|png|webp|wav|mp3|m4a|aac|flac)(\?.*)?$') {
            $mediaRefs.Add([pscustomobject]@{ Path = $path; Value = $node })
        }
    }
}

Walk $timelineObj '$'

$usage = $mediaRefs |
    Group-Object Value |
    ForEach-Object {
        [pscustomobject]@{
            Asset = $_.Name
            Count = $_.Count
            Locations = ($_.Group.Path -join "; ")
        }
    } |
    Sort-Object Count -Descending, Asset

$duplicates = $usage | Where-Object Count -gt 1

$audioLike = $scalarRefs | Where-Object {
    $_.Path -match '(?i)audio|music|voice|sound|sfx|ambient|original' -or
    $_.Value -match '(?i)\.(wav|mp3|m4a|aac|flac)$'
}

$timelineWriters = $hits | Where-Object {
    $_.Term -in @("timeline.json","json.dump","json.dumps","write_text") -or
    $_.Text -match '(?i)timeline.*(write|dump|save|export)|(?:write|dump|save|export).*timeline'
}

$selectionHits = $hits | Where-Object {
    $_.Term -in @("clip","asset","selector","selection","reuse","duplicate","dedup","recent","history")
}

$audioHits = $hits | Where-Object {
    $_.Term -in @("ffmpeg","concat","filter_complex","amix","amerge","atrim","asetpts","acrossfade","afade","volume","anullsrc","map","shortest","stream_loop","audio","music","voice","sound","sfx")
}

$usage | Export-Csv (Join-Path $OutDir "timeline_asset_usage.csv") -NoTypeInformation -Encoding UTF8
$duplicates | Export-Csv (Join-Path $OutDir "timeline_duplicates.csv") -NoTypeInformation -Encoding UTF8
$audioLike | Export-Csv (Join-Path $OutDir "timeline_audio_references.csv") -NoTypeInformation -Encoding UTF8
$timelineWriters | Export-Csv (Join-Path $OutDir "timeline_writer_hits.csv") -NoTypeInformation -Encoding UTF8
$selectionHits | Export-Csv (Join-Path $OutDir "asset_selection_hits.csv") -NoTypeInformation -Encoding UTF8
$audioHits | Export-Csv (Join-Path $OutDir "audio_assembly_hits.csv") -NoTypeInformation -Encoding UTF8
$ranked | Export-Csv (Join-Path $OutDir "ranked_source_files.csv") -NoTypeInformation -Encoding UTF8

$summary = [ordered]@{
    schema = "atlas_zero.rc2.timeline_audio_audit.v2"
    generated_at = (Get-Date).ToString("o")
    project_root = $Root
    project_id = $ProjectId
    timeline = $Timeline
    production_state = $(if (Test-Path $State) { $State } else { $null })
    source_files_scanned = @($codeFiles).Count
    total_source_hits = $hits.Count
    timeline_media_references = $mediaRefs.Count
    unique_media_assets = @($usage).Count
    repeated_media_assets = @($duplicates).Count
    audio_related_timeline_values = @($audioLike).Count
    top_repeated_assets = @($duplicates | Select-Object -First 100)
    top_source_files = @($ranked | Select-Object -First 100)
}

$summary | ConvertTo-Json -Depth 20 |
    Set-Content (Join-Path $OutDir "rc2_timeline_audio_audit_v2.json") -Encoding UTF8

$txt = Join-Path $OutDir "rc2_timeline_audio_audit_v2.txt"
"=" * 110 | Set-Content $txt -Encoding UTF8
"ATLAS ZERO RC2 — TARGETED TIMELINE / REPEAT / AUDIO AUDIT V2" | Add-Content $txt
"=" * 110 | Add-Content $txt
"" | Add-Content $txt
"Timeline: $Timeline" | Add-Content $txt
"State:    $State" | Add-Content $txt
"Source files scanned: $(@($codeFiles).Count)" | Add-Content $txt
"Media references:     $($mediaRefs.Count)" | Add-Content $txt
"Unique media assets:  $(@($usage).Count)" | Add-Content $txt
"Repeated assets:      $(@($duplicates).Count)" | Add-Content $txt
"" | Add-Content $txt

"--- TOP REPEATED TIMELINE ASSETS ---" | Add-Content $txt
$duplicates | Select-Object -First 100 |
    Format-Table Count, Asset, Locations -AutoSize |
    Out-String -Width 360 | Add-Content $txt

"--- LIKELY TIMELINE WRITERS ---" | Add-Content $txt
$timelineWriters |
    Sort-Object File, Line |
    Format-Table File, Line, Term, Text -AutoSize |
    Out-String -Width 360 | Add-Content $txt

"--- RANKED SOURCE FILES ---" | Add-Content $txt
$ranked | Select-Object -First 100 |
    Format-Table File, Hits, Terms -AutoSize |
    Out-String -Width 300 | Add-Content $txt

"--- AUDIO ASSEMBLY HITS ---" | Add-Content $txt
$audioHits |
    Sort-Object File, Line |
    Format-Table File, Line, Term, Text -AutoSize |
    Out-String -Width 360 | Add-Content $txt

Write-Host ""
Write-Host "=== TARGETED RC2 AUDIT COMPLETE ===" -ForegroundColor Green
Get-ChildItem $OutDir -File | Select-Object Name, Length, LastWriteTime
