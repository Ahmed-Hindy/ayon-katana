# AYON Katana

AYON Katana integrates Foundry Katana with AYON workfiles, loading, publishing,
Scene Inventory, Workfile Builder, Deadline, and the standard AYON menu.

Version **0.1.64** is the current stable release line.

## Supported hosts

- Katana 8.0v1 and 9.0v1.
- Windows is the primary artist-validated production platform.
- Rocky Linux 9 with Katana 9.0v1 is verified for headless AYON launch and the
  core workfile, creator, loader, publishing, Scene Inventory, Workfile Builder,
  USD, and Deadline-metadata workflows.
- Interactive Katana UI acceptance and external-renderer execution on Linux are
  still outstanding, and Katana 8.0v1 has not yet been verified on Linux.
- macOS is not currently supported.

## Main features

- AYON Workfiles, context persistence, Save As, and version-up integration.
- Scene Inventory and managed loader updates that preserve artist-owned graph
  content.
- USD, Alembic, image, node graph, and render setup loading and publishing.
- Semantic USD publishing for look, camera, layout, and assembly products.
- USD Look resource collection and remapping for supported local external assets,
  including UDIM texture sets.
- Local Katana batch rendering and Deadline submission metadata.
- AYON Workfile Builder placeholders and template-driven scene construction.
- Render and publish validation for paths, frame ranges, colorspace, resolution,
  camera, collisions, and instance context.

The integration uses Katana-native nodes and APIs throughout.

## Installation

Build the AYON addon package with:

```bash
uv run python create_package.py
```

Upload the generated `katana-<version>.zip` to AYON Server and add the Katana
addon to the target bundle together with a compatible AYON Core version.

## Feature gaps

See [Known limitations and feature gaps](known-limitations.md) for the current
scope and deliberately unsupported surfaces.
