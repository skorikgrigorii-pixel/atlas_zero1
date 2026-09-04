$ErrorActionPreference = "Stop"

$root = Get-Location
$path = Join-Path $root "src\az_enterprise\core\voice_production_engine_rc2.py"

if (-not (Test-Path $path -PathType Leaf)) {
    throw "File not found: $path"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root "workspace\backups\voice_clean_provider_output_$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item $path (Join-Path $backupDir "voice_production_engine_rc2.py") -Force

$content = [System.IO.File]::ReadAllText(
    $path,
    [System.Text.Encoding]::UTF8
)

# 1. Remove the provider-only SSML/break suffix.
$oldBreak = @'
        # Give ElevenLabs enough generated audio after the final word.
        # The break is sent only to the provider and is not stored
        # in the approved narration script.
        synthesis_text = (
            text
            + "`n<break time=""0.8s"" />"
        )

        provider_result = provider.synthesize(
            text=synthesis_text,
'@

$newBreak = @'
        provider_result = provider.synthesize(
            text=text,
'@

if ($content.Contains($oldBreak)) {
    $content = $content.Replace($oldBreak, $newBreak)
}
elseif ($content -match 'text=synthesis_text') {
    throw "A synthesis_text variant exists but did not match the expected block."
}

# 2. Make -af optional. An empty filter list currently causes FFmpeg failure.
$oldCommand = @'
        self._run_command(
            [
                ffmpeg,
                "-y",
                "-i",
                str(block_path),
                "-af",
                ",".join(audio_filters),
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            (
                "ElevenLabs audio preparation failed "
                f"for {scene_id}"
            ),
        )
'@

$newCommand = @'
        preparation_command = [
            ffmpeg,
            "-y",
            "-i",
            str(block_path),
        ]

        if audio_filters:
            preparation_command.extend([
                "-af",
                ",".join(audio_filters),
            ])

        preparation_command.extend([
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ])

        self._run_command(
            preparation_command,
            (
                "ElevenLabs audio preparation failed "
                f"for {scene_id}"
            ),
        )
'@

if (-not $content.Contains($oldCommand)) {
    throw "FFmpeg preparation block was not found. File was not changed."
}

$content = $content.Replace($oldCommand, $newCommand)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $path,
    $content,
    $utf8NoBom
)

& ".\.venv\Scripts\python.exe" -m py_compile $path

if ($LASTEXITCODE -ne 0) {
    throw "Python syntax check failed."
}

Write-Host ""
Write-Host "PATCH INSTALLED" -ForegroundColor Green
Write-Host "Removed ElevenLabs break tag."
Write-Host "FFmpeg now works when no audio filters are required."
Write-Host "Backup: $backupDir"
Write-Host ""
Write-Host "Delete VO01 cache and regenerate:" -ForegroundColor Cyan
Write-Host '$audio = ".\workspace\projects\hogueras\01_Audio"'
Write-Host 'Remove-Item "$audio\voice_blocks\voice_block_01.mp3","$audio\scenes\VO01.wav","$audio\voice_report_VO01.json","$audio\voice_manifest_VO01.json" -Force -ErrorAction SilentlyContinue'
Write-Host '.\.venv\Scripts\python.exe -m az_enterprise.cli voice-rc2 hogueras --scene-id VO01'
