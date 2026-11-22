#!/usr/bin/env pwsh
# load-config.ps1 — Load and validate the roadmap extension configuration and emit
# a stable JSON contract on stdout. PowerShell mirror of load-config.sh.
#
# Deterministic only. Contains no judgment (Constitution Principle II).
# Resolution order per value: environment override -> roadmap-config.yml ->
# extension.yml defaults -> built-in default.
#
# Output (stdout, single line JSON):
#   {"roadmap_path":"...","roadmap_exists":bool,"adr_dir":"...","adr_present":bool,
#    "prd_globs":["...",...],"max_findings":N}
#
# Exit codes: 0 ok; 1 invalid configuration value.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --- Locate repo root (CWD-independent: walk up from the script's own location) --
function Find-SpecifyRoot([string]$startDir) {
    $d = $startDir
    while ($d) {
        if (Test-Path (Join-Path $d '.specify')) { return $d }
        $parent = Split-Path $d -Parent
        if (-not $parent -or $parent -eq $d) { break }
        $d = $parent
    }
    return $null
}

$repoRoot = Find-SpecifyRoot $PSScriptRoot
# Fall back to walking up from CWD (covers unusual install layouts).
if (-not $repoRoot) { $repoRoot = Find-SpecifyRoot (Get-Location).Path }
# Last resort: CWD (no spec-kit repo located — built-in defaults still apply below).
if (-not $repoRoot) { $repoRoot = (Get-Location).Path }

$configFile    = Join-Path $repoRoot '.specify/extensions/roadmap/roadmap-config.yml'
$extensionFile = Join-Path $repoRoot '.specify/extensions/roadmap/extension.yml'

# --- Built-in defaults ----------------------------------------------------------
$defRoadmapPath  = '.specify/memory/roadmap.md'
$defAdrDir       = 'docs/adr/'
$defMaxFindings  = '50'
$defPrdGlobs     = @('**/prd*.md','**/PRD*.md','**/prd-intake.yaml','**/product-spec.md','docs/product/**/*.md')

# --- Minimal YAML scalar reader -------------------------------------------------
function Get-YamlScalar([string]$key, [string]$file) {
    if (-not (Test-Path $file)) { return '' }
    $match = Select-String -Path $file -Pattern ("^\s*{0}:" -f [regex]::Escape($key)) | Select-Object -Last 1
    if (-not $match) { return '' }
    $raw = ($match.Line -replace '^[^:]*:', '').Trim()
    $raw = $raw -replace '^"(.*)"$', '$1'
    $raw = $raw -replace "^'(.*)'$", '$1'
    if ($raw -eq 'null' -or $raw -eq '~') { $raw = '' }
    return $raw
}

function Resolve-Value([string]$envVal, [string]$key, [string]$default) {
    if ($envVal) { return $envVal }
    $v = Get-YamlScalar $key $configFile
    if (-not $v) { $v = Get-YamlScalar $key $extensionFile }
    if (-not $v) { $v = $default }
    return $v
}

$roadmapPath = Resolve-Value $env:SPECKIT_ROADMAP_PATH 'path' $defRoadmapPath
$adrDir      = Resolve-Value $env:SPECKIT_ROADMAP_ADR_DIR 'dir' $defAdrDir
$maxFindings = Resolve-Value $env:SPECKIT_ROADMAP_MAX_FINDINGS 'max_findings' $defMaxFindings

# --- Validate -------------------------------------------------------------------
if ($maxFindings -notmatch '^[0-9]+$') {
    [Console]::Error.WriteLine("Error: report.max_findings must be a positive integer, got '$maxFindings'")
    exit 1
}

# --- Derived booleans -----------------------------------------------------------
# Absolute paths are used as-is; relative paths are resolved against repo root.
$roadmapAbs = if ([System.IO.Path]::IsPathRooted($roadmapPath)) { $roadmapPath } else { Join-Path $repoRoot $roadmapPath }
$roadmapExists = Test-Path -PathType Leaf $roadmapAbs
$adrAbs = if ([System.IO.Path]::IsPathRooted($adrDir)) { $adrDir } else { Join-Path $repoRoot $adrDir }
$adrPresent   = Test-Path -PathType Container $adrAbs

# --- PRD globs ------------------------------------------------------------------
$prdGlobs = @()
if ($env:SPECKIT_ROADMAP_PRD_GLOBS) {
    $prdGlobs = $env:SPECKIT_ROADMAP_PRD_GLOBS.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
} else {
    foreach ($f in @($configFile, $extensionFile)) {
        if ((Test-Path $f) -and (Select-String -Path $f -Pattern '^\s*globs:' -Quiet)) {
            $lines = Get-Content $f
            $ing = $false
            foreach ($line in $lines) {
                if ($line -match '^\s*globs:') { $ing = $true; continue }
                if ($ing -and $line -match '^\s*-\s*(.+)$') {
                    $item = $Matches[1].Trim() -replace '^"(.*)"$','$1' -replace "^'(.*)'$",'$1'
                    if ($item) { $prdGlobs += $item }
                    continue
                }
                if ($ing -and $line -match '^\s*[^\s-]') { $ing = $false }
            }
            if ($prdGlobs.Count -gt 0) { break }
        }
    }
    if ($prdGlobs.Count -eq 0) { $prdGlobs = $defPrdGlobs }
}

# --- Emit JSON contract ---------------------------------------------------------
$obj = [ordered]@{
    roadmap_path   = $roadmapPath
    roadmap_exists = [bool]$roadmapExists
    adr_dir        = $adrDir
    adr_present    = [bool]$adrPresent
    prd_globs      = @($prdGlobs)
    max_findings   = [int]$maxFindings
}
# Compress to a single line to match the bash contract.
$obj | ConvertTo-Json -Compress -Depth 5
