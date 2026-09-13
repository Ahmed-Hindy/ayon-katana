# Known limitations and feature gaps

AYON Katana 0.1.64 focuses on Katana-native production workflows and exposes
only features that map to supported Katana workflows.

## Platform and host coverage

- Windows remains the primary artist-validated production platform.
- Rocky Linux 9 with Katana 9.0v1 is verified for headless AYON launch and the
  core workfile, creator, loader, publishing, Scene Inventory, Workfile Builder,
  USD, and Deadline-metadata workflows.
- Interactive Katana menu/UI behavior, Viewer capture, and external-renderer
  execution have not yet been artist-accepted on Linux.
- Katana 8.0v1 has not yet been verified on Linux.
- macOS is not supported.
- Katana versions other than 8.0v1 and 9.0v1 are not currently supported.

## Workfiles and context

- Workfiles use filesystem `.katana` paths; asset-ID workfiles are not
  supported.
- Cross-context Save As and version-up depend on AYON Core's workfile services.
- Native save, new, open, reopen, and creator metadata persistence are covered by
  live acceptance tests. Interactive Workfiles UI and cross-context UX still
  require artist acceptance.

## Loading

- USD, Alembic, image, node graph, and supported semantic USD workflows are
  covered.
- FBX, HDA, BGEO, VDB, Arnold ASS, renderer proxy formats, KLF Look Files, and
  LiveGroup source assets are not exposed without a proven Katana-native
  consumer.
- The native `UsdSubLayerAdd` path can show stale animated camera locators in
  Katana 9.0v1; `UsdIn` is the supported animated-camera playback route.
- AYON entity URIs require the optional AYON USD Resolver and are disabled by
  default.

## Publishing

- Local rendering is synchronous and blocks Publisher until Katana batch exits.
- Render paths are validated but not repaired automatically.
- Node graph publishing is limited to one selected `Group` with an output.
- USD Look publishing collects supported local external resources into the
  published resource directory and remaps authored asset paths, including UDIM
  texture sets. Remote URIs, missing or ambiguously anchored resources, and
  transfer destination collisions are rejected rather than silently rewritten.
- Semantic USD creators describe the intended product type but do not yet prove
  the exported stage contains the promised semantic content.
- USD farm export is not implemented; local native USD export is the supported
  path.
- Viewport review-sequence capture is not implemented. ImageWrite review output
  and still workfile thumbnails are supported instead.

## Renderer and farm scope

- RenderMan local rendering is live-tested on Windows with Katana 9.0v1,
  including a real frame through the production local-render extractor.
- The validated Rocky Linux Katana image intentionally contains no external
  renderer plugin, so Linux renderer execution remains a coverage gap.
- 3Delight support remains provisional and should be verified against a valid
  studio renderer/license setup before production use.
- Arnold/KtoA is not part of the supported deployment matrix.
- Deadline support supplies Katana submission metadata and depends on the
  studio's AYON Deadline addon, Deadline repository, renderer, and host
  configuration. Automated acceptance validates the metadata path but does not
  submit a real farm job.

## Deliberately out of scope

SOP/BGEO/APEX authoring, HUSD output processors, value clips, legacy shelf
tooling, and host-specific conversion utilities are not implemented because
Katana does not expose those workflows.
