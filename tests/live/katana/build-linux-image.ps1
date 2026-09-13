param(
    [string] $Image = "ayon-katana/katana9-rocky:9.0v1",
    [string] $BaseImage = "rockylinux:9",
    [string] $InstallerVolume = "katana9-installer-cache",
    [string] $InstallerFile = "Katana9.0v1-linux-x86-release-64.tgz",
    [string] $ExpectedSha256 = "c0a46189bb5f279d9dca8c16445dc45dfd65f722e290d73ed6020898e57de94e"
)

$ErrorActionPreference = "Stop"

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]] $Arguments)

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code ${LASTEXITCODE}: docker $($Arguments -join ' ')"
    }
}

$containerName = "ayon-katana9-build-$PID"
$archivePath = "/cache/$InstallerFile"

Invoke-Docker volume inspect $InstallerVolume *> $null

$hashOutput = & docker run --rm `
    -v "${InstallerVolume}:/cache:ro" `
    $BaseImage `
    sha256sum $archivePath
if ($LASTEXITCODE -ne 0) {
    throw "Katana installer was not found in Docker volume '$InstallerVolume'."
}
$actualHash = ($hashOutput -split "\s+")[0]
if ($actualHash -ne $ExpectedSha256) {
    throw "Katana installer checksum mismatch. Expected $ExpectedSha256, got $actualHash."
}

try {
    Invoke-Docker run --name $containerName -d `
        -v "${InstallerVolume}:/cache:ro" `
        $BaseImage sleep infinity *> $null

    $installCommand = @"
set -euo pipefail
rm -rf /tmp/katana-installer
mkdir -p /tmp/katana-installer
tar xzf '$archivePath' -C /tmp/katana-installer
cd /tmp/katana-installer
./install.sh --accept-eula --no-3delight --katana-path /opt/Katana9.0v1
dnf install -y \
    dbus-libs \
    libICE \
    libSM \
    libX11 \
    libglvnd-egl \
    libglvnd-glx \
    libglvnd-opengl \
    libxkbcommon \
    mesa-dri-drivers \
    mesa-libEGL \
    mesa-libGL \
    mesa-libGLU \
    pcre2-utf16
dnf clean all
rm -rf /var/cache/dnf /tmp/katana-installer
missing=`$(ldd /opt/Katana9.0v1/bin/katanaBin | grep 'not found' || true)
if [ -n "`$missing" ]; then
    echo "`$missing" >&2
    exit 1
fi
"@
    Invoke-Docker exec $containerName bash -lc $installCommand
    Invoke-Docker commit `
        --change "ENV KATANA_ROOT=/opt/Katana9.0v1" `
        $containerName $Image *> $null
} finally {
    & docker rm -f $containerName *> $null
}

$imageInfo = docker image inspect $Image --format "{{.Id}} {{.Size}}"
if ($LASTEXITCODE -ne 0) {
    throw "Built image could not be inspected: $Image"
}
Write-Host "Built $Image ($imageInfo)"
