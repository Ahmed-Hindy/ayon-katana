# AYON Katana AI-Code-Smell Audit and Fix Plan

## Purpose

This document records a second-pass audit of `ayon-katana` after pulling current `develop`, with a specific focus on code patterns that often appear in AI-generated implementations but are undesirable in a mature DCC integration: excessive duck typing, broad exception swallowing, redundant alias handling, duplicated wrappers, duplicated transactions, compatibility branches without evidence, and defensive access to objects whose APIs are already guaranteed by Katana, Pyblish, or AYON Core.

The goal is not to remove all defensive programming. The intended rule is:

> Prefer direct native Katana, Pyblish, and AYON calls when the producer/framework guarantees the object and API. Keep defensive capability checks only when the external API is genuinely optional, version-dependent, UI/headless-dependent, or otherwise demonstrated to vary.

This addon is still incubating, so permanent fallback support for obsolete internal contracts is not desirable unless there is a concrete migration requirement.

## Repository state at this audit

- Branch: `develop`
- HEAD after pull: `93b04b1`
- Tracking: `origin/develop`
- `develop` was verified aligned with `origin/develop` at audit start.
- Full test suite before new fixes: `393 passed`.
- Ruff and formatting checks passed before new fixes.

Pre-existing unrelated local changes must not be folded into this cleanup accidentally:

- `create_package.py`
- `tests/test_package_builder.py`
- `DEVELOPMENT_PLAN.md`

A prior deliberate but still uncommitted cleanup also exists:

- `client/ayon_katana/plugins/publish/validate_workfile_paths.py`
  - changed `getattr(instance.context, "data", {})` to direct `instance.context.data`.

## Architectural intent

The desired direction is:

- prefer direct native Katana calls for native Katana nodes and parameters;
- prefer direct Pyblish/AYON framework access when the framework contract guarantees an attribute;
- do not catch arbitrary implementation errors merely to turn them into empty values or artist-facing validation failures;
- use `PublishValidationError` for actual scene/content/value validation problems;
- allow programming errors and broken addon-owned producer contracts to surface as implementation errors;
- keep Katana-specific compatibility only when required by verified Katana 8/9 behavior;
- avoid object-or-string dual contracts when the producer now owns and guarantees one canonical representation;
- remove duplicated post-create persistence and other work that the base creator already owns;
- keep transaction rollback where it protects the scene, but avoid duplicating the same rollback mechanics indefinitely;
- keep the public addon implementation simpler than the historical development probes and one-off compatibility experiments.

## Findings and current verdicts

### 1. `api/dependencies.py` over-defends guaranteed Katana node/parameter APIs

Current patterns include:

```python
get_type = getattr(node, "getType", None)
checker = getattr(parameter, "isExpression", None)
getter = getattr(parameter, "getExpression", None)
getter = getattr(parameter, "getValue", None)
```

and broad exception handling that converts native API failures into `False` or `""`.

This was verified against the bundled developer documentation for both Katana 8.0v1 and 9.0v1. `NodegraphAPI.Parameter.isExpression()`, `getExpression()`, and `getValue()` are documented native APIs. Nodes returned by Katana graph traversal are Katana nodes and expose `getType()`.

Verdict: **change now**.

Use direct calls. An unexpected failure should not silently turn a broken expression or parameter into an empty path.

### 2. Canonical `instance_node` still accepts object-or-string compatibility

`api/plugin.py` now guarantees persisted creator metadata contains:

```python
created_instance["instance_node"] = instance_node.getName()
```

Nevertheless, helper code in:

- `plugins/publish/actions.py`
- `plugins/publish/validate_render_product_paths_unique.py`

still checks whether `instance_node` is already a node object and otherwise coerces it through `str()`.

No current producer stores native node objects in `instance_node`.

Verdict: **change now**.

Treat `instance_node` as the canonical persisted node-name string and resolve it with `compat.get_node(instance.data["instance_node"])`. Missing persisted keys should surface according to the plugin/framework contract rather than being hidden as generic `None`.

### 3. Workfile-builder creator access uses unnecessary `getattr`

`plugins/workfile_build/create_placeholder.py` currently does:

