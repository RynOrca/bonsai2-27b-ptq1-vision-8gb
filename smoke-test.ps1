[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:18200/v1',
    [string]$ImagePath
)

$ErrorActionPreference = 'Stop'
$base = $BaseUrl.TrimEnd('/')
$models = Invoke-RestMethod -Uri "$base/models" -TimeoutSec 60
if (-not @($models.data.id).Contains('qwen3.8-27b-long')) {
    throw 'qwen3.8-27b-long is absent from /v1/models'
}

$parts = @()
if ($ImagePath) {
    $path = [IO.Path]::GetFullPath($ImagePath)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Image not found: $path" }
    $extension = [IO.Path]::GetExtension($path).ToLowerInvariant()
    $mime = switch ($extension) {
        '.png' { 'image/png' }
        '.jpg' { 'image/jpeg' }
        '.jpeg' { 'image/jpeg' }
        '.webp' { 'image/webp' }
        default { throw 'Supported image types: PNG, JPEG, WebP' }
    }
    $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
    $parts += @{ type = 'image_url'; image_url = @{ url = "data:$mime;base64,$b64"; detail = 'auto' } }
    $parts += @{ type = 'text'; text = 'Describe the image briefly. Mention one detail visible only in the image.' }
} else {
    $parts += @{ type = 'text'; text = 'Reply with exactly OK' }
}

$body = @{
    model = 'qwen3.8-27b-long'
    messages = @(@{ role = 'user'; content = $parts })
    max_tokens = 128
    temperature = 0
} | ConvertTo-Json -Depth 10 -Compress

$response = Invoke-RestMethod -Uri "$base/chat/completions" -Method Post `
    -ContentType 'application/json' -Body $body -TimeoutSec 180
$answer = [string]$response.choices[0].message.content
if ([string]::IsNullOrWhiteSpace($answer)) { throw 'The model returned an empty answer' }
if (-not $ImagePath -and $answer.Trim() -ne 'OK') { throw "Unexpected text answer: $answer" }
Write-Host "PASS finish=$($response.choices[0].finish_reason) prompt=$($response.usage.prompt_tokens) output=$($response.usage.completion_tokens)"
Write-Host $answer
