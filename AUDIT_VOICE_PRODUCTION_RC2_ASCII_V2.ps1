param(
    [string]$RepoRoot = (Get-Location).Path
)

$ErrorActionPreference = "Continue"

$repo = (Resolve-Path $RepoRoot).Path
$outputDir = Join-Path $repo "workspace\audits\voice_production"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$patterns = @(
    "voice",
    "narrat",
    "speech",
    "tts",
    "text.to.speech",
    "elevenlabs",
    "openai.*audio",
    "azure.*speech",
    "google.*speech",
    "polly",
    "coqui",
    "piper",
    "espeak",
    "pyttsx",
    "audio",
    "wav",
    "mp3",
    "master_audio",
    "voiceover",
    "speaker",
    "phoneme",
    "subtitle",
    "srt",
    "vtt"
)

$patternRegex = $patterns -join "|"

$extensions = @(
    ".py",
    ".ps1",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".txt",
    ".ini",
    ".cfg"
)

$excludedRegex = "\\(\.git|\.venv|venv|__pycache__|node_modules|workspace\\exports|workspace\\audits)\\"

$files = @(
    Get-ChildItem -Path $repo -Recurse -File -Force |
        Where-Object {
            ($extensions -contains $_.Extension.ToLowerInvariant()) -and
            ($_.FullName -notmatch $excludedRegex)
        }
)

$candidateFiles = @()
$references = @()

