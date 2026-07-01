# Project Overview

This document orients a new agent or human collaborator to the active codebase.
Keep it current when the updater contract, builder flow, or file layout changes.

## What This Repo Is

`desktop_app_source_updater` is a small Python package for code-only updates in
desktop apps that ship a stable launcher plus updateable source code beside it.
It is meant for apps where the launcher can check a GitHub Release asset before
importing the real app package.

The stack is deliberately plain Python: standard library runtime code, a flat
package directory at `desktop_app_source_updater/`, setuptools metadata in
`pyproject.toml`, and unittest coverage under `tests/`.

## Active Runtime Path

### 1. Downstream App Launcher

External to this repository.

- Computes the app root.
- Optionally puts an adjacent source folder on `sys.path`.
- Calls `run_startup_update(UpdateConfig(...))` before importing the app.
- Displays `format_update_message(result)` when it returns a non-empty string.

### 2. Public Package API

[`desktop_app_source_updater/__init__.py`](desktop_app_source_updater/__init__.py)

- Re-exports the public runtime API: `UpdateConfig`,
  `StartupUpdateResult`, `run_startup_update`, `format_update_message`,
  `read_python_assignment_version`, `UpdateError`, and blocked-path defaults.
- This is the import surface downstream apps should use.

### 3. Startup Update Runtime

[`desktop_app_source_updater/core.py`](desktop_app_source_updater/core.py)

- Resolves the installed app version from an explicit value or Python assignment
  in `installed_version_file`.
- Resolves an update zip from a direct URL, local file path, file URL, or latest
  GitHub Release metadata plus `asset_prefix`.
- Loads and validates `manifest.json`, payload hashes, app name, schema version,
  allowed paths, compatibility versions, and baseline hashes.
- Blocks dependency, packaging, build, cache, archive, and local-data paths.
- Applies payload files with a temporary backup and rollback on failure.
- Returns status/message data instead of raising for normal update outcomes.

### 4. Release Asset Builder

[`desktop_app_source_updater/build_update_asset.py`](desktop_app_source_updater/build_update_asset.py)

- CLI entry point for building custom source update zips from an app repository.
- Reads target and baseline files from Git refs with `git show`.
- Supports repeated `--from-ref` values for jump-ahead compatibility.
- Refuses source-only assets when blocked path categories changed.
- Refuses runtime deletions, renames, and complex changes because those need a
  packaged refresh.
- Emits a zip with `manifest.json` plus changed runtime payload files.

## Repo Structure Map

```text
project_root/
|- AGENTS.md
|- README.md
|- project_overview.md
|- next_steps.md
|- work_log.md
|- work_log_archive/
|- pyproject.toml
|- desktop_app_source_updater/
|  |- __init__.py
|  |- core.py
|  `- build_update_asset.py
`- tests/
   |- test_core.py
   `- test_build_update_asset.py
```

## What Looks Active vs. Legacy

### Active / relevant now

- [`desktop_app_source_updater/core.py`](desktop_app_source_updater/core.py)
- [`desktop_app_source_updater/build_update_asset.py`](desktop_app_source_updater/build_update_asset.py)
- [`desktop_app_source_updater/__init__.py`](desktop_app_source_updater/__init__.py)
- [`tests/test_core.py`](tests/test_core.py)
- [`tests/test_build_update_asset.py`](tests/test_build_update_asset.py)
- [`README.md`](README.md)
- [`AGENTS.md`](AGENTS.md)
- [`next_steps.md`](next_steps.md)
- [`work_log.md`](work_log.md)

### Likely older or secondary

- No legacy implementation is currently in-tree.

## Tests And Fixtures

- [`tests/test_core.py`](tests/test_core.py) covers runtime update behavior with
  temporary app roots, local release zips, release metadata JSON, jump-ahead
  baselines, blocked paths, and local edit hash mismatches.
- [`tests/test_build_update_asset.py`](tests/test_build_update_asset.py) creates
  temporary Git repositories to verify multi-baseline manifest generation and
  refusal of dependency changes. These tests skip only when Git is unavailable.
- There is no persistent sample-data directory. Fixtures are generated in
  temporary directories by the tests.

Current verification commands:

```powershell
$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"
& $py -m unittest discover -s tests
& $py -m compileall -q desktop_app_source_updater
& $py -m desktop_app_source_updater.build_update_asset --help
```

## User Data Expectations

The package should not touch user data. It reads release metadata and update
assets, then writes only manifest-listed source files that pass path and hash
checks.

The custom update zip format is:

```text
manifest.json
<allowed runtime path>/...
```

The manifest schema version is currently `1`. Important fields include:

- `app`: must match `UpdateConfig.app_name`.
- `version`: target version in the update asset.
- `from_versions`: compatible installed versions.
- `changed_files`: changed runtime paths used for messages and policy checks.
- `files`: payload entries with `path`, `sha256`, and preferably
  `previous_sha256_by_version`.

## Practical Mental Model

If you only want to understand the current product, read files in this order:

1. [`README.md`](README.md)
2. [`AGENTS.md`](AGENTS.md)
3. [`desktop_app_source_updater/__init__.py`](desktop_app_source_updater/__init__.py)
4. [`desktop_app_source_updater/core.py`](desktop_app_source_updater/core.py)
5. [`desktop_app_source_updater/build_update_asset.py`](desktop_app_source_updater/build_update_asset.py)
6. [`tests/test_core.py`](tests/test_core.py)
7. [`tests/test_build_update_asset.py`](tests/test_build_update_asset.py)

## Questions Worth Clarifying Later

- Which named Python or conda environment, if any, should become the documented
  default for this repo?
- Should this package be published as an internal editable dependency, a GitHub
  release artifact, or a PyPI package for downstream desktop apps?
- Which two downstream apps should count as the first adoption proof before the
  updater is considered broadly ready?
- Should future source-only updates support deletions or renames, or should
  those remain packaged-refresh-only cases?
