# Live Katana tests — BETA/WIP

These tests run inside **real headless Katana** using the AYON Applications launch
environment. They exist to verify host/API behavior that unit-test mocks cannot
reliably represent.

This framework is currently **BETA/WIP and intended for local developer use**.
It is not a required pull-request CI gate.

## Requirements

- AYON Launcher/Console connected to the target AYON server;
- the Katana application variants configured in the AYON Applications addon;
- valid local Katana licenses;
- a real AYON project/folder/task context that is valid for those applications;
- renderer plugins only if renderer-dependent coverage is desired.

The runner removes installed AYON Katana addon paths from `PYTHONPATH` and
`KATANA_RESOURCES`, then injects this checkout so a staging addon cannot mask a
regression.

## Local PowerShell usage

Use the tracked PowerShell front-end. Set `AYON_CONSOLE` once for your machine. The wrapper uses AYON staging by
default; pass `-AyonVariant production` when intentionally testing the
production bundle:

```powershell
$env:AYON_CONSOLE = "C:\Program Files\Ynput\AYON 1.6.0\ayon_console.exe"
```

Then run a real AYON context:

```powershell
.\tests\live\katana\run-local.ps1 `
  -Project "MyProject" `
  -Folder "/sequences/sq01/sh010" `
  -Task "lighting" `
  -Suite native
```

Both supported applications are tested by default. Restrict a run when needed:

```powershell
.\tests\live\katana\run-local.ps1 `
  -Project "MyProject" `
  -Folder "/sequences/sq01/sh010" `
  -Task "lighting" `
  -Applications "katana/9.0v1" `
  -Suite integration
```

Use PowerShell rather than Git Bash/MSYS. MSYS can rewrite AYON folder paths such
as `/sequences/...` into Windows filesystem paths before AYON sees them. The
runner validates this and fails early with a targeted error.

Available suites:

- `native`: direct Katana/Foundry API contracts; fastest and the best first run;
- `integration`: real AYON host, Creator/CreateContext, Pyblish, creator error
  boundaries, USD extraction, render validation when a renderer is available,
  plus Image/Alembic/USD/Katana loader transaction and rollback coverage;
- `existing`: read-only compatibility against a supplied workfile;
- `all`: run all three suites.

For the existing-workfile suite:

```powershell
.\tests\live\katana\run-local.ps1 `
  -Project "MyProject" `
  -Folder "/sequences/sq01/sh010" `
  -Task "lighting" `
  -Suite existing `
  -Workfile "G:\path\to\scene.katana"
```

Use a project/folder/task context matching the workfile. The suite hashes the
source before and after the run and fails if the file changes.

Results and Katana logs default to:

```text
.artifacts/live-katana/<katana-version>/<suite>/
```

Override that with `-Output`. The default per-process timeout is 240 seconds;
change it with `-TimeoutSeconds`.

## Reading results

Every Katana process writes a structured `result.json`. The runner writes a
combined local `summary.json` plus a path- and traceback-free
`public-summary.json` intended for public CI artifacts. A result has:

- `success`: whether all assertions for the available capabilities passed;
- `checks`: live behavior that was actually exercised;
- `coverage_gaps`: capabilities that could not be tested in that host launch;
- `observations`: concrete native values useful for comparing Katana versions;
- `error`: traceback when a real assertion or operation failed;
- `katana.log`: captured host output via the runner summary.

A coverage gap is not equivalent to a pass. For example, if Katana 8 has no
registered renderer plugins, the integration suite records the renderer tests as
unavailable instead of claiming they passed.

## BETA/WIP GitHub workflow

`.github/workflows/live-katana-beta.yml` is deliberately manual-only and targets
a self-hosted Windows runner. It has no `push` or `pull_request` trigger and is
not intended to be a required status check yet. Workflow failures remain visible
as failures; being manual and non-required is what keeps this beta job
non-blocking.

The public workflow exposes only `native` and `integration`. The `existing`
workfile suite is local-only because workfile paths and scene metadata can be
studio-sensitive. GitHub uploads only `public-summary.json`; raw AYON/Katana
logs, per-process results, tracebacks, observations, and local paths remain on
the self-hosted machine.

Local runs are authoritative during this beta phase. Promote the workflow to a
required CI gate only after the self-hosted runner, licensing, AYON credentials,
renderer availability, artifact retention and failure handling are stable.

## What belongs here

Add a live assertion when the question is about real Katana or Foundry behavior,
for example:

- method/property availability across Katana versions;
- native return shapes such as `cookLocation().getAttrs()`;
- node deletion or save/reload behavior;
- real node parameters, ports and renderer registry;
- Foundry USD/Sdf proxy types;
- native USD stage acquisition;
- real `KatanaFile` import/export;
- host lifecycle behavior involving Katana callbacks.

If the behavior is owned entirely by AYON Katana and can be expressed without a
real DCC, prefer the normal pytest suite instead.
