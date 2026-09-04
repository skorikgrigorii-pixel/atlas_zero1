$ErrorActionPreference = "Stop"

$root = Get-Location
$path = Join-Path $root "src\az_enterprise\core\voice_production_engine_rc2.py"

if (-not (Test-Path $path -PathType Leaf)) {
    throw "File not found: $path"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root "workspace\backups\voice_preserve_natural_ending_$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item $path (Join-Path $backupDir "voice_production_engine_rc2.py") -Force

$content = [System.IO.File]::ReadAllText(
    $path,
    [System.Text.Encoding]::UTF8
)

$old = @'
        # Narration audio must end with the spoken text.
        # Scene timing belongs to the video timeline, not
        # to the voice file. Remove only trailing silence;
        # preserve pauses inside the narration.
        audio_filters.extend([
            "areverse",
            (
                "silenceremove="
                "start_periods=1:"
                "start_duration=0.35:"
                "start_threshold=-40dB"
            ),
            "areverse",
        ])
'@

$new = @'
        # Keep the provider's natural ending intact.
        # Do not pad narration to the scene duration and
        # do not trim quiet final phonemes.
'@

if (-not $content.Contains($old)) {
    throw "Trailing-silence filter block was not found. File was not changed."
}

$content = $content.Replace($old, $new)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $path,
    $content,
    $utf8NoBom
)

Write-Host ""
Write-Host "PATCH INSTALLED" -ForegroundColor Green
Write-Host "Natural speech ending will be preserved."
Write-Host "No scene-duration padding will be added."
Write-Host "Backup: $backupDir"
Write-Host ""

& ".\.venv\Scripts\python.exe" -m py_compile $path

if ($LASTEXITCODE -ne 0) {
    throw "Python syntax check failed."
}

Write-Host "Syntax: OK" -ForegroundColor Green
Write-Host ""
Write-Host "Regenerate VO01:" -ForegroundColor Cyan
Write-Host ".\.venv\Scripts\python.exe -m az_enterprise.cli voice-rc2 hogueras --scene-id VO01"
