$ErrorActionPreference = "Stop"

$repo = (Get-Location).Path
$director = Join-Path $repo "src\az_enterprise\core\director_core_rc2.py"
$narrative = Join-Path $repo "src\az_enterprise\core\narrative_runtime_rc2.py"

if (-not (Test-Path $director -PathType Leaf)) { throw "Director file not found: $director" }
if (-not (Test-Path $narrative -PathType Leaf)) { throw "Narrative runtime file not found: $narrative" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $repo "workspace\backups\rc2_external_script_policy_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $director (Join-Path $backup "director_core_rc2.py") -Force
Copy-Item $narrative (Join-Path $backup "narrative_runtime_rc2.py") -Force

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$narrativeText = [System.IO.File]::ReadAllText($narrative, [System.Text.Encoding]::UTF8)
$validationAnchor = @'
        self._validate_result(payload)
'@
$validationReplacement = @'
        if (
            self.mode != "local_fallback"
            and bool(payload.get("fallback_used"))
        ):
            raise RuntimeError(
                "Production narration is blocked: "
                f"mode={self.mode!r}, "
                f"provider_status={payload.get('provider_status')!r}. "
                "Import an approved external script or complete "
                "the configured documentary provider successfully."
            )

        self._validate_result(payload)
'@
if (-not $narrativeText.Contains($validationAnchor)) { throw "Narrative validation anchor was not found." }
$narrativeText = $narrativeText.Replace($validationAnchor, $validationReplacement)
[System.IO.File]::WriteAllText($narrative, $narrativeText, $utf8NoBom)

$directorText = [System.IO.File]::ReadAllText($director, [System.Text.Encoding]::UTF8)

if ($directorText -notmatch 'from pathlib import Path') {
    $directorText = [regex]::Replace(
        $directorText,
        'from __future__ import annotations\r?\n',
        { param($m) $m.Value + "`nfrom pathlib import Path`n" },
        1
    )
}

if ($directorText -notmatch 'from \.narrative_runtime_rc2 import NarrativeRuntimeRC2') {
    $importAnchor = 'from \.voice_production_engine_rc2 import VoiceProductionEngineRC2\r?\n'
    if ($directorText -notmatch $importAnchor) { throw "VoiceProductionEngineRC2 import anchor was not found." }
    $directorText = [regex]::Replace(
        $directorText,
        $importAnchor,
        {
            param($m)
            $m.Value +
            "from .narrative_runtime_rc2 import NarrativeRuntimeRC2`n" +
            "from .production_script_regenerator_rc2 import (`n" +
            "    ProductionScriptRegeneratorRC2,`n" +
            ")`n"
        },
        1
    )
}

$methodAnchor = @'
    def _stage_services(self) -> dict[str, Callable[[], dict[str, Any]]]:
'@
if (-not $directorText.Contains($methodAnchor)) { throw "_stage_services anchor was not found." }

$methods = @'
    def _discover_approved_external_script(self) -> Path | None:
        script_dir = self.config.project_dir / "script"
        candidates = (
            script_dir / "approved_external_script.json",
            script_dir / "approved_external_script.md",
            script_dir / "approved_external_script.txt",
            script_dir / "external_script.json",
            script_dir / "external_script.md",
            script_dir / "external_script.txt",
        )
        for path in candidates:
            if path.exists() and path.is_file():
                return path
        return None

    def _run_voice_stage(self) -> dict[str, Any]:
        external_script = self._discover_approved_external_script()
        if external_script is None:
            raise RuntimeError(
                "VOICE_BLOCKED_APPROVED_SCRIPT_REQUIRED: "
                "No approved external script was found in "
                f"{self.config.project_dir / 'script'}. "
                "Expected approved_external_script.json/.md/.txt "
                "or external_script.json/.md/.txt."
            )

        narrative_report = NarrativeRuntimeRC2(
            self.config,
            mode="external_script",
            allow_paid=False,
            external_script_path=external_script,
        ).run()

        if (
            narrative_report.get("provider_status")
            != "external_script_loaded"
            or bool(narrative_report.get("fallback_used"))
        ):
            raise RuntimeError(
                "External narration import did not produce "
                "an approved canonical result."
            )

        production_script_report = (
            ProductionScriptRegeneratorRC2(
                self.config,
            ).run()
        )

        voice_report = VoiceProductionEngineRC2(
            self.config,
        ).run()

        return {
            "state": voice_report.get("state", "VOICE_READY"),
            "project_id": self.config.project_id,
            "authority": "DirectorCoreRC2",
            "policy": "approved_external_script_only",
            "external_script": str(external_script),
            "narrative_report": narrative_report,
            "production_script_report": production_script_report,
            "voice_report": voice_report,
        }

'@
$directorText = $directorText.Replace($methodAnchor, $methods + $methodAnchor)

$oldVoiceBlock = @'
            "voice": lambda: {
                "state": "VOICE_SKIPPED_TEMPORARY",
                "project_id": self.config.project_id,
                "reason": (
                    "Temporary bypass of ElevenLabs. "
                    "Voice production is intentionally disabled "
                    "until the narration script is approved."
                ),
            },
'@
$newVoiceBlock = @'
            "voice": self._run_voice_stage,
'@
if (-not $directorText.Contains($oldVoiceBlock)) { throw "Temporary voice bypass block was not found." }
$directorText = $directorText.Replace($oldVoiceBlock, $newVoiceBlock)
[System.IO.File]::WriteAllText($director, $directorText, $utf8NoBom)

& .\.venv\Scripts\python.exe -m py_compile `
    ".\src\az_enterprise\core\narrative_runtime_rc2.py" `
    ".\src\az_enterprise\core\director_core_rc2.py"

if ($LASTEXITCODE -ne 0) {
    Copy-Item (Join-Path $backup "director_core_rc2.py") $director -Force
    Copy-Item (Join-Path $backup "narrative_runtime_rc2.py") $narrative -Force
    throw "Syntax validation failed. Original files were restored."
}

Write-Host ""
Write-Host "RC2 EXTERNAL SCRIPT POLICY INSTALLED" -ForegroundColor Green
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "Approved script directory:"
Write-Host (Join-Path $repo "workspace\projects\hogueras\script")
Write-Host ""
Write-Host "No OpenAI or ElevenLabs request was started."
