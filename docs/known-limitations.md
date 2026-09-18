# Known limitations and feature gaps

AYON Katana focuses on Katana-native production workflows and exposes only
features that map to supported Katana workflows.

## Platform and host coverage

- Windows is the primary production platform.
- Rocky Linux 9 with Katana 9.0v1 is supported for validated headless AYON
  workflows; interactive Viewer/UI and renderer execution remain unverified.
- Katana 8.0v1 and 9.0v1 are the tested versions.
- macOS is not supported.

## Workfiles

- Workfiles use filesystem `.katana` paths; asset-ID workfiles are not
  supported.
- Cross-context Save As and version-up depend on AYON Core's workfile services.

## Loading

- Following types are supported:
  - `USD`, `Alembic`, `image`, `node graph`.
- FBX, VDB, Arnold ASS, renderer proxy formats, KLF Look Files, and
  LiveGroup source assets are not currently supported.
- for Katana 9.0v1, `UsdSubLayerAdd` node is buggy when it comes to showing animations in the viewport. 
  Try using `UsdIn`.
- AYON entity URIs require the optional AYON USD Resolver, which is disabled by
  default and hasn't been properly tested.

## Publishing

- Local rendering is synchronous and blocks Publisher until Katana batch exits.
- Render paths are validated but not repaired automatically.
- Node graph publishing is limited to one selected `Group` with an output.
- USD Look publishing collects supported local external resources into the
  published resource directory and remaps authored asset paths, including UDIM
  texture sets. Remote URIs, missing or ambiguously anchored resources, and
  transfer destination collisions are rejected.
- Semantic USD Camera publishing verifies that the exported stage contains at
  least one composed `Camera` prim. Layout and assembly publishing does not
  currently enforce a universal semantic stage-content check.
- USD farm export is not implemented; only local native USD export.
- Scene Review will capture the Katana Viewer to a PNG image
  sequence for AYON review processing. Linux interactive Viewer capture remains
  untested.

## Renderer and farm scope

- Only Renderman and 3Delight have been tested. I don't think Arnold needs its own testing mechanism.
- RenderMan and 3Delight were tested on Windows only with Katana 9.0v1.
- Rocky Linux testing didn't involve any external renderer plugin, so Linux renderer execution remains a coverage gap.
- Deadline support supplies Katana submission metadata and depends on the
  studio's AYON Deadline addon, Deadline repository, renderer, and host
  configuration. Automated acceptance validates the metadata path but does not
  submit a real farm job.
