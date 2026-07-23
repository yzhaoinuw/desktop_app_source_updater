# Work Log

Prepend new session notes to the top of this file.

Rotation policy: the live log holds at most the **5 most recent unique calendar dates**. When a new date would push the file past 5 unique dates, move the oldest 5 dates as a chunk into a new file at `work_log_archive/work_log_<earliest>_to_<latest>.md`. The live file always holds at most 5 unique dates; each archive file always holds exactly 5.

If today's date already has a `## YYYY-MM-DD` header at the top, add a new `###` session subsection under it rather than starting a second `## YYYY-MM-DD` header for the same date.

Update this log at the end of any substantive work session unless the user explicitly asks not to document it. Substantive work includes file edits, meaningful validation or debugging, technical decisions or reversals, reusable discoveries, branch/PR/release state changes, or follow-up work that future agents need. Log useful experiments even when the code was reverted; skip casual Q&A, trivial one-off commands, and pure scratch work with no future coordination value.

## 2026-07-22

### Added schema-2 semantic Python config merging (Codex GPT-5, default mode)

- Added a schema-2 manifest contract that marks exactly one Python config file
  for semantic merging and explicitly allowlists its user-editable assignments;
  schema 1 remains replacement-only and rejects strategy metadata.
- Added a stdlib-only AST merge engine that starts from downloaded source,
  preserves installed literal values through source-span replacement, merges
  dictionaries recursively, and retains downloaded code, comments, ordering,
  defaults, and removals.
- Prepared and compiled merged bytes before mutation, kept ordinary payload
  files on the existing whole-file baseline checks, and integrated final bytes
  with the existing all-or-nothing backup and rollback transaction.
- Added builder flags `--python-config-merge` and repeatable
  `--editable-assignment`, including downloaded-template validation and
  automatic schema-2 asset emission.
- Documented why an unknown edit to any ordinary bundled file skips the entire
  update, why unlisted files are untouched, and why downstream adoption needs
  a new full packaged release before schema-2 assets are safe.
- Delivery path is `feature/issue-2-python-config-merge` to `dev` to `main`,
  followed by closing GitHub issue #2 after both published refs are confirmed.
- Verification:
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m unittest discover -s tests -v`: 23 tests passed.
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m compileall -q desktop_app_source_updater`: passed.
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m desktop_app_source_updater.build_update_asset --help`: passed and listed the schema-2 config merge options.
  - `treaty validate .`: not run because the `treaty` command is unavailable
    in this shell.

### Added multiple installed byte baselines to the asset builder (Codex GPT-5, default mode)

- Added repeatable `--installed-baseline-manifest` inputs that describe exact
  installed SHA-256 or missing-file states for versions already declared by
  `--from-ref`.
- Kept `previous_sha256_by_version` for unambiguous per-version states and used
  the existing schema-1 `previous_sha256` list for deduplicated present-file
  alternatives such as canonical LF and packaged CRLF bytes.
- Made the builder refuse baseline combinations that need both missing-file
  handling and multiple present-file hashes because schema 1 cannot represent
  that combination safely.
- Added end-to-end regression coverage showing that both legitimate byte
  lineages update, an unknown local edit remains untouched, jump-ahead file
  additions keep version-aware `null` baselines, and the unrepresentable case
  fails closed.
- Updated the adoption guide, project overview, and active next-step record for
  GitHub issue #1 on `dev`.
- Verification:
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m unittest discover -s tests -v`: 10 tests passed.
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m compileall -q desktop_app_source_updater`: passed.
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m desktop_app_source_updater.build_update_asset --help`: passed and listed `--installed-baseline-manifest`.

## 2026-07-14

### Updated Agent Collab Treaty to v0.3.3 (Codex GPT-5, default mode)

- Updated the Copier treaty pin from `v0.3.2` to `v0.3.3` while preserving the
  enabled tri-color adoption badge.
- Resolved the expected whole-file `AGENTS.md` conflict, then condensed the
  project-specific guide from 133 to 73 lines while retaining the new release,
  workstation-date, and badge safeguards.
- Verification:
  - `treaty validate .`: passed.
  - `python -m unittest discover -s tests`: 8 tests passed.
  - `python -m compileall -q desktop_app_source_updater`: passed.
  - `python -m desktop_app_source_updater.build_update_asset --help`: passed.
  - `git diff --cached --check`: passed.

### Fixed GitHub release metadata requests (Codex GPT-5, default mode)

- Fixed startup update discovery to request GitHub release metadata as JSON
  while continuing to request update assets as binary content.
- Added regression coverage for both HTTP media types so a shared download
  helper cannot silently send an asset-only header to the metadata endpoint.
- The affected `sleep_scoring` v0.16.5 GitHub Release was revoked before the
  fix. Its replacement full package pinned this commit, passed the frozen
  executable's online metadata check from a fresh extraction, and was
  republished only after every remote asset digest matched the local files.
- Verification:
  - `python -m unittest discover -s tests`: 8 tests passed.
  - `python -m compileall -q desktop_app_source_updater`: passed.
  - `python -m desktop_app_source_updater.build_update_asset --help`: passed.
  - A real anonymous request to the `sleep_scoring` latest-release endpoint
    returned `up-to-date` instead of HTTP 415.
  - The final `sleep_scoring` package queried the republished public v0.16.5
    metadata and printed `no update available`.

## 2026-07-01

### Expanded README adoption guide (Codex GPT-5)

- Rewrote `README.md` to explain how human maintainers and agents adopt the updater in an existing app without cloning or vendoring it.
- Added GitHub dependency installation, launcher wiring, first-full-release rule, source-update asset publishing steps, test checklist, troubleshooting notes, and a pasteable agent prompt.
- Verification:
  - Inspected `README.md` content after rewrite.