```python
creator = self.builder.get_creators_by_name().get(creator_name)
product_type = getattr(creator, "product_base_type", creator_name)
```

Houdini `origin/develop` directly accesses `creator.product_base_type`, and AYON Core's creator API defines the attribute.

Verdict: **change now**.

Handle a missing creator explicitly, and otherwise access the creator API directly.

### 4. Duplicate `_get_parameter()` helpers in `api/image.py` and `api/usd.py`

Both helpers call `node.getParameter(name)`, then use a defensive `getattr(node, "getName", lambda: "<unknown>")()` only for diagnostics.

The callers pass native Katana nodes, so `getName()` is guaranteed. The two helpers are nearly identical.

Verdict: **change now, minimally**.

At minimum use direct `node.getName()`. Prefer one small shared required-parameter helper only if it meaningfully reduces duplication without introducing abstraction overhead.

### 5. `render._parameter_value()` swallows arbitrary native failures

Current behavior:

```python
parameter = node.getParameter(parameter_path)
if parameter is None:
    return default
try:
    return parameter.getValue(_TIME)
except Exception:
    return default
```

This treats "parameter is absent" and "existing native parameter failed unexpectedly" as the same condition.

`api/lib.py` already has a narrower equivalent that only catches `TypeError`.

Verdict: **change now**.

Use direct native `getValue()` for an existing parameter. Keep a default only for an absent parameter (and only retain a narrow exception if a verified Katana API condition requires it).

### 6. Image/USD validators blanket-wrap arbitrary implementation errors as artist validation

Both validators do roughly:

```python
try:
    settings = read_*_settings(node)
except Exception as exc:
    raise PublishValidationError(...)
```

They already explicitly validate missing nodes, node types, source connectivity, supported settings, frame ranges, and so on. Therefore an unexpected `AttributeError`, `TypeError`, or API regression inside the addon-owned settings reader is not necessarily an artist scene problem.

Houdini validators generally do not blanket-wrap native access this way.

Verdict: **change now**.

Call owned settings readers directly. Let programming/API failures propagate. Preserve explicit `PublishValidationError` for actual invalid scene values.

### 7. Base/specialized creator catch-all exception presentation masked bugs

`KatanaCreator.create()`, `CreateImage`, `CreateUsdLayer`, and `CreateRender` caught every exception to perform rollback and then converted unexpected failures to `CreatorError`.

Rollback is required because failed creation must not leave native nodes or ghost Publisher instances. Exception translation is a separate concern: unexpected native/API/programming failures should retain their original type and traceback, while expected user/setup validation should raise `CreatorError` explicitly at the point where it is detected.

Verdict: **changed now**.

The creator transactions still catch broadly only to clean up objects owned by the active creation attempt, then use bare `raise` to preserve the original exception. Existing selection, renderer-configuration, duplicate-product, and unsupported-target checks continue to raise `CreatorError` explicitly. Tests cover base imprint failure plus ImageWrite, USD, and Render post-create failures and verify both rollback and preservation of the original error message/type.

### 8. Redundant second imprints in Image and USD creators

The base `KatanaCreator.create()` now:

- creates the native node;
- creates the `CreatedInstance`;
- sets canonical `instance_node` to the native resolved name;
- adds it to creator context;
- imprints it.

`CreateImage` and `CreateUsdLayer` then set the same `instance_node` value and imprint again even though no new persistent AYON instance metadata was added.

Verdict: **changed now**.

The duplicate Image/USD `instance_node` assignment and imprint were removed. Native node parameter configuration persists on the node itself. `CreateRender` still performs a later imprint because it owns additional render-specific metadata (`render_node` and `render_settings_node`).

### 9. Loader transactions duplicated rollback and relabeled native errors

Alembic, Image, and USD loaders independently repeat creation/update transaction mechanics. They previously rolled back correctly but then wrapped every failure in a generic `RuntimeError`, losing the original exception type. `KatanaImportLoader.update()` did the same, while its initial `load()` path was not transactional at all.

The safety behavior is desirable and stronger than some mature Houdini loader implementations, so rollback was preserved. The generic exception relabeling was not.

Verdict: **behavior changed now; structural deduplication deferred**.

