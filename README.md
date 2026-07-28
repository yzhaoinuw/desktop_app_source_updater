# Desktop App Source Updater

[![Agent Collab Treaty](https://raw.githubusercontent.com/yzhaoinuw/agent_collab_treaty/main/assets/treaty-adopted.svg)](https://github.com/yzhaoinuw/agent_collab_treaty)

`desktop_app_source_updater` is a small stdlib-only updater for Python desktop apps that ship a stable launcher plus updateable source code beside it.

It is for apps with this shape:

```text
run_desktop_app.py
  -> optionally applies a code-only update
  -> imports the app package from src/, app_src/, fp_analysis_app/, etc.
```

The updater checks a GitHub Release asset such as `my_app_update_v1.2.3.zip`,
validates its manifest and hashes, and replaces only approved runtime source
files before the app imports. It discovers the latest tag from GitHub's
ordinary `/releases/latest` redirect, so normal startup checks do not spend
GitHub REST API quota. Users do not need Git installed.

## The Short Version

Do not clone this repo inside your app repo. Treat it as an external Python dependency and bundle it into the app's next normal packaged release.

Until this package is on PyPI, install it from GitHub:

```powershell
python -m pip install "desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@main"
```

Or add this to the app's dependency file:

```text
desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@main
```

Then add the updater call to the app's stable launcher before importing the real app runtime. After that first bundled release, future code-only releases can publish small update zip assets instead of requiring users to reinstall the whole app.

## What This Does And Does Not Do

This does:

- update selected Python source files before the app imports
- fetch a custom zip from the app's GitHub Releases
- verify payload hashes and installed-file baseline hashes
- support users jumping across multiple compatible previous versions
- skip safely when local runtime files differ from the expected baseline

This does not:

- install Python itself
- install or update dependencies
- replace a full packaged app installer
- update PyInstaller specs, conda envs, lockfiles, data files, caches, or build outputs
- handle source deletions or renames as hot updates

If dependencies, packaging, build files, local data, deletions, or renames change, ship a normal full packaged app release.

## Why Ordinary Local Edits Skip The Whole Update

The updater checks only the files listed in a particular update asset. Every
ordinary listed file must match a recognized installed baseline before any
file is changed. If even one ordinary file has unknown bytes, the updater
skips the entire asset and leaves every file unchanged. It does not overwrite
the edited file or partially update the remaining files.

This fail-closed behavior is intentional. A hash mismatch could be a deliberate
user patch, an emergency local fix, accidental damage, or an unexpected package
build. The updater cannot safely decide that those bytes are disposable, and
updating only part of a release could leave mutually dependent modules at
incompatible versions.

A source file that is not listed in the update asset is not inspected or
touched. If a later asset needs to update that file, its installed bytes must
then match a recognized baseline. The schema-2 Python config merge described
below is the only exception to whole-file baseline matching, and it applies
only to the explicitly declared user-editable config file and assignment names.

## Adopt It In An Existing App

### 1. Add The Dependency

For development and packaging, install from GitHub:

```powershell
python -m pip install "desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@main"
```

For a repo dependency file, use:

```text
desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@main
```

The end-user machine should not need Git. Your packaging process must bundle this dependency into the next full app build.

### 2. Identify The Stable Launcher

Find the file users actually run, often something like:

```text
run_desktop_app.py
Start My App.cmd
packaging/windows/...
```

The updater call belongs in the Python launcher before the real app package is imported. Do not put it deep inside the app runtime after imports already happened.

### 3. Add Startup Update Code

Example launcher pattern:

```python
from pathlib import Path
import os
import sys

from desktop_app_source_updater import UpdateConfig, format_update_message, run_startup_update

APP_ROOT = Path(__file__).resolve().parent
USER_STATE_ROOT = Path(
    os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache")
)
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

def show_update_available(installed_version, target_version):
    print(
        f"[startup-update] updating from version "
        f"{installed_version} to version {target_version}",
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

Replace every `my_app` value with app-specific names. The important part is that `run_startup_update(...)` runs before `from my_app_src...` imports the real app.

### 4. Choose App-Specific Config Values

Required choices:

- `app_name`: stable manifest app name, for example `fp_analysis`
- `app_root`: folder containing the installed launcher and source folder
- `latest_release_url`: ordinary GitHub URL ending in `/releases/latest` for
  the app repo, not this updater repo
- `asset_prefix`: release asset prefix, for example `fp_analysis_update_`
- `allowed_payload_paths`: source paths the updater may replace, for example `("fp_analysis_app/",)`
- `installed_version_file` or `installed_version`: how the updater knows the current app version
- `check_state_file`: app-specific per-user JSON path used for durable check
  throttling; relative paths resolve under `app_root`, but an absolute
  per-user path is recommended

Recommended environment variables:

- `skip_update_env`: let developers/users bypass startup updates, for example `MY_APP_SKIP_UPDATE=1`
- `update_zip_url_env`: let tests point directly at a local zip or test asset
- `timeout_env`: let troubleshooting override the network timeout
- `force_check_env`: bypass the normal check interval for an explicit package
  gate or troubleshooting check

`check_interval_seconds` defaults to 24 hours. After a successful tag check, a
second launch inside that interval makes no network request. HTTP 403 and 429
responses persist their `Retry-After` or `X-RateLimit-Reset` backoff in the same
atomic state file, so repeated launches do not hammer GitHub. Missing or corrupt
state is ignored safely.

For an explicit check, call
`run_startup_update(update_config, force_check=True)` or enable the configured
`force_check_env`. Direct `update_url` and `update_zip_url_env` overrides remain
available for package gates and tests; they bypass remote discovery and its
cache. State is also keyed to the configured release source and asset prefix,
so changing a remote test endpoint is not suppressed by an unrelated cached
check.

`release_api_url` and `release_api_env` remain supported for existing adopters.
That legacy mode now reads `tag_name` and compares it with the installed version
before downloading an asset, but new integrations should prefer
`latest_release_url` to avoid unauthenticated GitHub REST API rate limits.

The version file should contain a simple assignment that the default regex can read:

```python
VERSION = "1.2.3"
```

### 5. Ship The First Adoption As A Full Release

The first time you add this updater to an app, it is a new dependency. That release must be shipped as a normal full packaged app so the updater package is present on user machines.

After that, source-only update zips can update compatible app versions when only allowed source files changed.

### 6. Build A Source Update Asset

Run the builder from the app repo, not from this updater repo:

```powershell
python -m desktop_app_source_updater.build_update_asset `
  --app-name my_app `
  --runtime-path my_app_src `
  --from-ref v1.2.0 `
  --from-ref v1.2.1 `
  --from-ref v1.2.2 `
  --installed-baseline-manifest release_baselines/v1.2.2-windows.json `
  --to-ref v1.2.3 `
  --version v1.2.3 `
  --version-file my_app_src/__init__.py `
  --asset-prefix my_app_update_
```

Use one `--from-ref` for each previous release that should be able to jump to the new version. If the builder refuses because dependency or packaging paths changed, publish a full packaged release instead.

Use repeatable `--installed-baseline-manifest` arguments when legitimate
installations reporting the same version can contain different bytes, such as
LF Git blobs and CRLF files from a Windows package. Each compact JSON manifest
names a version already declared by `--from-ref` and maps every changed runtime
path to its exact installed SHA-256. Use `null` only when that file was absent:

```json
{
  "version": "v1.2.2",
  "files": {
    "my_app_src/app.py": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "my_app_src/new_module.py": null
  }
}
```

The builder deduplicates hashes and keeps version-specific baselines whenever
each version has one known file state. When a file has multiple present-byte
baselines, it emits the schema-1 `previous_sha256` accepted-hash list while
`from_versions` remains the compatibility gate. Schema 1 cannot represent a
changed path whose baseline set needs both a missing-file state and multiple
present-file hashes, so the builder refuses that case instead of creating an
unsafe or incomplete asset.

### Merge One User-Editable Python Config

If an app intentionally keeps user settings in a Python config file, a schema-2
asset can merge that one file while every other payload file retains the normal
hash-verified replacement behavior:

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

The path is app-specific; the updater does not hard-code `config.py`. The
assignment allowlist is also explicit because a config module may contain
derived runtime values that users are not meant to control.

For the declared assignments, the downloaded file remains the authoritative
template:

- a value present in both files keeps the installed user's value;
- a value missing from the installed file uses the downloaded default;
- assignments and dictionary keys removed from the downloaded template remain
  removed;
- literal dictionaries merge recursively, while scalar and list values are
  preserved atomically;
- imports, functions, comments, ordering, and undeclared assignments come from
  the downloaded file.

Both files are parsed without being imported or executed. Invalid Python,
duplicate or unsupported editable assignments, and nonliteral editable values
fail the entire update before mutation. The merged final bytes are prepared and
compiled before the existing backup-and-rollback transaction applies any file.

Schema 2 is a frozen-runtime compatibility boundary. An older updater supports
only schema 1 and rejects schema-2 assets instead of ignoring the merge request
and overwriting the config. Therefore, an app must first ship a full packaged
release containing a schema-2-compatible updater. It cannot safely introduce
this capability to an old packaged installation through a source-only asset.

### 7. Upload The Zip To The App Release

Attach the generated zip to the app's GitHub Release. API-free redirect
discovery uses this exact deterministic filename:

```text
<asset_prefix><release-tag>.zip
```

For example:

```text
my_app_update_v1.2.3.zip
```

The manifest version and release tag must agree, with an optional leading `v`
treated as equivalent. If the app's version file stores `1.2.3` while the
GitHub tag is `v1.2.3`, either pass `--version v1.2.3` to the builder or use
`--output` to give the zip the tag-based filename above.

The runtime discovers the latest GitHub Release tag, compares it with the
installed version, and downloads the versioned asset only when the tag is
newer. It then requires the manifest version to agree with the discovered tag,
validates compatibility and local baselines, and applies the payload.

## Test Before Shipping

At minimum, test these cases in the app repo:

- clean compatible install updates successfully
- skipped-release jump updates successfully when multiple `--from-ref` values are included
- local edit/hash mismatch skips without overwriting user-modified files
- one ordinary bundled-file edit skips the entire asset without partially
  applying other files
- schema-2 config updates preserve declared user values while replacing
  ordinary source files normally
- dependency or packaging changes make the builder refuse a source-only asset
- `MY_APP_SKIP_UPDATE=1` bypasses the startup update
- a second ordinary launch inside the check interval makes zero network requests
- `force_check=True` bypasses the interval
- current and newer installed versions perform tag discovery but never fetch
  the update zip
- HTTP 403/429 responses persist their advertised backoff
- app still launches normally when GitHub is unreachable

For local tests, `update_zip_url_env` can point directly at a generated zip file so you do not need to publish a real release asset for every test.

## Prompt For An Agent

Paste this into an existing app repo when asking an agent to adopt the updater:

```text
Adopt desktop_app_source_updater in this app.

Do not clone or vendor the updater repo into this app repo. Treat it as an external Python dependency from GitHub:

desktop-app-source-updater @ git+https://github.com/yzhaoinuw/desktop_app_source_updater.git@main

First read this repo's AGENTS.md and project docs. Identify:
- the stable desktop launcher users run
- the active app source folder/package
- where the app version is defined
- how this app is packaged for end users
- the GitHub repo whose Releases should host update zip assets

Wire the updater into the launcher before the real app runtime is imported:

from desktop_app_source_updater import UpdateConfig, run_startup_update, format_update_message

Use app-specific config values:
- app_name
- app_root
- installed_version_file or installed_version
- latest_release_url
- asset_prefix
- allowed_payload_paths
- an app-specific per-user check_state_file
- skip/update/timeout/force-check env var names if useful

Important constraints:
- This updater is for code-only source updates.
- The first adoption adds a dependency, so it must ship as a normal full packaged release.
- Future source-update zips must not include dependency, packaging, build, cache, archive, local-data, deletion, or rename changes.
- End users should not need Git or a clone of the updater repo.

After wiring it:
- update the app dependency/build/packaging files so the updater is bundled
- add or update README/release docs explaining source-update assets
- run the app's tests/smoke checks
- build a test update asset with python -m desktop_app_source_updater.build_update_asset
- verify a clean compatible install updates
- verify a local-edit mismatch safely skips
- document the app-specific UpdateConfig choices in AGENTS.md or work_log.md
```

## Troubleshooting

`format_update_message(result)` returns empty text for normal quiet outcomes
such as disabled, throttled, or already up to date. The result also exposes
backwards-compatible `installed_version` and `target_version` metadata. For
visible messages:

- `updated`: update applied
- `skipped`: updater found a reason not to modify local files, often a hash mismatch
- `blocked`: update is incompatible or includes paths that require a full packaged release
- `failed`: tag/metadata discovery, asset download, zip, manifest, callback, or
  apply step failed

Discovery and asset-download errors are labeled separately. Use
`skip_update_env` to bypass updates during debugging,
`run_startup_update(..., force_check=True)` for an explicit remote check, and
`update_zip_url_env` to test with a local zip path.

## Development

```powershell
python -m unittest discover -s tests
python -m compileall -q desktop_app_source_updater
python -m desktop_app_source_updater.build_update_asset --help
```
