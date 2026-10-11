[CmdletBinding()]
param([string]$AssetsDir, [string]$ManifestPath)

$ErrorActionPreference = 'Stop'
if (-not $AssetsDir) {
    $AssetsDir = Join-Path $PSScriptRoot '..\bonsai2-27b-ptq1-vision-8gb-assets'
}
$root = [IO.Path]::GetFullPath($AssetsDir)
$manifest = if ($ManifestPath) { [IO.Path]::GetFullPath($ManifestPath) } else { Join-Path $PSScriptRoot 'assets.sha256' }
$count = 0
$failed = 0

foreach ($line in Get-Content -LiteralPath $manifest) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -notmatch '^([A-Fa-f0-9]{64}) \*(.+)$') { throw "Invalid manifest line: $line" }
    $expected = $Matches[1].ToUpperInvariant()
    $relative = $Matches[2]
    if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') {
        throw "Unsafe manifest path: $relative"
    }
    $file = Join-Path $root ($relative -replace '/', '\')
    $count++
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        Write-Host "MISSING $relative"
        $failed++
        continue
    }
    $stream = [IO.File]::OpenRead($file)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '')
    } finally {
        $stream.Dispose()
        $hasher.Dispose()
    }
    if ($actual -ne $expected) {
        Write-Host "MISMATCH $relative"
        $failed++
        continue
    }
    Write-Host "OK $relative"
}

Write-Host "RESULT checked=$count failed=$failed"
if ($failed) { exit 1 }