Alembic/Image/USD load and update paths now catch broadly only to restore/delete state and then bare-raise the original error. `KatanaImportLoader.update()` follows the same policy. Initial Katana graph loading now validates the representation path before graph mutation, rolls back the newly created container when import/setup fails, and preserves the original exception. Tests verify rollback plus exception-type preservation.

The repeated transaction code remains a maintenance smell. If it is later consolidated, prefer a small Katana loader/container primitive rather than a large abstraction.

### 10. Private cross-module coupling

Examples:

```python
colorspace._get_ocio_config_path()
self._host._has_been_setup
```

The first is a private colorspace helper used across modules. The second is private host state read by the separate lifecycle controller.

Verdict: **changed now**.

The colorspace helper is now public `get_ocio_config_path()`, and lifecycle uses the read-only `KatanaHost.is_installed` property instead of reaching into `_has_been_setup`.

### 11. `hasattr(current_instance, "set_mandatory")` is justified and should stay

This pattern appears in `ayon-houdini origin/develop` as well. It represents compatibility with AYON Core versions/structures and is not a Katana-only generated-code smell.

Verdict: **keep**.

### 12. `isBypassed` capability detection is justified and should stay

Katana render code probes `node.isBypassed`, and Houdini uses equivalent `hasattr(node, "isBypassed")` behavior. This is a native-host capability difference rather than addon-owned contract uncertainty.

Verdict: **keep**.

### 13. UI/callback compatibility probing is justified, but node compatibility was narrowed

`callbacks.py` and `thumbnail.py` deal with optional callback enum members, headless UI APIs, Viewer tab APIs, and Qt focus/visibility behavior; those capability checks remain justified.

`compat.py` was verified natively rather than kept defensive wholesale. Katana 9 `Node2D` leaf nodes genuinely do not expose `getChildren()`, so `iter_nodes()` retains that capability guard. In contrast, supported native nodes expose `getParent()` and `getOutputPorts()` in both Katana 8 and 9, so those helpers now call the native APIs directly and their tests reject arbitrary non-node objects.

Verdict: **keep only the verified `getChildren()` compatibility path; direct-call the stable node APIs**.

### 14. USD resource/spec introspection needed a mixed contract, not blanket defensiveness

The initial audit treated most `usd_resources.py` / `usd_publish.py` introspection as external heterogeneity. A deeper pass separated genuinely polymorphic/list-op compatibility from stable `pxr.Sdf` APIs.

Stable native APIs now use direct access, including:

- `Sdf.Layer.subLayerPaths`, `realPath`, `resolvedPath`, `identifier`, `GetLayerStack()`, `ListTimeSamplesForPath()`, and `QueryTimeSample()`;
- `Sdf.Path.pathString`, `GetPrimPath()`, and `AppendProperty()`;
- `Sdf.AssetPath.path` and `resolvedPath`;
- `Sdf.AttributeSpec.typeName`, `default`, `path`, `layer`, `HasInfo()`, and `GetInfo()`;
- composition item `assetPath`;
- `Sdf.Layer.GetFileFormat().formatId`.

The cross-version list-proxy helper around `GetAppliedItems()` remains because that compatibility path is deliberate. Asset-value flattening also remains polymorphic because USD attributes may hold scalar or array asset values.

Broad exception swallowing around `Sdf.ComputeAssetPathRelativeToLayer()` and `UsdStage.GetLayerStack()` was removed so native/programming failures do not silently become unresolved or empty dependencies.

Verdict: **changed now, selectively**.

### 15. `_layerDefineNode` rehydration is an intentional Katana workaround

The private attribute assignment in `api/usd.py` was verified previously against native Katana 8 and 9 behavior. Katana serializes the `UsdLayerExport` graph but does not restore this transient Python reference while native `write()` uses it.

Verdict: **keep**.

### 16. AYON task lookup errors were silently downgraded during context timing

`api/context.py` caught every exception from active-task lookup in both `apply_current_frame_range()` and `apply_context_settings()`, logged it, and continued as though timing were simply unavailable. Houdini's equivalent context/frame reset resolves the active task directly.

