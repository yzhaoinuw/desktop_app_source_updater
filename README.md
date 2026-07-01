# Desktop App Source Updater

[![Agent Collab Treaty](https://raw.githubusercontent.com/yzhaoinuw/agent_collab_treaty/main/assets/treaty-adopted.svg)](https://github.com/yzhaoinuw/agent_collab_treaty)

`desktop_app_source_updater` is a small stdlib-only updater for Python desktop apps that ship a stable launcher plus updateable source code beside it.

It is for apps with this shape:

```text
run_desktop_app.py
  -> optionally applies a code-only update
  -> imports the app package from src/, app_src/, fp_analysis_app/, etc.
```

The updater checks a GitHub Release asset such as `my_app_update_v1.2.3.zip`, validates its manifest and hashes, and replaces only approved runtime source files before the app imports. Users do not need Git installed.

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
import sys

from desktop_app_source_updater import UpdateConfig, format_update_message, run_startup_update

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

result = run_startup_update(
    UpdateConfig(
        app_name="my_app",
        app_root=APP_ROOT,
        installed_version_file="my_app_src/__init__.py",
        release_api_url="https://api.github.com/repos/me/my_app/releases/latest",
        asset_prefix="my_app_update_",
        allowed_payload_paths=("my_app_src/",),
        skip_update_env="MY_APP_SKIP_UPDATE",
        update_zip_url_env="MY_APP_UPDATE_ZIP_URL",
        timeout_env="MY_APP_UPDATE_TIMEOUT_SECONDS",
    )
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
- `release_api_url`: latest-release API URL for the app repo, not this updater repo
- `asset_prefix`: release asset prefix, for example `fp_analysis_update_`
- `allowed_payload_paths`: source paths the updater may replace, for example `("fp_analysis_app/",)`
- `installed_version_file` or `installed_version`: how the updater knows the current app version

Recommended environment variables:

- `skip_update_env`: let developers/users bypass startup updates, for example `MY_APP_SKIP_UPDATE=1`
- `update_zip_url_env`: let tests point directly at a local zip or test asset
- `timeout_env`: let troubleshooting override the network timeout

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
  --to-ref v1.2.3 `
  --version-file my_app_src/__init__.py `
  --asset-prefix my_app_update_
```

Use one `--from-ref` for each previous release that should be able to jump to the new version. If the builder refuses because dependency or packaging paths changed, publish a full packaged release instead.

### 7. Upload The Zip To The App Release

Attach the generated zip to the app's GitHub Release. The default filename is:

```text
<asset_prefix><version>.zip
```

For example:

```text
my_app_update_1.2.3.zip
```

The runtime finds the latest GitHub Release, chooses the matching zip asset, validates the manifest, and applies it only if the installed version is compatible and local files match the expected baseline.

## Test Before Shipping

At minimum, test these cases in the app repo:

- clean compatible install updates successfully
- skipped-release jump updates successfully when multiple `--from-ref` values are included
- local edit/hash mismatch skips without overwriting user-modified files
- dependency or packaging changes make the builder refuse a source-only asset
- `MY_APP_SKIP_UPDATE=1` bypasses the startup update
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
- release_api_url
- asset_prefix
- allowed_payload_paths
- skip/update/timeout env var names if useful

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

`format_update_message(result)` returns empty text for normal quiet outcomes such as disabled or already up to date. For visible messages:

- `updated`: update applied
- `skipped`: updater found a reason not to modify local files, often a hash mismatch
- `blocked`: update is incompatible or includes paths that require a full packaged release
- `failed`: metadata, download, zip, manifest, or apply step failed

Use `skip_update_env` to bypass updates during debugging. Use `update_zip_url_env` to test with a local zip path.

## Development

```powershell
python -m unittest discover -s tests
python -m compileall -q desktop_app_source_updater
python -m desktop_app_source_updater.build_update_asset --help
```
