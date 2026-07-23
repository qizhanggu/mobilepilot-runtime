param(
    [string]$Manifest = "artifacts/evaluation/screenspot-v2-20260723/manifests/integration_audit_manifest.json",
    [string]$OutputDirectory = "data/screenspot-v2/audit-images"
)

$ErrorActionPreference = "Stop"
$repository = "Voxel51/ScreenSpot-v2"
$commit = "f221b744a2e73f64d5178a0548db8e667c4843e0"
$rows = Get-Content -Raw -Encoding utf8 -LiteralPath $Manifest | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

foreach ($row in $rows) {
    $name = [System.IO.Path]::GetFileName($row.image_repository_path)
    $target = Join-Path $OutputDirectory $name
    if (Test-Path -LiteralPath $target) {
        continue
    }
    $relative = $row.image_repository_path -replace "\\", "/"
    $url = "https://hf-mirror.com/datasets/$repository/resolve/$commit/$relative"
    & curl.exe -L --fail --show-error --output $target $url
    if ($LASTEXITCODE -ne 0) {
        throw "download failed: $relative"
    }
}

$downloaded = Get-ChildItem -LiteralPath $OutputDirectory -File
if ($downloaded.Count -ne $rows.Count) {
    throw "expected $($rows.Count) images, found $($downloaded.Count)"
}
Write-Output "downloaded=$($downloaded.Count)"