foreach ($file in $files) {
    $relativePath = $file.FullName.Substring($repo.Length).TrimStart("\")
    $filenameMatch = $relativePath -match $patternRegex

    $hits = @(
        Select-String `
            -Path $file.FullName `
            -Pattern $patternRegex `
            -AllMatches `
            -CaseSensitive:$false `
            -ErrorAction SilentlyContinue
    )

    if ($filenameMatch -or $hits.Count -gt 0) {
        $candidateFiles += [pscustomobject]@{
            path = $relativePath
            extension = $file.Extension
            size_bytes = $file.Length
            last_write_time = $file.LastWriteTime.ToString("s")
            filename_match = [bool]$filenameMatch
            reference_count = $hits.Count
        }
    }

    foreach ($hit in $hits) {
        $lineText = $hit.Line.Trim()

        if ($lineText.Length -gt 300) {
            $lineText = $lineText.Substring(0, 300)
        }

        $references += [pscustomobject]@{
            path = $relativePath
            line_number = $hit.LineNumber
            text = $lineText
        }
    }
}

$pythonFiles = @($files | Where-Object { $_.Extension -eq ".py" })
$syntaxResults = @()

foreach ($file in $pythonFiles) {
    $relativePath = $file.FullName.Substring($repo.Length).TrimStart("\")
    $compileOutput = @(
        & python -W default -m py_compile $file.FullName 2>&1
    )
    $compileExitCode = $LASTEXITCODE

    $warnings = @(
        $compileOutput |
            Where-Object {
                $_ -match "Warning:"
            }
    )

    $errors = @(
        $compileOutput |
            Where-Object {
                $_ -notmatch "Warning:"
            }
    )

    $syntaxResults += [pscustomobject]@{
        path = $relativePath
        ok = ($compileExitCode -eq 0)
        warning = if ($warnings.Count -eq 0) {
            $null
        }
        else {
            $warnings -join [Environment]::NewLine
        }
        error = if ($compileExitCode -eq 0) {
            $null
        }
        else {
            $errors -join [Environment]::NewLine
        }
    }
}

$likelyEntryPoints = @(
    $candidateFiles |
        Where-Object {
            $_.path -match "(run|main|cli|launcher|pipeline|runtime|orchestrator|director|render|movie)"
        } |
        Sort-Object path
)

$syntaxErrors = @(
    $syntaxResults |
        Where-Object { -not $_.ok }
)

$report = [ordered]@{
    audit_name = "ATLAS ZERO Voice Production Audit"
    generated_at = (Get-Date).ToString("o")
    repository_root = $repo
    summary = [ordered]@{
        scanned_files = $files.Count
        scanned_python_files = $pythonFiles.Count
        voice_candidate_files = $candidateFiles.Count
        voice_references = $references.Count
        python_syntax_errors = $syntaxErrors.Count
        python_syntax_warnings = @($syntaxResults | Where-Object { $_.warning }).Count
        likely_entry_points = $likelyEntryPoints.Count
    }
    candidate_files = @($candidateFiles | Sort-Object path)
    likely_entry_points = $likelyEntryPoints
    references = @($references | Sort-Object path, line_number)
    python_syntax = $syntaxResults
}

$jsonPath = Join-Path $outputDir "voice_production_audit.json"
$markdownPath = Join-Path $outputDir "voice_production_audit.md"

$jsonText = $report | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText(
    $jsonPath,
    $jsonText,
    [System.Text.UTF8Encoding]::new($false)
)

$markdown = New-Object System.Collections.Generic.List[string]

$markdown.Add("# ATLAS ZERO - Voice Production Audit")
$markdown.Add("")
$markdown.Add("Generated: $($report.generated_at)")
$markdown.Add("")
$markdown.Add("## Summary")
$markdown.Add("")
$markdown.Add("- Scanned files: $($report.summary.scanned_files)")
$markdown.Add("- Scanned Python files: $($report.summary.scanned_python_files)")
$markdown.Add("- Voice candidate files: $($report.summary.voice_candidate_files)")
$markdown.Add("- Voice references: $($report.summary.voice_references)")
$markdown.Add("- Python syntax errors: $($report.summary.python_syntax_errors)")
$markdown.Add("- Python syntax warnings: $($report.summary.python_syntax_warnings)")
$markdown.Add("- Likely entry points: $($report.summary.likely_entry_points)")
$markdown.Add("")
$markdown.Add("## Candidate files")
$markdown.Add("")

foreach ($item in $report.candidate_files) {
    $markdown.Add(
        "- " +
        $item.path +
        " | references=" +
        $item.reference_count +
        " | filename_match=" +
        $item.filename_match
    )
}

$markdown.Add("")
$markdown.Add("## Likely integration entry points")
$markdown.Add("")

if ($likelyEntryPoints.Count -eq 0) {
    $markdown.Add("- None")
}
else {
    foreach ($item in $likelyEntryPoints) {
        $markdown.Add("- " + $item.path)
    }
}

$markdown.Add("")
$markdown.Add("## Python syntax errors")
$markdown.Add("")

if ($syntaxErrors.Count -eq 0) {
    $markdown.Add("- None")
}
else {
    foreach ($item in $syntaxErrors) {
        $markdown.Add("- " + $item.path)
        $markdown.Add("  " + ($item.error -replace "\r?\n", " | "))
    }
}

$markdown.Add("")
$markdown.Add("## Voice-related references")
$markdown.Add("")

if ($references.Count -eq 0) {
    $markdown.Add("- None")
}
else {
    foreach ($item in ($references | Sort-Object path, line_number)) {
        $markdown.Add(
            "- " +
            $item.path +
            ":" +
            $item.line_number +
            " | " +
            $item.text
        )
    }
}

[System.IO.File]::WriteAllText(
    $markdownPath,
    ($markdown -join [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "ATLAS ZERO - VOICE PRODUCTION AUDIT"
Write-Host ("=" * 72)
Write-Host "Repository:           $repo"
Write-Host "Scanned files:        $($report.summary.scanned_files)"
Write-Host "Scanned Python files: $($report.summary.scanned_python_files)"
Write-Host "Candidate files:      $($report.summary.voice_candidate_files)"
Write-Host "Voice references:     $($report.summary.voice_references)"
Write-Host "Python syntax errors:   $($report.summary.python_syntax_errors)"
Write-Host "Python syntax warnings: $($report.summary.python_syntax_warnings)"
Write-Host "Likely entry points:    $($report.summary.likely_entry_points)"
Write-Host ""
Write-Host "JSON: $jsonPath"
Write-Host "MD:   $markdownPath"
