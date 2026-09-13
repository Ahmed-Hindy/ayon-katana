param(
    [Parameter(Mandatory = $true)]
    [string] $Project,

    [Parameter(Mandatory = $true)]
    [string] $Folder,

    [Parameter(Mandatory = $true)]
    [string] $Task,

    [ValidateSet("native", "integration", "acceptance", "render", "automated")]
    [string] $Suite = "native",

    [string] $Application = "katana/9.0v1",

    [string] $Image = "ayon-katana/katana9-rocky:ayon-1.6.0",

    [string] $LicenseServer = "4101@host.docker.internal",

    [string] $Output = "",

    [string] $AyonConsole = $env:AYON_CONSOLE
)

$ErrorActionPreference = "Stop"

if (-not $AyonConsole) {
    throw "Pass -AyonConsole or set AYON_CONSOLE."
}
if (-not (Test-Path -LiteralPath $AyonConsole -PathType Leaf)) {
    throw "AYON Console does not exist: $AyonConsole"
}
if (-not $Folder.StartsWith("/")) {
    throw "-Folder must be an AYON folder path beginning with '/'."
}

$environment = @{
    AYON_KATANA_LIVE_PROJECT = $Project
    AYON_KATANA_LIVE_FOLDER = $Folder
    AYON_KATANA_LIVE_TASK = $Task
    AYON_KATANA_LIVE_APPLICATIONS = $Application
    AYON_KATANA_LIVE_SUITE = $Suite
    AYON_KATANA_LINUX_AYON_IMAGE = $Image
    AYON_KATANA_LINUX_LICENSE_SERVER = $LicenseServer
}
if ($Output) {
    $environment["AYON_KATANA_LINUX_OUTPUT"] = $Output
}

$previous = @{}
foreach ($name in $environment.Keys) {
    $previous[$name] = [Environment]::GetEnvironmentVariable(
        $name,
        [EnvironmentVariableTarget]::Process
    )
}

try {
    foreach ($item in $environment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $item.Key,
            $item.Value,
            [EnvironmentVariableTarget]::Process
        )
    }

    $bootstrap = Join-Path $PSScriptRoot "linux_ayon_bootstrap.py"
    & $AyonConsole --headless --use-staging run $bootstrap
    $exitCode = $LASTEXITCODE
} finally {
    foreach ($item in $previous.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $item.Key,
            $item.Value,
            [EnvironmentVariableTarget]::Process
        )
    }
}

if ($exitCode -ne 0) {
    throw "Linux AYON/Katana live runner failed with exit code $exitCode."
}
