param([uint32]$ProductPid = 0)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$productText = if ($ProductPid -gt 0) { [string]$ProductPid } else { Read-Host 'Team product PID' }
$productNumber = [uint32]0
if (-not [uint32]::TryParse($productText, [ref]$productNumber) -or $productNumber -eq 0) {
    throw 'Enter the positive product PID from your own platform product.'
}
$secureProductSecret = Read-Host 'Product SECRET (hidden)' -AsSecureString
$productSecret = [System.Net.NetworkCredential]::new('', $secureProductSecret).Password
try {
    if ($productSecret -notmatch '^[A-Za-z0-9_-]{8,128}$') {
        throw 'Unexpected product secret format; no configuration saved.'
    }
    $localDirectory = Join-Path $repoRoot '.local'
    New-Item -ItemType Directory -Force -Path $localDirectory | Out-Null
    @{ pid = $productNumber; secret = $productSecret } | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $localDirectory 'product.json') -Encoding utf8
    Write-Host 'Saved only in ignored .local/product.json. Rebuild and flash before pairing.'
} finally {
    $productSecret = $null
}
