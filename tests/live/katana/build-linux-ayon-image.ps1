param(
    [string] $Image = "ayon-katana/katana9-rocky:ayon-1.6.0",
    [string] $BaseImage = "ayon-katana/katana9-rocky:9.0v1",
    [string] $InstallerVolume = "ayon-launcher-1.6.0-rocky9-cache",
    [string] $InstallerFile = "AYON-1.6.0-linux-rocky9.tar.gz",
    [string] $ExpectedSha256 = "9ba58cb5783085c0a94245c2b6c825581111240ece0d04bdd05e65a2b002655c"
)

$ErrorActionPreference = "Stop"

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]] $Arguments)

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code ${LASTEXITCODE}: docker $($Arguments -join ' ')"
    }
}

$containerName = "ayon-katana-linux-ayon-build-$PID"
$archivePath = "/cache/$InstallerFile"

Invoke-Docker volume inspect $InstallerVolume *> $null

$hashOutput = & docker run --rm `
    -v "${InstallerVolume}:/cache:ro" `
    $BaseImage `
    sha256sum $archivePath
if ($LASTEXITCODE -ne 0) {
    throw "AYON installer was not found in Docker volume '$InstallerVolume'."
}
$actualHash = ($hashOutput -split "\s+")[0]
if ($actualHash -ne $ExpectedSha256) {
    throw "AYON installer checksum mismatch. Expected $ExpectedSha256, got $actualHash."
}

try {
    Invoke-Docker run --name $containerName -d `
        -v "${InstallerVolume}:/cache:ro" `
        $BaseImage sleep infinity *> $null

    $installCommand = @"
set -euo pipefail
rm -rf /opt/ayon
mkdir -p /opt/ayon
tar xzf '$archivePath' -C /opt/ayon --strip-components=1
dnf install -y fontconfig freetype
dnf clean all
rm -rf /var/cache/dnf
test -x /opt/ayon/ayon
missing=""
for library in \
    /opt/ayon/vendor/python/PySide6/Qt/lib/libQt6Core.so.6 \
    /opt/ayon/vendor/python/PySide6/Qt/lib/libQt6Gui.so.6 \
    /opt/ayon/vendor/python/PySide6/Qt/lib/libQt6Widgets.so.6; do
    if [ -f "`$library" ]; then
        unresolved=`$(ldd "`$library" | grep 'not found' || true)
        if [ -n "`$unresolved" ]; then
            missing="`$missing`n`$library`n`$unresolved"
        fi
    fi
done
if [ -n "`$missing" ]; then
    echo "`$missing" >&2
    exit 1
fi
"@
    Invoke-Docker exec $containerName bash -lc $installCommand
    Invoke-Docker commit $containerName $Image *> $null
} finally {
    & docker rm -f $containerName *> $null
}

$imageInfo = docker image inspect $Image --format "{{.Id}} {{.Size}}"
if ($LASTEXITCODE -ne 0) {
    throw "Built image could not be inspected: $Image"
}
Write-Host "Built $Image ($imageInfo)"
