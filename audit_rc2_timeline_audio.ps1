param(
    [string]$ProjectRoot = (Get-Location).Path,
    [string]$ProjectId = "hogueras"
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path $ProjectRoot).Path
$OutDir = Join-Path $Root "workspace\audits\rc2_timeline_audio_audit"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$ReportTxt = Join-Path $OutDir "rc2_timeline_audio_audit.txt"
$ReportJson = Join-Path $OutDir "rc2_timeline_audio_audit.json"

$timelineCandidates = @(
    (Join-Path $Root "workspace\exports\$ProjectId\movie_runtime_rc1\timeline.json"),
    (Join-Path $Root "workspace\exports\$ProjectId\rc2\timeline.json"),
    (Join-Path $Root "workspace\exports\$ProjectId\timeline.json")
)

$timelinePath = $timelineCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

$patterns = @(
    "timeline.json",
    "timeline",
    "MovieRuntimeRC1",
    "movie_runtime",
    "render_preview_rc2",
    "phase4_av_master_rc2",
    "visual_master_rc2",
    "audio",
    "music",
    "voice",
    "narration",
    "original_audio",
    "source_audio",
    "ambient",
    "sound",
    "sfx",
    "ffmpeg",
    "concat",
    "atrim",
    "amix",
    "acrossfade",
    "afade",
    "volume",
    "anullsrc",
    "clip",
    "asset",
    "reuse",
    "duplicate",
    "dedup",
    "selection",
    "selector"
)

$excludeDirs = @(
    "\.git\",
    "\.venv\",
    "\node_modules\",
    "\workspace\exports\",
    "\workspace\backups\",
    "\__pycache__\"
)

function Is-Excluded([string]$path) {
    foreach ($d in $excludeDirs) {
        if ($path -like "*$d*") { return $true }
    }
    return $false
}

$codeFiles = Get-ChildItem $Root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        -not (Is-Excluded $_.FullName) -and
        $_.Extension -in @(".py", ".ps1", ".json", ".yaml", ".yml", ".toml")
    }

$matches = New-Object System.Collections.Generic.List[object]

foreach ($file in $codeFiles) {
    try {
        $lineNo = 0
        Get-Content $file.FullName -ErrorAction Stop | ForEach-Object {
            $lineNo++
            $line = $_
            foreach ($pattern in $patterns) {
                if ($line -match [regex]::Escape($pattern)) {
                    $matches.Add([pscustomobject]@{
                        File = $file.FullName.Substring($Root.Length + 1)
                        Line = $lineNo
                        Pattern = $pattern
                        Text = $line.Trim()
                    })
                }
            }
        }
    } catch {}
}

$rankedFiles = $matches |
    Group-Object File |
    ForEach-Object {
        [pscustomobject]@{
            File = $_.Name
            Hits = $_.Count
            Patterns = ($_.Group.Pattern | Sort-Object -Unique) -join ", "
        }
    } |
    Sort-Object Hits -Descending

$timelineSummary = $null
$timelineErrors = @()

if ($timelinePath) {
    try {
        $timelineRaw = Get-Content $timelinePath -Raw -Encoding UTF8
        $timelineObj = $timelineRaw | ConvertFrom-Json -Depth 100

        $allNodes = New-Object System.Collections.Generic.List[object]

        function Walk-Node($node, [string]$path) {
            if ($null -eq $node) { return }

            if ($node -is [System.Collections.IDictionary]) {
                foreach ($key in $node.Keys) {
                    Walk-Node $node[$key] "$path.$key"
                }
                return
            }

            if ($node -is [pscustomobject]) {
                foreach ($prop in $node.PSObject.Properties) {
                    Walk-Node $prop.Value "$path.$($prop.Name)"
                }
                return
            }

            if (($node -is [System.Collections.IEnumerable]) -and -not ($node -is [string])) {
                $i = 0
                foreach ($item in $node) {
                    Walk-Node $item "$path[$i]"
                    $i++
                }
                return
            }

            if ($node -is [string]) {
                if ($node -match "\.(mp4|mov|mkv|avi|jpg|jpeg|png|webp|wav|mp3|m4a|aac)$") {
                    $allNodes.Add([pscustomobject]@{
                        Path = $path
                        Value = $node
                    })
                }
            }
        }

        Walk-Node $timelineObj '$'

        $assetUsage = $allNodes |
            Group-Object Value |
            ForEach-Object {
                [pscustomobject]@{
                    Asset = $_.Name
                    Count = $_.Count
                    Locations = ($_.Group.Path -join "; ")
                }
            } |
            Sort-Object Count -Descending

        $duplicates = $assetUsage | Where-Object { $_.Count -gt 1 }

        $timelineSummary = [pscustomobject]@{
            Path = $timelinePath.Substring($Root.Length + 1)
            ReferencedAssets = $allNodes.Count
            UniqueAssets = ($assetUsage | Measure-Object).Count
            DuplicateAssets = ($duplicates | Measure-Object).Count
            TopRepeatedAssets = @($duplicates | Select-Object -First 50)
        }

        $assetUsage | Export-Csv (Join-Path $OutDir "timeline_asset_usage.csv") -NoTypeInformation -Encoding UTF8
    }
    catch {
        $timelineErrors += $_.Exception.Message
    }
}

