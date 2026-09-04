param(
    [string]$ProjectRoot = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path $ProjectRoot).Path
$OutDir = Join-Path $Root "workspace\audits\rc2_existing_quality_audit"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$roots = @(
    (Join-Path $Root "src"),
    (Join-Path $Root "tools"),
    (Join-Path $Root "scripts"),
    (Join-Path $Root "tests")
) | Where-Object { Test-Path $_ }

$files = foreach ($r in $roots) {
    Get-ChildItem $r -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".py", ".ps1", ".json", ".yaml", ".yml", ".toml") }
}

$terms = @(
    "audit",
    "validator",
    "validation",
    "validate",
    "verifier",
    "verify",
    "checker",
    "check",
    "inspector",
    "reviewer",
    "quality_gate",
    "quality gate",
    "qualitygate",
    "preflight",
    "integrity",
    "continuity",
    "duplicate",
    "dedup",
    "reuse",
    "timeline",
    "audio",
    "music",
    "sound",
    "ffprobe",
    "ffmpeg",
    "freeze",
    "frozen",
    "black frame",
    "silence",
    "sync",
    "overlap"
)

$hits = New-Object System.Collections.Generic.List[object]

foreach ($file in $files) {
    try {
        $lines = Get-Content -LiteralPath $file.FullName -Encoding UTF8
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = [string]$lines[$i]
            foreach ($term in $terms) {
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
    Sort-Object -Property Hits -Descending

$definitions = $hits | Where-Object {
    $_.Text -match '^\s*(class|def)\s+.*(Audit|Validator|Validation|Verifier|Checker|Inspector|Quality|Preflight|Integrity|Continuity)'
}

$imports = $hits | Where-Object {
    $_.Text -match '^\s*(from|import)\s+.*(audit|validator|validation|verifier|checker|quality|preflight|integrity|continuity)'
}

$runtimeRefs = $hits | Where-Object {
    $_.File -match '(?i)runtime|pipeline|director|orchestrator|render|movie' -and
    $_.Term -in @("audit","validator","validation","validate","verifier","verify","checker","check","quality_gate","quality gate","qualitygate","preflight","integrity","continuity")
}

$timelineRefs = $hits | Where-Object {
    $_.Term -in @("timeline","duplicate","dedup","reuse","continuity")
}

$audioRefs = $hits | Where-Object {
    $_.Term -in @("audio","music","sound","ffprobe","ffmpeg","freeze","frozen","black frame","silence","sync","overlap")
}

$ranked | Export-Csv (Join-Path $OutDir "ranked_quality_files.csv") -NoTypeInformation -Encoding UTF8
$definitions | Export-Csv (Join-Path $OutDir "quality_definitions.csv") -NoTypeInformation -Encoding UTF8
$imports | Export-Csv (Join-Path $OutDir "quality_imports.csv") -NoTypeInformation -Encoding UTF8
$runtimeRefs | Export-Csv (Join-Path $OutDir "runtime_quality_references.csv") -NoTypeInformation -Encoding UTF8
$timelineRefs | Export-Csv (Join-Path $OutDir "timeline_quality_references.csv") -NoTypeInformation -Encoding UTF8
$audioRefs | Export-Csv (Join-Path $OutDir "audio_quality_references.csv") -NoTypeInformation -Encoding UTF8

$summary = [ordered]@{
    schema = "atlas_zero.rc2.existing_quality_audit.v1"
    generated_at = (Get-Date).ToString("o")
    project_root = $Root
    files_scanned = @($files).Count
    total_hits = $hits.Count
    likely_quality_files = @($ranked | Select-Object -First 100)
    definitions = @($definitions)
    imports = @($imports)
    runtime_quality_references = @($runtimeRefs)
    timeline_quality_references = @($timelineRefs)
    audio_quality_references = @($audioRefs)
}

$summary | ConvertTo-Json -Depth 20 |
    Set-Content (Join-Path $OutDir "rc2_existing_quality_audit.json") -Encoding UTF8

$txt = Join-Path $OutDir "rc2_existing_quality_audit.txt"
"=" * 110 | Set-Content $txt -Encoding UTF8
"ATLAS ZERO RC2 — EXISTING QUALITY / AUDIT / PREFLIGHT INVENTORY" | Add-Content $txt
"=" * 110 | Add-Content $txt
"" | Add-Content $txt
"Project root: $Root" | Add-Content $txt
"Files scanned: $(@($files).Count)" | Add-Content $txt
"Total hits: $($hits.Count)" | Add-Content $txt
"" | Add-Content $txt

"--- TOP QUALITY-RELATED FILES ---" | Add-Content $txt
$ranked | Select-Object -First 100 |
    Format-Table File, Hits, Terms -AutoSize |
    Out-String -Width 300 | Add-Content $txt

"--- DEFINITIONS ---" | Add-Content $txt
$definitions |
    Sort-Object File, Line |
    Format-Table File, Line, Term, Text -AutoSize |
    Out-String -Width 360 | Add-Content $txt

"--- IMPORTS ---" | Add-Content $txt
$imports |
    Sort-Object File, Line |
    Format-Table File, Line, Term, Text -AutoSize |
    Out-String -Width 360 | Add-Content $txt

"--- RUNTIME / PIPELINE CONNECTIONS ---" | Add-Content $txt
$runtimeRefs |
    Sort-Object File, Line |
    Format-Table File, Line, Term, Text -AutoSize |
    Out-String -Width 360 | Add-Content $txt

"--- TIMELINE / DUPLICATE REFERENCES ---" | Add-Content $txt
$timelineRefs |
    Sort-Object File, Line |
    Format-Table File, Line, Term, Text -AutoSize |
    Out-String -Width 360 | Add-Content $txt

"--- AUDIO / FREEZE / SYNC REFERENCES ---" | Add-Content $txt
$audioRefs |
    Sort-Object File, Line |
    Format-Table File, Line, Term, Text -AutoSize |
    Out-String -Width 360 | Add-Content $txt

Write-Host ""
Write-Host "=== EXISTING QUALITY AUDIT COMPLETE ===" -ForegroundColor Green
Get-ChildItem $OutDir -File | Select-Object Name, Length, LastWriteTime