The Katana helpers now call the AYON task lookup directly. A legitimate `None` task remains a normal no-active-task state, while server/Core/programming failures propagate.

Verdict: **changed now**.

### 17. Renderer registry failures were silently converted to no renderers

`api/render.py` previously wrapped documented `RenderingAPI.RenderPlugins.GetRendererPluginNames()` in `except Exception: return []`. The API is documented in both bundled Katana 8 and 9 developer guides and was exercised successfully in both native runtimes.

Renderer discovery now calls it directly. A real registry failure no longer masquerades as an installation with zero renderers.

Verdict: **changed now**.

### 18. Native USD stage inspection over-translated host failures

`get_composed_usd_stage()` previously wrapped `getName()`, `getType()`, node-flavor inspection, `NodesUsdAPI.GetStage()`, and `stage_handle.getUsdStage()` in defensive exception translation. Its callers already provide native Katana nodes, and the native APIs are part of the supported USD integration contract.

Verdict: **changed now**.

The helper now directly calls the native node and stage APIs. It still raises explicit `ValueError` for a missing/non-native source and explicit `RuntimeError` when Katana legitimately returns no stage handle or no composed stage. Unexpected host failures retain their original exception type. Unit tests verify propagation.

The ignored native smoke initially exposed an important test assumption: `UsdIn` is a Geolib node and is **not** registered with the `nativeusd` flavor. The smoke was corrected to use real `UsdLayerWrite`, which is registered `nativeusd` in both Katana 8.0v1 and 9.0v1. `get_composed_usd_stage()` passed with that real node in both hosts.

### 19. Render camera cooking and output positioning hid native failures

`ValidateRenderCamera` caught every exception from native scenegraph cooking and converted it to `PublishValidationError`. `get_output_nodes()` similarly caught every `NodegraphAPI.GetNodePosition()` failure and silently assigned a zero X position.

Verdict: **changed now**.

Camera path absence/wrong location type remain explicit artist-facing validation states, but an unexpected native cook failure now propagates. Render output sorting directly calls `GetNodePosition()`. The latter API was exercised successfully in both native Katana 8 and 9 before the fallback was removed. Regression tests verify that native cook/position failures retain their original exception types.

### 20. USD-look validators caught more than their declared scene-failure contract

The look assignment, disallowed-content, and material-definition validators previously used `except Exception`, converting arbitrary implementation errors into scene validation failures.

Verdict: **changed now, narrowly**.

These validators now translate only `ValueError` and `RuntimeError`, which are the declared scene/stage/layer inspection failures produced by their helpers. Unexpected errors such as `AttributeError` propagate unchanged. Parameterized tests verify both sides of this boundary: known scene inspection errors remain `PublishValidationError`, while programming errors are not relabeled.

### 21. Render creator update repeated base validation and swallowed owned-graph failures

`CreateRender.update_instances()` previously rechecked `instance_node.getName()` after the base creator had already validated the live node and refreshed canonical identity, then swallowed all failures from `get_render_node()` and `get_settings_node()`.

Verdict: **changed now**.

The redundant `getName()`/exception branch was removed. The subclass now directly resolves its addon-owned Render and RenderSettings children, fails explicitly if either owned node is absent, refreshes their persisted names, and imprints the resulting render metadata. Tests model the real base creator identity behavior and verify that an owned render lookup failure propagates.

### 22. Docstring/comment density is high and often trivial

The addon contains hundreds of docstrings, including many private helpers where the docstring merely restates the function name.

Verdict: **soft cleanup only**.

Do not churn the repository solely to remove docstrings. When touching code, keep documentation that explains contracts, host limitations, or non-obvious behavior; remove trivial repetition opportunistically.

### 23. Remaining `.get()` calls are not equivalent to the removed duck typing

A follow-up scan reviewed `.get()` access on publish/create data after the direct-call cleanup. The remaining calls mostly fall into different contracts from the removed `getattr`/catch-all patterns:

- persisted artist/scene metadata where absence should become a normal validation mismatch rather than a programming exception;
- optional publish metadata such as review/farm/family flags and representation lists;
- collector dependencies where `.get()` is immediately followed by an explicit domain error explaining which prior node/data was not collected;
- server/entity data where AYON legitimately permits an absent entity or attribute.

