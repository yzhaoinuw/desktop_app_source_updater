# Guidelines and Tips for Agents

Read this file first when joining this repo. Keep it short, then open the other
docs only when the task needs them.

## Purpose

`desktop_app_source_updater` is a standard-library-only updater for Python
desktop apps with a stable launcher and updateable source code beside it. It
applies custom GitHub Release zip assets before the downstream app imports.

This is for code-only updates. It is not an installer, dependency resolver, or
full packaged-app replacement mechanism.

## Runtime

Use Python 3.10 or newer. This shell may not have `python` on PATH; this known
working interpreter is fine for local checks:

```powershell
$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"
```

The package lives directly at `desktop_app_source_updater/`.

No runtime dependencies are configured beyond the Python standard library. Do
not add dependencies, formatters, linters, or pre-commit as drive-by churn.

## Common Commands

Run tests:

```powershell
& $py -m unittest discover -s tests
```

Run the current verification set:

```powershell
& $py -m unittest discover -s tests
& $py -m compileall -q desktop_app_source_updater
& $py -m desktop_app_source_updater.build_update_asset --help
```

There is no standalone desktop app in this repo. Manual testing happens by
wiring the package into a downstream app and building an update zip there.

## Runtime Contract

Public API is exported from `desktop_app_source_updater/__init__.py`;
implementation lives in `desktop_app_source_updater/core.py`.

Downstream launchers should:

1. Compute the app root.
2. Add the app root to `sys.path` if needed.
3. Call `run_startup_update(UpdateConfig(...))` before importing app runtime.
4. Display `format_update_message(result)` when it returns text.
5. Import and launch normally.

The updater must:

- apply only manifest-listed files under `allowed_payload_paths`
- block dependency, packaging, build, cache, archive, and local-data paths
- verify installed files against manifest baseline hashes
- support jump-ahead updates with `previous_sha256_by_version`
- skip or block rather than overwrite unknown local edits
- keep downstream paths and environment variable names configurable

## Builder Contract

The builder lives in `desktop_app_source_updater/build_update_asset.py` and runs as:

```powershell
python -m desktop_app_source_updater.build_update_asset
```

Run it from a downstream app repo. It reads Git refs, accepts repeated
`--from-ref` values, writes a source-update zip, and refuses source-only assets
when dependency, packaging, build, cache, archive, local-data, deletion, rename,
or complex runtime changes require a packaged refresh.

## Docs Map

- `project_overview.md`: active file map and mental model
- `next_steps.md`: current adoption follow-ups
- `work_log.md`: newest session notes and verification breadcrumbs
- `README.md`: user-facing usage and release asset format
- `pyproject.toml`: package metadata and console script
- `tests/`: runtime and builder behavior coverage

Update `work_log.md` after substantive work unless the user asks not to. Update
`next_steps.md` when concrete future work changes.

## Git

This checkout may report dubious ownership. For read-only checks, prefer:

```powershell
git -c safe.directory=C:/path/to/this/repo status --short --branch
```

Only add a global safe-directory entry if the user explicitly asks.

## Reminders

- Keep source updates conservative and code-only.
- Preserve local-edit protection through known baseline hashes.
- Preserve multi-version jump-ahead support.
- `fp_analysis` is the prototype source, not a hard-coded target.