$likelyTimeline = $rankedFiles | Where-Object {
    $_.Patterns -match "timeline|MovieRuntimeRC1|movie_runtime"
} | Select-Object -First 40

$likelySelection = $rankedFiles | Where-Object {
    $_.Patterns -match "clip|asset|reuse|duplicate|dedup|selection|selector"
} | Select-Object -First 40

$likelyAudio = $rankedFiles | Where-Object {
    $_.Patterns -match "audio|music|voice|narration|original_audio|source_audio|ambient|sound|sfx|ffmpeg|concat|atrim|amix|acrossfade|afade|volume|anullsrc"
} | Select-Object -First 60

$result = [ordered]@{
    schema = "atlas_zero.rc2.timeline_audio_audit.v1"
    generated_at = (Get-Date).ToString("o")
    project_root = $Root
    project_id = $ProjectId
    timeline_path = $timelinePath
    timeline_errors = $timelineErrors
    timeline_summary = $timelineSummary
    likely_timeline_files = @($likelyTimeline)
    likely_asset_selection_files = @($likelySelection)
    likely_audio_files = @($likelyAudio)
    all_ranked_files = @($rankedFiles | Select-Object -First 150)
}

$result | ConvertTo-Json -Depth 20 | Set-Content $ReportJson -Encoding UTF8

"=" * 100 | Set-Content $ReportTxt -Encoding UTF8
"ATLAS ZERO RC2 — TIMELINE / ASSET SELECTION / AUDIO AUDIT" | Add-Content $ReportTxt
"=" * 100 | Add-Content $ReportTxt
"" | Add-Content $ReportTxt
"PROJECT ROOT: $Root" | Add-Content $ReportTxt
"PROJECT ID:   $ProjectId" | Add-Content $ReportTxt
"TIMELINE:     $timelinePath" | Add-Content $ReportTxt
"" | Add-Content $ReportTxt

"--- LIKELY TIMELINE PRODUCERS ---" | Add-Content $ReportTxt
$likelyTimeline | Format-Table -AutoSize | Out-String -Width 260 | Add-Content $ReportTxt

"--- LIKELY ASSET / CLIP SELECTION FILES ---" | Add-Content $ReportTxt
$likelySelection | Format-Table -AutoSize | Out-String -Width 260 | Add-Content $ReportTxt

"--- LIKELY AUDIO ASSEMBLY FILES ---" | Add-Content $ReportTxt
$likelyAudio | Format-Table -AutoSize | Out-String -Width 260 | Add-Content $ReportTxt

if ($timelineSummary) {
    "--- TIMELINE DUPLICATE ASSETS ---" | Add-Content $ReportTxt
    $timelineSummary.TopRepeatedAssets |
        Format-Table Count, Asset, Locations -AutoSize |
        Out-String -Width 320 |
        Add-Content $ReportTxt
}

"--- MATCH DETAILS ---" | Add-Content $ReportTxt
$matches |
    Sort-Object File, Line, Pattern |
    Format-Table File, Line, Pattern, Text -AutoSize |
    Out-String -Width 360 |
    Add-Content $ReportTxt

Write-Host ""
Write-Host "=== RC2 AUDIT COMPLETE ===" -ForegroundColor Green
Write-Host "Text report: $ReportTxt"
Write-Host "JSON report: $ReportJson"
if ($timelinePath) {
    Write-Host "Asset usage:  $(Join-Path $OutDir 'timeline_asset_usage.csv')"
} else {
    Write-Warning "timeline.json was not found in the expected locations."
}
Write-Host ""
Get-Item $ReportTxt, $ReportJson | Select-Object FullName, Length, LastWriteTime
