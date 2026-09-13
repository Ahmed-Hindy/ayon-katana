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
- `acceptance`: disposable high-level workflow coverage for Pyblish discovery,
  workfile Save As/new/open/reload persistence, nodegraph publish/load-back,
  Scene Inventory actions, Workfile Builder placeholder behavior and configured
  trigger evaluation, plus Deadline command metadata without submitting a job;
- `render`: save a disposable workfile copy and render one real frame through
  `ExtractLocalRender`; reports a coverage gap when the launch scene has no
  usable render instance or renderer;
- `automated`: run `native`, `integration`, `acceptance`, and `render`; this is
  the broad self-hosted headless acceptance mode;
- `existing`: read-only compatibility against a supplied workfile;
- `all`: run every suite, including `existing` (therefore requires `-Workfile`).

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

The public workflow exposes `native`, `integration`, `acceptance`, `render`, and
the combined `automated` mode. It can also run the pre-provisioned Rocky Linux
Katana host probe on the same Windows runner through Docker. The `existing`
workfile suite is local-only because workfile paths and scene metadata can be
studio-sensitive. GitHub uploads only `public-summary.json`; raw AYON/Katana
logs, per-process results, tracebacks, observations, and local paths remain on
the self-hosted machine.

Local runs are authoritative during this beta phase. Promote the workflow to a
required CI gate only after the self-hosted runner, licensing, AYON credentials,
renderer availability, artifact retention and failure handling are stable.

## Rocky Linux container host probe

`linux_host_probe.py` is intentionally AYON-independent. It verifies that a
containerized Katana installation can acquire a Foundry license and execute core
Katana/Foundry USD APIs before Linux AYON integration is attempted.

The validated local image uses Rocky Linux 9 and Katana 9.0v1. The Foundry
installer and any license material must remain outside Git. With a reachable
floating license server, run from PowerShell to avoid MSYS rewriting Linux paths:

```powershell
docker run --rm `
  -e 'foundry_LICENSE=4101@host.docker.internal' `
  -v "${PWD}:/workspace:ro" `
  ayon-katana/katana9-rocky:9.0v1 `
  /opt/Katana9.0v1/bin/katanaBin `
  --script /workspace/tests/live/katana/linux_host_probe.py
```

A successful run prints `AYON_KATANA_LINUX_HOST_PROBE=` followed by structured
JSON. This host probe is not equivalent to full Linux AYON acceptance; that still
requires a Linux AYON launch environment and real project context.

### Rebuilding the local Rocky image

The proprietary Foundry installer stays in the Docker volume
`katana9-installer-cache`; it is never copied into Git. The tracked builder checks
the known Katana 9.0v1 SHA-256, installs Katana into Rocky Linux 9 without bundled
3Delight, installs only the runtime libraries proven necessary by the live probe,
checks `katanaBin` with `ldd`, and commits the resulting local image:

```powershell
.\tests\live\katana\build-linux-image.ps1
```

The resulting default image tag is `ayon-katana/katana9-rocky:9.0v1`. Licensing
is deliberately not part of the image. Verify the final image against a floating
Foundry server with:

```powershell
.\tests\live\katana\run-linux-probe.ps1 `
  -LicenseServer "4101@host.docker.internal"
```

### Official Linux AYON acceptance

Full Linux acceptance uses AYON's normal server-driven distribution path rather
than a handcrafted Python environment. The active staging bundle must have a
Rocky-compatible Linux AYON installer and a Linux dependency package generated by
Ynput's `ayon-dependencies-tool`. The validated setup uses AYON 1.6.0 for Rocky 9
with Python 3.11.9 and a dependency package built from the active bundle's addon
requirements.

Build the local AYON+Katana image from the already verified AYON archive in the
Docker volume `ayon-launcher-1.6.0-rocky9-cache`:

```powershell
.\tests\live\katana\build-linux-ayon-image.ps1
```

The default output is `ayon-katana/katana9-rocky:ayon-1.6.0`. Neither AYON API
credentials, Foundry licensing data, nor Kitsu credentials are stored in the
image.

Run the full disposable Linux suite from an authenticated Windows AYON install:

```powershell
.\tests\live\katana\run-linux-ayon.ps1 `
  -Project "MyProject" `
  -Folder "/sequences/sq01/sh010" `
  -Task "lighting" `
  -Suite automated
```

The Windows launcher supplies its existing AYON authentication and reads the
existing Kitsu login from AYON's secure registry. Secrets are forwarded to Docker
only as inherited environment variables. A read-only live-test Keyring backend
exposes the Kitsu values through the standard `keyring` API without writing them
to the container filesystem. Real Linux artist workstations should continue to
use their normal OS Secret Service backend.

The Linux runner uses the server-distributed Core, Applications, addon clients,
and dependency package. The only host override is
`/opt/Katana9.0v1/bin/katanaBin`, allowing this checkout to be tested against the
pre-provisioned Katana installation. Results are written under
`.artifacts/live-katana-linux/`; public CI uploads only `public-summary.json`.

### Provisioning the AYON Linux bundle

Do not build an ad-hoc virtual environment for AYON. Use Ynput's official
`ayon-dependencies-tool`, whose `Dockerfile.rocky9` resolves the bundle on Rocky
Linux and creates the platform-specific dependency ZIP. The AYON server must
first contain the Linux installer matching the bundle's `installerVersion`.
For a production/staging server, use the normal AYON launcher upload tooling to
register that installer, then use the dependencies tool's Rocky 9 Docker mode to
generate and attach the Linux package.

When validating a new package, prefer the dependencies tool's `--skip-upload`
mode first. Inspect the generated metadata/checksum and only then upload and
assign it to the intended bundle. Preserve the existing Windows dependency
package assignment when adding the Linux package.

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
