# Known limitations and feature gaps

AYON Katana 0.1.63 focuses on Katana-native production workflows and exposes
only features that map to supported Katana workflows.

## Platform and host coverage

- Windows is the primary production-tested platform.
- Linux runtime and packaging are supported, but native Katana 8/9 execution on
  Linux has not yet been verified.
- macOS is not supported.
- Katana versions other than 8.0v1 and 9.0v1 are not currently supported.

## Workfiles and context

- Workfiles use filesystem `.katana` paths; asset-ID workfiles are not
  supported.
- Cross-context Save As and version-up depend on AYON Core's workfile services.
- Graphical version-up and reopen behavior has less host validation than the
  core filesystem workfile operations.

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
- USD Look publishes authored USD resource paths as-is and does not collect or
  localize external textures.
- Semantic USD creators describe the intended product type but do not prove the
  exported stage contains only that semantic data.
- USD farm export is not implemented; local native USD export is the supported
  path.
- Viewport review-sequence capture is not implemented. ImageWrite review output
  and still workfile thumbnails are supported instead.

## Renderer and farm scope

- RenderMan 27.3 is supported for local beauty and depth rendering. 3Delight
  support remains provisional and should be verified against a valid studio
  license before production use.
- Arnold/KtoA is not part of the supported deployment matrix.
- Deadline support supplies Katana submission metadata and depends on the
  studio's AYON Deadline addon, Deadline repository, renderer, and host
  configuration.

## Deliberately out of scope

SOP/BGEO/APEX authoring, HUSD output processors, value clips, legacy shelf
tooling, and host-specific conversion utilities are not implemented because
Katana does not expose those workflows.
