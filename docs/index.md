# AYON Katana

AYON Katana integrates Foundry Katana with AYON workfiles, loading, publishing,
Scene Inventory, Workfile Builder, Deadline, and the standard AYON menu.

Version **0.1.63** is the first stable release line.

## Supported hosts

- Katana 8.0v1 and 9.0v1.
- Windows is the primary validated production platform.
- Linux runtime and packaging are supported. Native Katana 8/9 execution on
  Linux has not yet been verified.
- macOS is not currently supported.

## Main features

- AYON Workfiles, context persistence, Save As, and version-up integration.
- Scene Inventory and managed loader updates that preserve artist-owned graph
  content.
- USD, Alembic, image, node graph, and render setup loading and publishing.
- Semantic USD publishing for look, camera, layout, and assembly products.
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