This matches the distinction already present in Houdini. For example, Houdini often directly indexes creator-owned collector contracts such as `instance.data["instance_node"]`, but also deliberately uses `.get()` in validators and host-specific collectors where missing persisted metadata is a supported invalid state. `ValidateInstanceInContextKatana` intentionally retains `.get()` for persisted `folderPath` and `task`, matching Houdini's validator behavior.

Verdict: **do not mechanically replace remaining `.get()` calls**.

Direct indexing should be introduced only when a specific producer/framework contract makes absence a programming error. A missing persisted scene value that the validator is supposed to diagnose should remain validation data, not be converted to an incidental `KeyError`.

### 24. Remaining broad catches were reviewed by purpose

After the cleanup, remaining `except Exception` blocks are concentrated in boundaries where catching broadly is intentional:

- transaction cleanup that immediately bare-raises the original failure;
- cleanup of files/nodes after a failed operation;
- stale/deleted Katana C++ object detection during creator collection/removal;
- optional/headless UI probing and thumbnail capture;
- startup/lifecycle/menu resilience where failure of an auxiliary UX feature must not prevent Katana from running;
- per-node resolver-cache flushing, where one broken `UsdIn` must not prevent other stages from being flushed;
- extractor/finalizer plugin boundaries that convert an operation failure to AYON's publish error type with domain context.

Verdict: **keep unless a specific boundary is later shown to hide a required failure**.

The key policy is no longer "avoid broad catches" in isolation. It is: do not use a broad catch to silently invent a normal value, an alternate object shape, or an artist error for an unexpected programming/native API failure.

## Implementation scope

The cleanup stayed limited to high-confidence contract simplification and transaction correctness:

1. direct native Katana node/parameter calls in `api/dependencies.py`;
2. canonical string-only `instance_node` resolution in publish helpers;
3. direct Creator API access in workfile-builder placeholder naming;
4. direct native node-name access in required-parameter diagnostics;
5. stop swallowing arbitrary failures in render parameter/registry/graph-position access;
6. stop blanket-wrapping owned Image/USD settings-reader and camera-cook failures;
7. remove redundant Image/USD second imprints;
8. preserve direct Pyblish `instance.context.data` and `instance.id` contracts;
9. expose deliberate public OCIO and host-installation interfaces instead of cross-module private access;
10. let AYON context lookup failures propagate while preserving legitimate `None` states;
11. use direct stable Sdf layer/path/spec/asset APIs while retaining only verified polymorphic/list-proxy compatibility;
12. preserve creator rollback without converting arbitrary failures to `CreatorError`;
13. use direct native USD stage inspection and preserve unexpected host exception types;
14. preserve loader rollback while retaining original exception types, and make initial Katana graph loading transactional;
15. narrow USD-look validation translation to declared scene/stage errors and make render instance updates trust the base creator/native owned graph contracts.

Each group received focused tests, followed by complete pytest, Ruff, formatting, and `git diff --check` gates. Runtime-sensitive native calls were exercised in both Katana 8.0v1 and 9.0v1.

## Non-goals for this pass

Do not yet:

- introduce a larger creator transaction abstraction beyond the current tested rollback blocks;
- redesign all loader transactions;
- remove validated Katana 8/9 compatibility logic;
- alter unrelated package/release changes;
- mechanically replace every `.get()` or every `getattr()`;
- change persisted user-data semantics without a concrete producer/consumer contract reason;
- commit or push without explicit user request.

## Implementation progress

The direct-contract cleanup has now been applied locally and remains uncommitted.

Completed:

- `api/dependencies.py`
  - direct `node.getType()`, `node.getName()`, `parameter.isExpression()`, `parameter.getExpression()`, and `parameter.getValue()` calls;
  - removed capability probing and broad exception-to-empty-value fallbacks for those guaranteed Katana APIs.
- `plugins/publish/validate_workfile_paths.py`
  - direct `instance.context.data` retained from the earlier cleanup;
  - direct `parameter.isExpression()` in repair logic;
  - direct `Utils.UndoStack` access, verified in the bundled Katana 8/9 documentation.
