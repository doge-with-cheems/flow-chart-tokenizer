param(
    [string]$Dest = "$env:USERPROFILE\.config\opencode\skills\ngm-flow-tokenizer",
    [switch]$IncludeExamples
)

$ErrorActionPreference = "Stop"
$src = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path (Join-Path $src "SKILL.md"))) {
    throw "SKILL.md not found. Run this script from the tokeize-ngm project root."
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item (Join-Path $src "SKILL.md") $Dest -Force
Copy-Item (Join-Path $src "references") $Dest -Recurse -Force
Copy-Item (Join-Path $src "scripts") $Dest -Recurse -Force

if ($IncludeExamples) {
    Copy-Item (Join-Path $src "examples") $Dest -Recurse -Force
}

# Remove Python caches if present.
Get-ChildItem $Dest -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Installed: $Dest"
Write-Host "Skill ID : ngm-flow-tokenizer"
Write-Host "Restart OpenCode or start a new session to load it."
