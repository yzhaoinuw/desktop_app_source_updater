# Desktop App Source Updater

[![Agent Collab Treaty](https://raw.githubusercontent.com/yzhaoinuw/agent_collab_treaty/main/assets/treaty-adopted.svg)](https://github.com/yzhaoinuw/agent_collab_treaty)

`desktop_app_source_updater` lets packaged Python desktop apps apply small,
code-only updates from GitHub Releases before the app source is imported. It
verifies the release and local files, then atomically updates only explicitly
allowed source paths.

## Content Overview

- [Installation](#installation)
- [Usage](#usage)
- [Real-World Examples](#real-world-examples)
- [Configuration](#configuration)
- [Build and Publish an Update](#build-and-publish-an-update)
- [Test an Integration](#test-an-integration)
- [Advanced Configuration](#advanced-configuration)
- [Update Scope and Safety](#update-scope-and-safety)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Agent Adoption Prompt](#agent-adoption-prompt)

## Installation

Python 3.10 or newer is required. The package has no runtime dependencies
outside the Python standard library.

Until the package is published on PyPI, install it from GitHub:

```powershell
python -m pip install "desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@main"
```

Or add the same direct reference to the app's dependency file:

```text
desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@main
```

Bundle this dependency into the app's next full packaged release. End-user
machines do not need Git or a clone of this repository.

## Usage

Call the updater from the stable Python launcher that users run, before the
launcher imports the app's updateable source package:

```python
from pathlib import Path
import os
import sys

from desktop_app_source_updater import (
    UpdateConfig,
    format_update_message,
    run_startup_update,
)

APP_ROOT = Path(__file__).resolve().parent
USER_STATE_ROOT = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache"))

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def show_update_available(installed_version, target_version):
    print(
        f"[startup-update] updating from {installed_version} to {target_version}",
        flush=True,
    )


update_config = UpdateConfig(
    app_name="my_app",
    app_root=APP_ROOT,
    installed_version_file="my_app_src/__init__.py",
    latest_release_url="https://github.com/me/my_app/releases/latest",
    asset_prefix="my_app_update_",
    allowed_payload_paths=("my_app_src/",),
    check_state_file=USER_STATE_ROOT / "my_app" / "update-check.json",
    skip_update_env="MY_APP_SKIP_UPDATE",
    update_zip_url_env="MY_APP_UPDATE_ZIP_URL",
    timeout_env="MY_APP_UPDATE_TIMEOUT_SECONDS",
    force_check_env="MY_APP_FORCE_UPDATE_CHECK",
    on_update_available=show_update_available,
)

result = run_startup_update(
    update_config,
    force_check="--check-update" in sys.argv,
)

message = format_update_message(result)
if message:
    print(f"[startup-update] {message}", flush=True)

from my_app_src.app import main

main()
```

Replace the example names and paths with values for the adopting app. The
important ordering is:

1. Import and run `desktop_app_source_updater`.
2. Display any nonempty update message.
3. Import and start the app runtime.

The first release that adds this dependency must be a full packaged release.
Once users have that updater-enabled build, later compatible releases can use
small source-update assets.

## Real-World Examples

These maintained desktop apps use this package in their startup launchers:

- [`sleep_scoring`](https://github.com/yzhaoinuw/sleep_scoring) applies
  lightweight release updates to its `app_src/` runtime before launching the
  packaged sleep-scoring application.
- [`fp_analysis`](https://github.com/yzhaoinuw/fp_analysis) updates its
  `fp_analysis_app/` runtime while enforcing additional app-specific boundaries
  for local data and generated assets.

## Configuration

The main `UpdateConfig` values are:

| Field | Purpose |
| --- | --- |
| `app_name` | Stable application name recorded in the update manifest. |
| `app_root` | Installed directory containing the launcher and app source. |
| `installed_version_file` or `installed_version` | Current app version used for compatibility checks. |
| `latest_release_url` | The adopting app's GitHub URL ending in `/releases/latest`. |
| `asset_prefix` | Prefix for source-update assets, such as `my_app_update_`. |
| `allowed_payload_paths` | Source directories that an update may change. |
| `check_state_file` | App-specific, per-user JSON file for durable check throttling. |

The default version-file pattern reads a simple assignment such as:

```python
VERSION = "1.2.3"
```

Optional environment-variable fields make development and support easier:

| Field | Typical use |
| --- | --- |
| `skip_update_env` | Disable startup updates temporarily. |
| `update_zip_url_env` | Test a local zip or prerelease asset directly. |
| `timeout_env` | Override the network timeout. |
| `force_check_env` | Bypass the normal check interval. |

Use an absolute, per-user path for `check_state_file`. Relative paths resolve
under `app_root`.

## Build and Publish an Update

Run the asset builder from the adopting app repository:

```powershell
python -m desktop_app_source_updater.build_update_asset `
  --app-name my_app `
  --runtime-path my_app_src `
  --from-ref v1.2.0 `
  --from-ref v1.2.1 `
  --from-ref v1.2.2 `
  --to-ref v1.2.3 `
  --version v1.2.3 `
  --version-file my_app_src/__init__.py `
  --asset-prefix my_app_update_
```

Use one `--from-ref` for every prior release that may update directly to the
new version. The builder validates the changed paths and refuses to create a
source-only asset when the release requires a full packaged update.

Attach the generated zip to the adopting app's GitHub Release using this exact
filename:

```text
<asset_prefix><release-tag>.zip
```

For the example above:

```text
my_app_update_v1.2.3.zip
```

The manifest version and release tag must agree; an optional leading `v` is
treated as equivalent. If the version file stores `1.2.3` and the GitHub tag is
`v1.2.3`, pass `--version v1.2.3` or set the tag-based filename with `--output`.

## Test an Integration

Before shipping, verify that:

- a clean compatible installation updates successfully;
- a skipped-release installation updates when all required `--from-ref` values
  are included;
- an unknown local edit skips the asset without changing any payload file;
- dependency or packaging changes make the builder refuse a source-only asset;
- the configured skip variable bypasses the update;
- a second ordinary launch inside the check interval makes no network request;
- a forced check bypasses the interval;
- current and newer installed versions never fetch the update zip;
- the app still launches when GitHub is unreachable.

For local tests, point `update_zip_url_env` at a generated zip file. This tests
the apply path without publishing a GitHub Release.

## Advanced Configuration

### Multiple Installed Baselines

Use repeatable `--installed-baseline-manifest` arguments when installations
reporting the same version can legitimately contain different bytes, such as
LF Git blobs and CRLF files from a Windows package:

```powershell
python -m desktop_app_source_updater.build_update_asset `
  --app-name my_app `
  --runtime-path my_app_src `
  --from-ref v1.2.2 `
  --installed-baseline-manifest release_baselines/v1.2.2-windows.json `
  --to-ref v1.2.3 `
  --version v1.2.3 `
  --version-file my_app_src/__init__.py `
  --asset-prefix my_app_update_
```

Each manifest names a version already supplied through `--from-ref` and maps
every changed runtime path to its installed SHA-256. Use `null` only when the
file was absent:

```json
{
  "version": "v1.2.2",
  "files": {
    "my_app_src/app.py": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "my_app_src/new_module.py": null
  }
}
```

The builder deduplicates equivalent hashes and preserves version-specific
baselines where needed. It refuses baseline combinations that the manifest
schema cannot represent safely.

### User-Editable Python Configuration

A schema-2 asset can merge one explicitly declared Python config file while
ordinary source files continue to use whole-file hash verification:

```powershell
python -m desktop_app_source_updater.build_update_asset `
  --app-name my_app `
  --runtime-path my_app_src `
  --from-ref v1.2.2 `
  --to-ref v1.2.3 `
  --version v1.2.3 `
  --version-file my_app_src/__init__.py `
  --python-config-merge my_app_src/config.py `
  --editable-assignment SLEEP_SCORING_MODEL `
  --editable-assignment WINDOW_CONFIG
```

The downloaded file remains the template. For allowlisted assignments, values
already present in the installed file are preserved, missing values receive the
downloaded defaults, and literal dictionaries merge recursively. Imports,
functions, comments, ordering, removed settings, and undeclared assignments
come from the downloaded file.

Both files are parsed without being imported or executed. Invalid Python,
duplicate or unsupported assignments, and nonliteral editable values fail the
entire update before mutation.

The adopting app must first ship a full release containing a schema-2-compatible
updater. Older packaged updaters reject schema-2 assets.

## Update Scope and Safety

Source-update assets are intended for changes to approved runtime source files.
Publish a full packaged release when a change affects dependencies, packaging,
build files, environments, data, file deletions, or file renames.

Before applying an asset, the updater checks every listed ordinary file against
the baselines recorded in the manifest. If any file has unknown bytes, the
entire asset is skipped and all files remain unchanged. This protects local
patches and prevents partial updates across mutually dependent modules.

Files not listed in the asset are not inspected or changed. The schema-2 merge
described above is the only exception to whole-file baseline replacement, and
it applies only to its declared file and assignment allowlist.

Updates are prepared before mutation and applied through a backup-and-rollback
transaction. The updater also blocks payload paths outside
`allowed_payload_paths` and rejects dependency, packaging, build, cache,
archive, and local-data paths.

### Release Checks

With `latest_release_url`, the updater discovers the newest tag through
GitHub's ordinary `/releases/latest` redirect, compares it with the installed
version, and checks for the deterministic asset filename before announcing or
downloading an update. A release without that asset is treated as up to date.

Successful checks are cached for `check_interval_seconds`, which defaults to
24 hours. Failed checks retry after `failure_retry_seconds`, which defaults to
1 hour. HTTP 403 and 429 backoff is persisted and takes precedence. Direct zip
overrides bypass discovery and its cache.

`release_api_url` and `release_api_env` remain available for existing adopters,
but new integrations should use `latest_release_url` to avoid unauthenticated
GitHub REST API rate limits.

## Troubleshooting

`format_update_message(result)` is empty for quiet outcomes such as disabled,
throttled, or already up to date. For other outcomes, inspect `result.status`
and `result.reason`:

| Status | Meaning |
| --- | --- |
| `updated` | The source update was applied. |
| `skipped` | Local state did not match a safe update baseline. |
| `blocked` | The asset was incompatible or contained disallowed changes. |
| `failed` | Discovery, download, validation, callback, or application failed. |

The result also exposes `installed_version` and `target_version`. Discovery and
asset-download errors are labeled separately.

For debugging:

- enable `skip_update_env` to bypass startup updates;
- call `run_startup_update(update_config, force_check=True)` for an immediate
  remote check;
- use `force_check_env` for the same behavior without a code change;
- use `update_zip_url_env` to test a local zip or explicit asset URL.

## Development

Use Python 3.10 or newer:

```powershell
python -m unittest discover -s tests
python -m compileall -q desktop_app_source_updater
python -m desktop_app_source_updater.build_update_asset --help
```

The public API is exported from `desktop_app_source_updater/__init__.py`; the
runtime implementation is in `desktop_app_source_updater/core.py`.

## Agent Adoption Prompt

The following prompt can be pasted into an adopting app repository:

```text
Adopt desktop_app_source_updater in this app.

Treat it as an external Python dependency from GitHub:

desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@main

First read this repo's AGENTS.md and project docs. Identify the stable launcher,
active app source package, version source, packaging workflow, and GitHub repo
that owns the app's Releases.

Call run_startup_update(UpdateConfig(...)) in the stable launcher before the
app runtime is imported. Configure app_name, app_root, installed_version_file
or installed_version, latest_release_url, asset_prefix, allowed_payload_paths,
an app-specific per-user check_state_file, and useful skip/update/timeout/force
environment-variable names.

Bundle the updater in a full packaged release before publishing source-update
assets. Update the app's dependency, packaging, README, and release guidance.
Then build a test asset, run the app's tests, and verify successful clean and
skipped-release updates, safe local-edit refusal, throttled repeated startup,
and normal launch when GitHub is unavailable.
```
