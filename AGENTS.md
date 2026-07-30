# Guidelines and Tips for Agents

Read this file first when joining the repo. Open the linked docs only when the
task needs them. Keep this file lean; put detailed guidance in the linked docs.

## Purpose

`desktop_app_source_updater` is a standard-library-only updater for Python
desktop apps. A stable launcher applies code-only GitHub Release zip assets
before importing the updateable application source beside it.

It is not an installer, dependency resolver, or packaged-app replacement.

## Runtime and Verification

Use Python 3.10 or newer. This interpreter is known to work locally:

```powershell
$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"
```

The package lives at `desktop_app_source_updater/`. Run:

```powershell
& $py -m unittest discover -s tests
& $py -m compileall -q desktop_app_source_updater
& $py -m desktop_app_source_updater.build_update_asset --help
```

## Contracts

Public API is exported from `desktop_app_source_updater/__init__.py`; the
implementation is in `core.py`. Launchers call
`run_startup_update(UpdateConfig(...))` before importing app runtime, display
`format_update_message(result)` when nonempty, then launch normally.

The updater must:

- apply only manifest-listed files under `allowed_payload_paths`
- block dependency, packaging, build, cache, archive, and local-data paths
- verify baseline hashes and preserve unknown local edits
- support jump-ahead updates through `previous_sha256_by_version`
- apply ordinary payload files atomically only when every listed baseline
  matches; unlisted source files remain untouched
- support one explicitly declared schema-2 Python config merge file while
  preserving only allowlisted literal assignments

The builder in `build_update_asset.py` accepts repeated `--from-ref` values
and refuses source-only assets when changes require a packaged refresh.

`UpdateConfig`'s field order is part of the public surface. Adopters pin this
package by commit and construct the config in a launcher that ships frozen
inside a packaged app, so inserting a field renumbers every positional
parameter after it and a positional caller misbinds silently instead of
failing. Append new fields after the existing ones and keep a default on every
field after `app_name` and `app_root`; `TestConfigCompatibility` enforces both.

## Docs and Session Hygiene

- `project_overview.md`: active file map and mental model
- `next_steps.md`: current adoption follow-ups
- `work_log.md`: recent work and verification
- `work_log_archive/`: older work-log entries, grouped in five-date chunks
- `README.md`: adoption, usage, and release asset format

Update `work_log.md` after substantive work: file edits, meaningful validation
or debugging, technical decisions, branch/release changes, or reusable findings.
Include model/mode metadata when available and the exact verification commands
run. Update `next_steps.md` when future work changes; skip both for trivial
exchanges or when the user asks to keep work off the record.

Keep at most five unique dates in the live work log. Before adding a dated entry,
run `Get-Date -Format yyyy-MM-dd`; never write a future date. `treaty validate`
enforces this.

Keep the tri-color treaty badge for GitHub; use shields.io only where raw SVG is
blocked.

## Git and Releases

For read-only Git checks, use a per-command `safe.directory` override; change
global config only when asked.

Before leaving a feature branch, confirm its changes are committed, verified,
and merged or intentionally parked. Treat commit-plus-push-plus-tag requests as
releases: update version/docs/work log, run verification, create the tag only
after those gates pass, and confirm published branch and tag refs.

## Updating the Treaty

Only pull upstream treaty changes when the maintainer asks.

- Start from a clean, git-tracked tree and use a dedicated branch.
- Run `treaty update --dry-run`, then `treaty update`.
- Treat the update as a three-way merge. Check `git status` and the unmerged
  index even if the command reports success.
- Resolve conflict markers by preserving repo-specific guidance and folding in
  relevant upstream rules; stage each resolved file.
- Review the final diff, run `treaty validate .` and the package verification
  commands above, and do not commit unresolved markers.

## Commit Messages

Use a short title. If one commit contains multiple user-requested changes, add
flat bullets describing user-visible behavior rather than tests, docs, or
behind-the-scenes implementation details.

## Reminders

- Keep source updates conservative and code-only.
- Preserve local-edit and jump-ahead protections.
- Keep downstream paths and environment variables configurable.
- `fp_analysis` is a prototype source, not a hard-coded target.
