param(
    [string]$Root = ".",
    [string]$OutDir = ".\audit_rc2_production"
)

$ErrorActionPreference = "Stop"
$src = Join-Path $Root "src\az_enterprise\core"
if (-not (Test-Path $src)) {
    throw "Core directory not found: $src"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$patterns = @(
    "RenderEngineRC1", "RenderEngineRC2", "ffmpeg", "ffprobe",
    "audio", "ambient", "natural_sound", "music", "mix", "mixer", "sound",
    "transition", "dissolve", "fade", "camera_motion", "montage", "compositor",
    "duplicate", "repeated", "max_use", "rhythm", "duration_sec",
    "ProjectConfigRC2", "QualityGateRC2", "AssignmentEngineRC2", "AssetEngineRC2",
    "StoryEngine", "production_script", "timeline_path", "canonical_render_path",
    "render_rc1", "movie_runtime_rc1", "franklin_render_rc1"
)

$files = Get-ChildItem $src -Recurse -File -Include *.py

$inventory = foreach ($file in $files) {
    $text = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    $hits = @()
    foreach ($p in $patterns) {
        if ($text -match [regex]::Escape($p)) { $hits += $p }
    }
    if ($hits.Count -gt 0) {
        [pscustomobject]@{
            File = $file.FullName.Substring((Resolve-Path $Root).Path.Length).TrimStart('\')
            Size = $file.Length
            Modified = $file.LastWriteTime.ToString("s")
            Matches = ($hits -join ", ")
        }
    }
}

$inventory | Sort-Object File | Export-Csv (Join-Path $OutDir "module_inventory.csv") -NoTypeInformation -Encoding UTF8
$inventory | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir "module_inventory.json") -Encoding UTF8

$searchReport = Join-Path $OutDir "code_matches.txt"
"ATLAS ZERO RC2 PRODUCTION CONTOUR AUDIT`r`nGenerated: $(Get-Date -Format s)`r`n" | Set-Content $searchReport -Encoding UTF8

foreach ($p in $patterns) {
    "`r`n==================== $p ====================`r`n" | Add-Content $searchReport -Encoding UTF8
    Select-String -Path ($files.FullName) -Pattern $p -SimpleMatch -Context 3,6 -ErrorAction SilentlyContinue |
        ForEach-Object { $_.ToString() } |
        Add-Content $searchReport -Encoding UTF8
}

$targetNames = @(
    "render_engine_rc2.py",
    "render_engine_rc1.py",
    "project_config_rc2.py",
    "quality_gate_rc2.py",
    "assignment_engine_rc2.py",
    "assignment_policy_rc2.py",
    "asset_engine_rc2.py",
    "story_engine.py",
    "story_engine_runtime.py",
    "timeline_engine_rc2.py",
    "production_script_assembler_rc2.py",
    "production_script_regenerator_rc2.py",
    "postproduction_quality_rc2.py"
)

$targetDir = Join-Path $OutDir "target_files"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
foreach ($name in $targetNames) {
    Get-ChildItem $src -Recurse -File -Filter $name -ErrorAction SilentlyContinue |
        ForEach-Object { Copy-Item $_.FullName (Join-Path $targetDir $_.Name) -Force }
}

$backupDir = Join-Path $OutDir "render_backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Get-ChildItem $src -Recurse -File | Where-Object {
    $_.Name -match "render_engine.*(backup|bak|before|zero)"
} | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $backupDir $_.Name) -Force
}

$projectScripts = Get-ChildItem (Join-Path $Root "workspace\projects") -Recurse -File -Filter "production_script*.json" -ErrorAction SilentlyContinue
$projectScripts | Select-Object FullName, Length, LastWriteTime |
    Export-Csv (Join-Path $OutDir "production_script_paths.csv") -NoTypeInformation -Encoding UTF8

$legacyRefs = Select-String -Path ($files.FullName) -Pattern "RenderEngineRC1|render_rc1|movie_runtime_rc1|franklin_render_rc1" -Context 2,4 -ErrorAction SilentlyContinue
$legacyRefs | ForEach-Object { $_.ToString() } | Set-Content (Join-Path $OutDir "legacy_dependency_map.txt") -Encoding UTF8

Compress-Archive -Path "$OutDir\*" -DestinationPath "$OutDir.zip" -Force

Write-Host "AUDIT COMPLETE" -ForegroundColor Green
Write-Host "Folder: $OutDir"
Write-Host "Archive: $OutDir.zip"