### Added treaty adoption badge (Codex GPT-5)

- Added the centrally hosted tri-color Agent Collab Treaty adoption badge to the top of `README.md`.
- Verification:
  - Inspected `README.md` to confirm the badge markdown is present and points to the treaty repository.

### Configured GitHub origin for renamed project (Codex GPT-5)

- Added local `origin` remote for `https://github.com/yzhaoinuw/desktop_app_source_updater.git`.
- Re-verified the renamed package before publishing.
- Verification:
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m unittest discover -s tests` passed: 7 tests.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m compileall -q desktop_app_source_updater` passed.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m desktop_app_source_updater.build_update_asset --help` passed.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m pip wheel --no-build-isolation --no-deps --disable-pip-version-check --wheel-dir .wheelhouse .` passed; generated artifacts were removed afterward.

### Renamed project to desktop_app_source_updater (Codex GPT-5)

- Renamed the Python package/import surface from `desktop_source_updater` to `desktop_app_source_updater`.
- Updated the distribution name to `desktop-app-source-updater`, the console script to `desktop-app-source-update-asset`, and the runtime HTTP User-Agent to `desktop-app-source-updater`.
- Updated README usage, builder commands, agent guidance, project overview paths, and tests for the new name.
- Confirmed no Git remote is configured yet, so there is no GitHub remote URL or redirect migration to perform.
- Verification:
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m unittest discover -s tests` passed: 7 tests.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m compileall -q desktop_app_source_updater` passed.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m desktop_app_source_updater.build_update_asset --help` passed.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m pip wheel --no-build-isolation --no-deps --disable-pip-version-check --wheel-dir .wheelhouse .` passed; generated artifacts were removed afterward.

### Trimmed guidance and flattened package layout (Codex GPT-5)

- Trimmed `AGENTS.md` from the long treaty draft form to a 77-line project guide.
- Moved the package from `src/desktop_source_updater/` to root-level `desktop_source_updater/` and removed the empty `src/` wrapper.
- Updated setuptools discovery, subprocess test environment, README development commands, and project overview paths for the flat layout.
- Reusable discovery: `pyproject.toml` had a UTF-8 BOM that this environment's pip/TOML parser rejected during wheel metadata prep; rewriting it as plain UTF-8 fixed package builds.
- Verification:
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m unittest discover -s tests` passed: 7 tests.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m compileall -q desktop_source_updater` passed.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m desktop_source_updater.build_update_asset --help` passed.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; & $py -m pip wheel --no-build-isolation --no-deps --disable-pip-version-check --wheel-dir .wheelhouse .` passed; generated artifacts were removed afterward.

### Filled treaty docs from handoff draft (Codex GPT-5)

- Replaced generic treaty placeholders in `AGENTS.md`, `project_overview.md`, and `next_steps.md` with project-specific guidance from `AGENTS_draft.md` plus source/test inspection.
- Documented the standard-library-only runtime contract, release-asset builder contract, active file map, test fixtures, Git dubious-ownership workaround, and downstream adoption follow-up.
- Removed `AGENTS_draft.md` after absorbing its content into the live treaty docs.
- Reusable discovery: this shell has no `python`, `py`, `python3`, or `conda` launcher on PATH; `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe` is a working Python 3.10.19 interpreter for this repo. Also, `python -m unittest` discovered zero tests here, so use `unittest discover -s tests`; use `compileall -q` instead of `py_compile` with a wildcard on Windows.
- Verification:
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; $env:PYTHONPATH = "$PWD\src"; & $py -m unittest discover -s tests` passed: 7 tests.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; $env:PYTHONPATH = "$PWD\src"; & $py -m compileall -q src\desktop_source_updater` passed.
  - `$py = "C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe"; $env:PYTHONPATH = "$PWD\src"; & $py -m desktop_source_updater.build_update_asset --help` passed.

<!--
Each session entry follows this shape:

## YYYY-MM-DD

### Short title for what was done (model + version, effort/thinking mode, token budget if known)

- bullet describing what was added or changed
- another bullet — keep them high-level and user/agent-facing, not implementation play-by-play
- if relevant, intended profiling signal or measurement:
  - what to look for in logs / output
  - what numbers were observed
- Verification:
  - the exact command(s) that were actually run
  - what passed / what was confirmed

Model / effort / token info goes in the parentheses after the `###` title when available from the system. Use whatever the model or interface actually reports — do not estimate or hallucinate. Omit any field that the interface does not surface.

- **Model**: the version string the interface reports (e.g. `grok-4.3`, `gpt-4o`, `claude-opus-4-7`).
- **Effort / thinking mode**: the effort knob the interface reports (e.g. `high`, `low`, `extended thinking`). Omit if no such knob exists or its setting is not surfaced.
- **Token budget**: **output tokens for the session** (output + thinking/reasoning tokens for models that report them separately, e.g. Claude with extended thinking). This is the cleanest cross-agent proxy for "amount produced." Omit if the interface does not surface a count.

Purely human-driven work can use `(human)`. Mixed human + agent sessions can combine them, e.g. `(human + grok-4.3, high)`.

Keep the parenthetical compact. Examples:
- `(grok-4.3, high, ~18k out)`
- `(gpt-4o, high, ~22k out)`
- `(claude-opus-4-7, extended thinking, ~30k out)`
- `(grok-4.3, low)`

Newest entry goes on top. If the session did multiple distinct pieces of work, use multiple `###` subsections under one `##` date header.
-->
