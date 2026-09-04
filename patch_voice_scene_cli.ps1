$ErrorActionPreference = "Stop"

$root = Get-Location
$cliPath = Join-Path $root "src\az_enterprise\cli.py"
$controlPath = Join-Path $root "src\az_enterprise\core\control_layer_rc2.py"

foreach ($path in @($cliPath, $controlPath)) {
    if (-not (Test-Path $path -PathType Leaf)) {
        throw "File not found: $path"
    }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root "workspace\backups\voice_scene_cli_$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

Copy-Item $cliPath (Join-Path $backupDir "cli.py") -Force
Copy-Item $controlPath (Join-Path $backupDir "control_layer_rc2.py") -Force

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ----------------------------------------------------------------------
# Patch cli.py
# ----------------------------------------------------------------------
$cli = [System.IO.File]::ReadAllText($cliPath, [System.Text.Encoding]::UTF8)

if ($cli -notmatch '"--scene-id"') {
    $old = @'
    voice_rc2_parser.add_argument(
        "--speech-rate",
        type=int,
        default=0,
    )
'@

    $new = @'
    voice_rc2_parser.add_argument(
        "--speech-rate",
        type=int,
        default=0,
    )
    voice_rc2_parser.add_argument(
        "--scene-id",
        default=None,
        help=(
            "Render only the specified scene "
            "(for example: VO01)."
        ),
    )
'@

    if (-not $cli.Contains($old)) {
        throw "Could not find the voice-rc2 argument block in cli.py"
    }

    $cli = $cli.Replace($old, $new)
}

if ($cli -notmatch 'scene_id=args\.scene_id') {
    $old = @'
        result = RC2ControlLayer(
            project_id=args.project_id,
            voice_name=args.voice_name,
            speech_rate=args.speech_rate,
        ).build_voice()
'@

    $new = @'
        result = RC2ControlLayer(
            project_id=args.project_id,
            voice_name=args.voice_name,
            speech_rate=args.speech_rate,
            scene_id=args.scene_id,
        ).build_voice()
'@

    if (-not $cli.Contains($old)) {
        throw "Could not find the voice-rc2 RC2ControlLayer call in cli.py"
    }

    $cli = $cli.Replace($old, $new)
}

[System.IO.File]::WriteAllText($cliPath, $cli, $utf8NoBom)

# ----------------------------------------------------------------------
# Patch control_layer_rc2.py
# ----------------------------------------------------------------------
$control = [System.IO.File]::ReadAllText(
    $controlPath,
    [System.Text.Encoding]::UTF8
)

if ($control -notmatch 'scene_id:\s*str\s*\|\s*None\s*=\s*None') {
    $old = @'
        voice_name: str = "Microsoft Irina Desktop",
        speech_rate: int = 0,
    ) -> None:
'@

    $new = @'
        voice_name: str = "Microsoft Irina Desktop",
        speech_rate: int = 0,
        scene_id: str | None = None,
    ) -> None:
'@

    if (-not $control.Contains($old)) {
        throw "Could not find RC2ControlLayer constructor signature"
    }

    $control = $control.Replace($old, $new)
}

if ($control -notmatch 'self\.scene_id\s*=\s*\(') {
    $old = @'
        self.voice_name = voice_name
        self.speech_rate = int(speech_rate)
'@

    $new = @'
        self.voice_name = voice_name
        self.speech_rate = int(speech_rate)
        self.scene_id = (
            str(scene_id).strip()
            if scene_id
            else None
        )
'@

    if (-not $control.Contains($old)) {
        throw "Could not find RC2ControlLayer instance assignments"
    }

    $control = $control.Replace($old, $new)
}

if ($control -notmatch 'scene_id=self\.scene_id') {
    $old = @'
        return VoiceProductionEngineRC2(
            self.config,
            voice_name=self.voice_name,
            speech_rate=self.speech_rate,
        ).run()
'@

    $new = @'
        return VoiceProductionEngineRC2(
            self.config,
            voice_name=self.voice_name,
            speech_rate=self.speech_rate,
            scene_id=self.scene_id,
        ).run()
'@

    if (-not $control.Contains($old)) {
        throw "Could not find VoiceProductionEngineRC2 call"
    }

    $control = $control.Replace($old, $new)
}

[System.IO.File]::WriteAllText($controlPath, $control, $utf8NoBom)

Write-Host ""
Write-Host "PATCH COMPLETED" -ForegroundColor Green
Write-Host "Backup: $backupDir"
Write-Host ""

Write-Host "Checking Python syntax..."
& ".\.venv\Scripts\python.exe" -m py_compile `
    ".\src\az_enterprise\cli.py" `
    ".\src\az_enterprise\core\control_layer_rc2.py" `
    ".\src\az_enterprise\core\voice_production_engine_rc2.py"

if ($LASTEXITCODE -ne 0) {
    throw "Python syntax check failed"
}

Write-Host "Syntax: OK" -ForegroundColor Green
Write-Host ""
Write-Host "Checking CLI option..."
& ".\.venv\Scripts\python.exe" -m az_enterprise.cli voice-rc2 --help

if ($LASTEXITCODE -ne 0) {
    throw "CLI help check failed"
}

Write-Host ""
Write-Host "READY FOR TEST:" -ForegroundColor Green
Write-Host ".\.venv\Scripts\python.exe -m az_enterprise.cli voice-rc2 hogueras --scene-id VO01"
