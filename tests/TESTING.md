# Testing strategy

AYON Katana uses two deliberately different test layers.

## Unit and policy tests

The default `pytest` suite is fast, deterministic, and must run without Katana.
It should test behavior owned by this addon: path manipulation, metadata contracts,
creator and loader policy, error classification, rollback decisions, publish data
shape, and AYON-facing validation semantics.

Mocks and fakes must not become an implementation of Foundry APIs. In particular,
unit tests should not be treated as evidence for whether a Katana or Foundry USD
object exposes a method, what a native call returns, how a deleted C++ object
behaves, or what save/reload does to node identity. Those assumptions belong in
the live contract suite.

When a unit test needs a native-looking object, keep the fake strict and minimal:
only implement the members required by the addon-owned behavior under test. A new
production dependency on another native member should require either an explicit
fake change or, preferably, a live contract assertion.

Useful unit-test boundaries include:

- known invalid creator settings become `CreatorError`;
- unexpected native/programming exceptions are not mislabeled as artist errors;
- failed creator or loader operations restore addon-owned state;
- canonical instance metadata is persisted and consumed consistently;
- validation plugins produce the intended AYON/Pyblish domain error;
- pure USD/path/resource transformations produce deterministic results.

Avoid adding mock-only tests whose assertion is effectively "Katana behaves this
way". Add or extend a live contract instead.

## Live Katana tests — BETA/WIP

The tracked live suite is under `tests/live/katana/`. It launches real headless
Katana through the AYON Applications environment and injects the current checkout
before any installed AYON Katana addon. `pytest` explicitly excludes `tests/live`,
so adding future `test_*.py` live scripts cannot accidentally consume a Katana
license during the normal test job.

This suite is currently **BETA/WIP and local-first**. It is not a required pull
request gate. Use `tests/live/katana/run-local.ps1` from PowerShell; see
`tests/live/katana/README.md` for setup and commands.

The live suite has three scopes:

- `native`: Foundry/Katana API contracts only;
- `integration`: real AYON host, Creator/CreateContext, Pyblish and transactional
  addon behavior in Katana;
- `existing`: read-only compatibility against an explicitly supplied `.katana`
  workfile.

Live scripts emit structured JSON. Missing optional host capabilities such as an
unavailable renderer are reported as `coverage_gaps`, not silently counted as
coverage and not automatically treated as a failure of unrelated contracts.

## Merge policy while live CI is WIP

Required automated checks remain the normal pytest, lint, documentation and addon
package gates. Before merging host-sensitive refactors, run the relevant live
suite locally on each supported Katana version where practical and include the
result in review notes.

The manual GitHub Actions live workflow is intentionally marked BETA/WIP. It is a
future self-hosted-runner entry point, not a required status check. It exposes only
`native` and `integration`; existing-workfile compatibility remains local-only.
Workflow failures remain visible as failures, while the absence of automatic PR
triggers and required-check configuration keeps the beta workflow non-blocking.
Only a sanitized public summary is uploaded from a self-hosted run. A unit guard
asserts that these boundaries remain in place while this policy is in effect.