- `plugins/publish/actions.py`
  - `instance_node` is treated as a persisted node-name string rather than a node-object-or-string union;
  - native node identities use direct `getName()` calls.
- `api/compat.py`
  - direct `getParent()` and `getOutputPorts()` for native Katana nodes;
  - retained the `getChildren()` capability guard because a real Katana 9 `Node2D` leaf was verified not to expose that method.
- `plugins/publish/validate_render_product_paths_unique.py`
  - same canonical string-only `instance_node` contract;
  - direct native `getName()` identity;
  - direct Pyblish `instance.id` label, matching the documented `AbstractEntity` contract.
- `plugins/workfile_build/create_placeholder.py`
  - direct AYON Creator API access through `creator.product_base_type`;
  - missing configured creators now fail explicitly instead of silently falling back to the creator name.
- `api/image.py` and `api/usd.py`
  - required-parameter diagnostics use direct native `node.getName()`.
- `api/render.py`
  - an existing Katana parameter now uses direct `getValue()`; only a genuinely missing parameter produces the caller-supplied default;
  - renderer discovery now calls documented `RenderingAPI.RenderPlugins.GetRendererPluginNames()` directly instead of converting registry failures into an empty renderer list;
  - render-output ordering directly calls `NodegraphAPI.GetNodePosition()` instead of silently substituting a zero graph position on failure.
- native USD stage inspection
  - `get_composed_usd_stage()` directly uses the native node, flavor, `NodesUsdAPI.GetStage()`, and stage-handle APIs;
  - explicit missing/non-native/no-stage states remain domain errors, while unexpected host exceptions propagate unchanged.
- `plugins/publish/validate_image.py` and `validate_usd_layer.py`
  - removed blanket `except Exception -> PublishValidationError` around addon-owned native settings readers;
  - unexpected native/programming failures now propagate while explicit scene validation remains artist-facing.
- render and USD-look validation boundaries
  - render camera cooking no longer converts arbitrary native cook failures into camera validation;
  - USD-look validators translate only declared `ValueError`/`RuntimeError` scene inspection failures, not arbitrary implementation exceptions.
- `plugins/create/create_image.py` and `create_usd_layer.py`
  - removed redundant second `instance_node` assignments and imprints already owned by `KatanaCreator.create()`.
- Image, USD, and Render creator context defaults
  - removed broad catches around `CreateContext.get_current_folder_entity()` / `get_current_task_entity()`;
  - a legitimate `None` entity still uses fallback frame/handle defaults, while Core/server/programming errors propagate.
- colorspace API boundary
  - `_get_ocio_config_path()` renamed to public `get_ocio_config_path()` because `api/lib.py` depends on it.
- lifecycle/host boundary
  - `KatanaHost.is_installed` added as a public read-only property;
  - `LifecycleController` no longer reaches into `_has_been_setup` directly.
- creator transactions and render updates
  - base, ImageWrite, USD, and Render creation still roll back newly owned nodes/instances on failure;
  - catch-all conversion to `CreatorError` was removed, so unexpected native/programming failures retain their original type and traceback;
  - known ImageWrite/USD configuration `ValueError`s are translated narrowly to `CreatorError`, preserving AYON's expected creator-failure semantics without masking unrelated native/programming failures;
  - render product-name updates preflight the owned Render/RenderSettings children before the base creator can rename or imprint the outer instance, preventing partial scene mutation when an owned graph is already damaged.
- loader transactions
  - Alembic, Image, USD, and Katana graph update rollback now preserves original exception types;
  - initial Katana graph loading now validates its path before graph mutation and deletes its newly created container on import/setup failure.
- context timing
  - AYON task lookup remains a lifecycle/service boundary: lookup failures are logged and leave Katana timing unchanged instead of escaping new-scene/task-change callbacks;
  - once a task entity is resolved, Katana frame-range operations continue to use direct native calls;
  - a legitimate missing task (`None`) remains a normal no-timing state.

Tests were updated where isolated fake base creators or fake CreateContext objects failed to model the real framework contract. Regression coverage distinguishes expected AYON/domain failures from unexpected native/programming failures instead of treating every exception identically.

Validation after the post-review corrections reached:

