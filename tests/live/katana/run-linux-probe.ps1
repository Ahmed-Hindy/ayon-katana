param(
    [string] $Image = "ayon-katana/katana9-rocky:9.0v1",
    [string] $LicenseServer = "4101@host.docker.internal"
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$probeScript = "/workspace/tests/live/katana/linux_host_probe.py"

& docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Linux Katana image is unavailable: $Image"
}

& docker run --rm `
    --add-host "host.docker.internal:host-gateway" `
    -e "foundry_LICENSE=$LicenseServer" `
    -v "${repositoryRoot}:/workspace:ro" `
    $Image `
    /opt/Katana9.0v1/bin/katanaBin `
    --script $probeScript
if ($LASTEXITCODE -ne 0) {
    throw "Linux Katana host probe failed with exit code $LASTEXITCODE."
}
