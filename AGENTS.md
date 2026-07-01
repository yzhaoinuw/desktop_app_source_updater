# Desktop Source Updater Handoff

Read this file first in future Codex sessions for this repository.

## Purpose

This repository owns a reusable stdlib-only updater for Python desktop apps that have a stable launcher, such as `run_desktop_app.py`, and import the real app code from an adjacent source folder such as `src/`, `app_src/`, `fp_analysis_app/`, or similar.

The updater is for code-only updates delivered as custom GitHub Release zip assets. It is not an installer, dependency resolver, or full packaged-app replacement mechanism.

## Runtime Contract

The runtime API lives in `src/desktop_source_updater/core.py` and is exported from `src/desktop_source_updater/__init__.py`.

The intended launcher pattern is:

1. Compute the launcher/app root.
2. Put that root on `sys.path` if the app uses an adjacent source folder.
3. Call `run_startup_update(UpdateConfig(...))` before importing the app runtime.
4. Print or display `format_update_message(result)` if non-empty.
5. Import and launch the app normally.

The updater must stay conservative:

- Apply only manifest-listed files whose paths match `allowed_payload_paths`.
- Refuse blocked dependency, packaging, build, or local-data path changes.
- Verify the current installed file hash against the manifest baseline for the detected installed version.
- Support jump-ahead updates from multiple compatible previous versions through `previous_sha256_by_version`.
- Skip or block safely instead of overwriting unknown local edits.
- Depend only on the Python standard library unless a future maintainer explicitly changes the project scope.

## Builder Contract

The update-asset builder lives in `src/desktop_source_updater/build_update_asset.py` and is exposed as:

```powershell
python -m desktop_source_updater.build_update_asset
```

It should be run from an app repository, not necessarily this repository. It reads Git refs, builds a custom source update zip, and supports repeated `--from-ref` values so one latest release asset can update users who skipped compatible releases.

If dependency or packaging files changed between any `--from-ref` and `--to-ref`, the builder should refuse to create a source-only update asset.

## Verification

Use these checks after substantive changes:

```powershell
python -m unittest
python -m py_compile src\desktop_source_updater\*.py
python -m desktop_source_updater.build_update_asset --help
```

No formatter or linter is configured yet. Do not add one as drive-by churn unless the user asks.

## Adoption Notes

For a downstream app, the minimal app-specific choices are:

- `app_name`
- `release_api_url`
- `asset_prefix`
- `installed_version_file` or explicit `installed_version`
- `allowed_payload_paths`
- optional app-specific environment variable names

Do not assume every app uses `fp_analysis_app/`; keep path and env names configurable.

## Current Follow-Up

Before broad adoption, test this package in at least two real desktop apps. The first known source is `C:\Users\yzhao\python_projects\fp_analysis`, where the prototype originated.
## Windows Git Note

If Git reports dubious ownership for this checkout, use a per-command safe-directory override for read-only checks:

```powershell
git -c safe.directory=C:/Users/yzhao/python_projects/desktop_source_updater status --short --branch
```

Only add a global safe-directory entry if the user explicitly asks for it.

