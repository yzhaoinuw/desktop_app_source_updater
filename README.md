# Desktop App Source Updater

`desktop_app_source_updater` is a small stdlib-only updater for Python desktop apps that ship a stable launcher plus updateable source code beside it.

It is meant for apps with this shape:

```text
run_desktop_app.py
  -> optionally applies a code-only update
  -> imports the app package from src/, app_src/, fp_analysis_app/, etc.
```

The updater checks a GitHub Release asset such as `my_app_update_v1.2.3.zip`, validates its manifest and hashes, and replaces only approved runtime source files before the app imports. Users do not need Git installed.

## Runtime Usage

Call the updater before importing the app runtime:

```python
from desktop_app_source_updater import UpdateConfig, format_update_message, run_startup_update

config = UpdateConfig(
    app_name="my_app",
    app_root=base_path,
    installed_version_file="my_app_src/__init__.py",
    release_api_url="https://api.github.com/repos/me/my_app/releases/latest",
    asset_prefix="my_app_update_",
    allowed_payload_paths=("my_app_src/",),
    skip_update_env="MY_APP_SKIP_UPDATE",
    update_zip_url_env="MY_APP_UPDATE_ZIP_URL",
)

result = run_startup_update(config)
message = format_update_message(result)
if message:
    print(f"[startup-update] {message}", flush=True)
```

## Release Asset Format

Each custom release asset is a zip with `manifest.json` at the root and payload files at their final relative paths:

```text
my_app_update_v1.2.3.zip
|- manifest.json
`- my_app_src/
   `- app.py
```

The manifest includes the target version, compatible source versions, payload hashes, and baseline hashes for each supported installed version. A single latest asset can jump users forward from multiple older versions when dependencies did not change.

## Build An Update Asset

From an app repository:

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

The command refuses to build a source-only update if dependency, packaging, build, or local-data paths changed. In that case, publish a full packaged app instead.

## Development

```powershell
python -m unittest discover -s tests
python -m compileall -q desktop_app_source_updater
```
