# Desktop App Source Updater

[![Agent Collab Treaty](https://raw.githubusercontent.com/yzhaoinuw/agent_collab_treaty/main/assets/treaty-adopted.svg)](https://github.com/yzhaoinuw/agent_collab_treaty)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21763329.svg)](https://doi.org/10.5281/zenodo.21763329)

`desktop_app_source_updater` lets a packaged Python desktop app update its own
source code from a GitHub Release, so a one-line fix doesn't mean rebuilding and
redistributing the whole app. It was built for apps frozen with PyInstaller but
depends on nothing from PyInstaller — any Python desktop app that ships a stable
launcher beside plain, updateable source files can use it.

## Content Overview

- [Installation](#installation)
- [Usage](#usage)
- [Real-World Examples](#real-world-examples)
- [Common Questions](#common-questions)
- [Configuration](#configuration)
- [Build and Publish an Update](#build-and-publish-an-update)
- [Update Scope and Safety](#update-scope-and-safety)
- [Reference](#reference) — release checks, multiple baselines, config merging,
  verification, troubleshooting, development
- [Adopting This in an App](#adopting-this-in-an-app)
- [Citation](#citation)
- [Acknowledgment](#acknowledgment)
- [License](#license)

## Installation

Python 3.10 or newer. No runtime dependencies outside the standard library.

```powershell
python -m pip install desktop-app-source-updater
```

Pin an exact version in the app's dependency file — `UpdateConfig`'s field order
is part of the public surface, and a launcher frozen into a packaged app cannot
be corrected afterward:

```text
desktop-app-source-updater==0.3.0

# or pin a commit or tag instead of a release:
desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@v0.3.0
```

Bundle this dependency into the app's next full packaged release. End-user
machines need neither Git nor a clone of this repository.

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

Replace the example names and paths with the adopting app's own. What matters is
the order: run the update, display any nonempty message, then import the app
runtime.

The first release that adds this dependency must be a full packaged release.
Later compatible releases can then ship small source-update assets.

## Real-World Examples

These maintained desktop apps use this package in their startup launchers:

- [`sleep_scoring`](https://github.com/yzhaoinuw/sleep_scoring) applies
  lightweight release updates to its `app_src/` runtime before launching the
  packaged sleep-scoring application.
- [`fp_analysis`](https://github.com/yzhaoinuw/fp_analysis) updates its
  `fp_analysis_app/` runtime while enforcing additional app-specific boundaries
  for local data and generated assets.

## Common Questions

### How do I update a PyInstaller app without rebuilding it?

Ship the app's Python source as plain files beside the frozen launcher instead of
inside the bundle, and call this package from that launcher before the source is
imported. It downloads a zip of only the changed files from your GitHub Release
and swaps them in, so a fix reaches users without a new build or installer.
Changes to dependencies, packaging, or the interpreter still need a full packaged
release — see [Update Scope and Safety](#update-scope-and-safety).

### Can I keep my `.py` files outside the frozen bundle and update only those?

Yes; that arrangement is what this package assumes. The frozen bundle holds the
interpreter and the compiled dependencies and is never touched, while
`allowed_payload_paths` names the source directories an update may change.
Anything outside them is refused.

### Do I need code signing or an update server?

Neither. Updates are ordinary GitHub Release assets fetched over HTTPS from your
own repository, so there is no server to run and no signing keys to generate or
protect. The trade-off is that the trust model is your GitHub account and TLS
rather than a signature over the payload.

### How does this compare to PyUpdater and tufup?

Both replace the whole frozen bundle.
[PyUpdater](https://github.com/Digital-Sapphire/PyUpdater), long the standard for
PyInstaller apps, is archived and unmaintained; its successor
[tufup](https://github.com/dennisvang/tufup) is actively maintained and ships
full or patched bundle archives signed with The Update Framework.

This package fills a different niche. It updates only the app's own Python source
and leaves the frozen bundle — the interpreter and every compiled dependency —
untouched, so an update is a zip of changed files rather than a copy of the
application, and applying one needs nothing outside the standard library. In
exchange there is no cryptographic signing, and dependency or packaging changes
still require a full packaged release. If your threat model requires signed
updates, use tufup.

## Configuration

The values most integrations set:

| Field | Purpose |
| --- | --- |
| `app_name` | Stable application name recorded in the update manifest. |
| `app_root` | Installed directory containing the launcher and app source. |
| `installed_version_file` or `installed_version` | Current app version used for compatibility checks. |
| `latest_release_url` | The adopting app's GitHub URL ending in `/releases/latest`. |
| `asset_prefix` | Prefix for source-update assets, such as `my_app_update_`. |
| `allowed_payload_paths` | Source directories that an update may change. |
| `check_state_file` | App-specific, per-user JSON file for durable check throttling. Use an absolute path; relative paths resolve under `app_root`. |

The default version-file pattern reads a simple assignment such as
`VERSION = "1.2.3"`.

Optional environment-variable fields make development and support easier:

| Field | Typical use |
| --- | --- |
| `skip_update_env` | Disable startup updates temporarily. |
| `update_zip_url_env` | Test a local zip or prerelease asset directly. |
| `timeout_env` | Override the network timeout. |
| `force_check_env` | Bypass the normal check interval. |

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

Use one `--from-ref` for every prior release that may update directly to the new
version. The builder validates the changed paths and refuses to create a
source-only asset when the release requires a full packaged update.

Attach the generated zip to the app's GitHub Release under exactly
`<asset_prefix><release-tag>.zip` — `my_app_update_v1.2.3.zip` for the example
above. The manifest version and the release tag must agree, with a leading `v`
treated as equivalent; pass `--version` or `--output` when the version file
stores `1.2.3` and the tag is `v1.2.3`.

## Update Scope and Safety

Source-update assets are for changes to approved runtime source files. Publish a
full packaged release when a change affects dependencies, packaging, build files,
environments, data, file deletions, or file renames.

Before applying an asset, the updater checks every listed file against the
baselines recorded in the manifest. If any file has unknown bytes, the entire
asset is skipped and nothing changes; this protects local patches and prevents
partial updates across mutually dependent modules. Files not listed in the asset
are never inspected or changed. The one exception to whole-file baseline
replacement is the declared config file described under
[User-Editable Python Configuration](#user-editable-python-configuration).

Updates are prepared before mutation and applied through a backup-and-rollback
transaction. The updater also blocks payload paths outside
`allowed_payload_paths` and rejects dependency, packaging, build, cache, archive,
and local-data paths.

## Reference

Details worth looking up once an integration is working.

### Release Checks

With `latest_release_url`, the updater discovers the newest tag through GitHub's
ordinary `/releases/latest` redirect, compares it with the installed version, and
checks for the deterministic asset filename before announcing or downloading an
update. A release without that asset is treated as up to date.

Successful checks are cached for `check_interval_seconds`, which defaults to 24
hours. Failed checks retry after `failure_retry_seconds`, which defaults to 1
hour. HTTP 403 and 429 backoff is persisted and takes precedence. Direct zip
overrides bypass discovery and its cache.

`release_api_url` and `release_api_env` remain available for existing adopters,
but new integrations should use `latest_release_url` to avoid unauthenticated
GitHub REST API rate limits.

### Multiple Installed Baselines

Use repeatable `--installed-baseline-manifest` arguments when installations
reporting the same version can legitimately contain different bytes, such as LF
Git blobs and CRLF files from a Windows package:

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

Each manifest names a version already supplied through `--from-ref` and maps every
changed runtime path to its installed SHA-256. Use `null` only when the file was
absent:

```json
{
  "version": "v1.2.2",
  "files": {
    "my_app_src/app.py": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "my_app_src/new_module.py": null
  }
}
```

The builder deduplicates equivalent hashes, preserves version-specific baselines
where needed, and refuses combinations the manifest schema cannot represent
safely.

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
functions, comments, ordering, removed settings, and undeclared assignments come
from the downloaded file.

Both files are parsed without being imported or executed. Invalid Python,
duplicate or unsupported assignments, and nonliteral editable values fail the
entire update before mutation.

The adopting app must first ship a full release containing a schema-2-compatible
updater; older packaged updaters reject schema-2 assets.

### Verifying an Integration

Before shipping, confirm that:

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

Point `update_zip_url_env` at a generated zip to exercise the apply path locally
without publishing a GitHub Release.

### Troubleshooting

`format_update_message(result)` is empty for quiet outcomes such as disabled,
throttled, or already up to date. For other outcomes, inspect `result.status` and
`result.reason`:

| Status | Meaning |
| --- | --- |
| `updated` | The source update was applied. |
| `skipped` | Local state did not match a safe update baseline. |
| `blocked` | The asset was incompatible or contained disallowed changes. |
| `failed` | Discovery, download, validation, callback, or application failed. |

The result also exposes `installed_version` and `target_version`, and labels
discovery and asset-download errors separately.

For debugging:

- enable `skip_update_env` to bypass startup updates;
- call `run_startup_update(update_config, force_check=True)` for an immediate
  remote check;
- use `force_check_env` for the same behavior without a code change;
- use `update_zip_url_env` to test a local zip or explicit asset URL.

### Development

Use Python 3.10 or newer:

```powershell
python -m unittest discover -s tests
python -m compileall -q desktop_app_source_updater
python -m desktop_app_source_updater.build_update_asset --help
```

The public API is exported from `desktop_app_source_updater/__init__.py`; the
runtime implementation is in `desktop_app_source_updater/core.py`.

## Adopting This in an App

The integration is mechanical enough that a capable coding agent can do it from a
short instruction. Paste this into the adopting app's repository:

```text
Adopt desktop-app-source-updater in this app. Add it as a pinned dependency, then
call run_startup_update(UpdateConfig(...)) from the stable launcher, before the
app's own source package is imported.

Read this repo to find the launcher, the updateable source package, and the
version file. Bundle the updater in a full packaged release before publishing any
source-update asset.
```

## Citation

If you use this package in research, use GitHub's **Cite this repository** button
or the
[CITATION.cff](https://github.com/yzhaoinuw/desktop_app_source_updater/blob/main/CITATION.cff)
file to obtain an APA or BibTeX entry.

Each release is archived on Zenodo. Cite the concept DOI
[10.5281/zenodo.21763329](https://doi.org/10.5281/zenodo.21763329), which resolves
to the newest release; use a release's own DOI only when you need to pin the exact
version you ran.

## Acknowledgment

This package was extracted from software developed for research supported in part
by the BRAIN Initiative of the US National Institutes of Health (U19NS128613).

## License

Released under the MIT License — see
[`LICENSE`](https://github.com/yzhaoinuw/desktop_app_source_updater/blob/main/LICENSE).
