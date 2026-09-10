param(
    [Parameter(Mandatory = $true)]
    [string] $Project,

    [Parameter(Mandatory = $true)]
    [string] $Folder,

    [Parameter(Mandatory = $true)]
    [string] $Task,

    [ValidateSet("native", "integration", "existing", "all")]
    [string] $Suite = "native",

    [string] $Applications = "katana/9.0v1,katana/8.0v1",

    [string] $Workfile = "",

    [string] $Output = "",

    [int] $TimeoutSeconds = 240,

    [ValidateSet("staging", "production")]
    [string] $AyonVariant = "staging",

    [switch] $QuietHostOutput,

    [switch] $PublicOutput,

    [string] $AyonConsole = $env:AYON_CONSOLE
)

$ErrorActionPreference = "Stop"

if (-not $AyonConsole) {
    throw "Pass -AyonConsole or set the AYON_CONSOLE environment variable."
}
if (-not (Test-Path -LiteralPath $AyonConsole -PathType Leaf)) {
    throw "AYON Console does not exist: $AyonConsole"
}
if (-not $Folder.StartsWith("/")) {
    throw "-Folder must be an AYON folder path beginning with '/'."
}
if ($Suite -in @("existing", "all") -and -not $Workfile) {
    throw "-Workfile is required for the existing suite."
}
if ($Workfile -and -not (Test-Path -LiteralPath $Workfile -PathType Leaf)) {
    throw "Live-test workfile does not exist: $Workfile"
}
if ($TimeoutSeconds -lt 1) {
    throw "-TimeoutSeconds must be greater than zero."
}

$liveEnvironment = @{
    AYON_KATANA_LIVE_PROJECT = $Project
    AYON_KATANA_LIVE_FOLDER = $Folder
    AYON_KATANA_LIVE_TASK = $Task
    AYON_KATANA_LIVE_APPLICATIONS = $Applications
    AYON_KATANA_LIVE_SUITE = $Suite
    AYON_KATANA_LIVE_TIMEOUT = [string] $TimeoutSeconds
    AYON_KATANA_LIVE_WORKFILE = $Workfile
    AYON_KATANA_LIVE_OUTPUT = $Output
}
$previousEnvironment = @{}
foreach ($name in $liveEnvironment.Keys) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable(
        $name,
        [EnvironmentVariableTarget]::Process
    )
}

$exitCode = 1
try {
    foreach ($item in $liveEnvironment.GetEnumerator()) {
        if ($item.Value) {
            [Environment]::SetEnvironmentVariable(
                $item.Key,
                $item.Value,
                [EnvironmentVariableTarget]::Process
            )
        } else {
            [Environment]::SetEnvironmentVariable(
                $item.Key,
                $null,
                [EnvironmentVariableTarget]::Process
            )
        }
    }

    $runner = Join-Path $PSScriptRoot "run.py"
    $ayonArguments = @()
    if ($AyonVariant -eq "staging") {
        $ayonArguments += "--use-staging"
    }
    $ayonArguments += @("run", $runner)

    if ($QuietHostOutput) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $null = & $AyonConsole @ayonArguments 2>&1
            $exitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($Output) {
            $summaryName = if ($PublicOutput) {
                "public-summary.json"
            } else {
                "summary.json"
            }
            $summaryPath = Join-Path $Output $summaryName
            if (Test-Path -LiteralPath $summaryPath -PathType Leaf) {
                Get-Content -LiteralPath $summaryPath -Raw
            }
        }
    } else {
        & $AyonConsole @ayonArguments
        $exitCode = $LASTEXITCODE
    }
} finally {
    foreach ($item in $previousEnvironment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $item.Key,
            $item.Value,
            [EnvironmentVariableTarget]::Process
        )
    }
}

if ($exitCode -ne 0) {
    throw "Live Katana runner failed with exit code $exitCode."
}
