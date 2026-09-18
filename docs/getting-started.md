# Getting started

AYON Katana is distributed as an AYON Server addon and launched through the
AYON Launcher.

## Requirements

The addon currently declares these compatibility requirements:

- AYON Server 1.1.2 or newer.
- AYON Core 1.9.9 or newer.
- AYON Deadline 0.7.0 or newer when Deadline integration is used.

Katana 8.0v1 and 9.0v1 are the tested host versions. Windows is the primary
production platform and Rocky Linux 9 remains in beta. See
[Known limitations](known-limitations.md) for the current platform, renderer,
loading, and publishing scope.

## Build the addon package

From the repository root, build the uploadable addon ZIP with:

```bash
uv run python create_package.py
```

The package is written to:

```text
package/katana-<version>.zip
```

Use `--extract` when you also want the package expanded into AYON's versioned
addon directory layout for local inspection.

## Install in AYON Server

Upload `katana-<version>.zip` to AYON Server, then include the Katana addon in
the bundle used by your artists. The same bundle must contain a compatible AYON
Core version. Include the Deadline addon when farm submission metadata is part
of the studio workflow.

Project settings can override the addon version, so verify the project is
resolving the intended Katana version before testing a deployment.

## Launch Katana

Launch Katana from AYON Launcher with a project, folder, task, and compatible
Katana application selected.

A basic installation check should confirm that:

- the AYON menu is available in Katana;
- Workfiles can open and save the current scene;
- Loader and Scene Inventory are available;
- Publisher can discover Katana publish instances; and
- Workfile Builder is available when configured for the project.

For renderer support, USD behavior, Scene Review, and Deadline scope, continue
with [Known limitations](known-limitations.md).