- focused lifecycle/render/Image/USD suite: `101 passed`;
- full suite: `416 passed`;
- Ruff lint: passed;
- Ruff format check: passed (`152 files already formatted`);
- `git diff --check`: passed.

A dedicated ignored runtime smoke was added under `.local-backup/direct-native-call-smoke/` and run against both supported native hosts. It creates real Katana `ImageWrite`, `ImageRead`, `UsdLayerExport`, and native-USD `UsdLayerWrite` nodes and exercises the new direct parameter/node calls, graph-position access, workfile-reference collection, renderer registry, and composed native USD stage lookup.

Native results:

- Katana 9.0v1: `DIRECT_NATIVE_CALL_SMOKE_PASSED`;
- Katana 8.0v1: `DIRECT_NATIVE_CALL_SMOKE_PASSED`.

Both runs used the current checkout. The smoke exercises documented `RenderingAPI.RenderPlugins.GetRendererPluginNames()` and `NodegraphAPI.GetNodePosition()` calls, the actual `nativeusd` flavor registry, `NodesUsdAPI.GetStage()`/`getUsdStage()` through a real `UsdLayerWrite`, and Foundry's bundled `fnpxr` Sdf/Usd API shape used by the standard `pxr` contracts in full USD environments: layer/path/spec/asset access, layer-stack access, time-sample listing, and file-format lookup. The expected minimal-environment warning about no valid renderer plug-ins did not affect these API checks.

## Post-implementation live regression review

The branch was compared side-by-side with clean `origin/develop` using real AYON-launched headless Katana processes, not mock tests as runtime evidence. The checkout client/resources were injected ahead of the installed staging Katana addon so the tested code was the branch itself.

The comparison found and corrected four overreaches from the first direct-contract pass:

- Katana 9 can return a cooked scenegraph location whose `getAttrs()` result is `None` for a missing path. The helper now treats that documented native result as unresolved, while other unexpected native exceptions still propagate. `ValidateRenderCamera` again reports a normal `PublishValidationError` for a missing camera path.
- A damaged render instance previously failed `CreateContext.save_changes()` only after the base update had renamed/imprinted the outer instance. Owned Render/RenderSettings children are now checked before mutation; the live damaged-graph probe raises `CreatorsSaveFailed` with the node name and persisted product metadata unchanged.
- Invalid ImageWrite/USD creator settings again surface as `CreatorError`, but only the configuration helpers' explicit `ValueError` contract is translated. Injected native `RuntimeError`s remain transparent after rollback.
- AYON task lookup failures during timing/context lifecycle handling are logged and contained. This is an AYON/server boundary, not a Katana native API capability check, so direct-native-call cleanup does not justify making lifecycle callbacks brittle.

Live headless matrix after the corrections:

- Katana 9.0v1: real host startup/context, workfile path repair with native `Utils.UndoStack`, Image/USD/Nodegraph/Render creation, collectors/validators, save/reload recollection, native USD extraction/stage access, Sdf resource rewrite, and Image/Alembic/USD/Katana loader load/failure-rollback/update/remove all passed.
- Katana 8.0v1: the same applicable matrix passed. This launch has no registered pixel renderer, so Render-creator/camera checks remain unavailable there.
- Existing `testpr_sh01_storyboard_v036.katana` was loaded read-only on both Katana 9 and 8. Embedded context, creator recollection, native render graph collection, colorspace, and dependency scanning passed; the file digest remained unchanged. On Katana 8 only renderer-registration validation was skipped because PRMan is not registered in that process.
- Side-by-side baseline testing confirmed the new `KatanaImportLoader` initial-load transaction is an improvement: `origin/develop` leaves a failed container behind for an invalid imported graph, while this branch removes it completely.

Still intentionally deferred:

- consolidating repeated Alembic/Image/USD loader transactions;
- deciding whether the remaining creator rollback duplication warrants a small shared transaction helper; behavior is now correct and tested, so this is maintenance-only;
- opportunistic reduction of trivial docstrings;
- only genuinely polymorphic USD value/list-proxy compatibility remains defensive; stable Sdf layer/path/spec/asset APIs now use direct native calls.
