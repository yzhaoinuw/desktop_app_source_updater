# Work Log

Prepend new session notes to the top of this file.

Rotation policy: the live log holds at most the **5 most recent unique calendar dates**. When a new date would push the file past 5 unique dates, move the oldest 5 dates as a chunk into a new file at `work_log_archive/work_log_<earliest>_to_<latest>.md`. The live file always holds at most 5 unique dates; each archive file always holds exactly 5.

If today's date already has a `## YYYY-MM-DD` header at the top, add a new `###` session subsection under it rather than starting a second `## YYYY-MM-DD` header for the same date.

Update this log at the end of any substantive work session unless the user explicitly asks not to document it. Substantive work includes file edits, meaningful validation or debugging, technical decisions or reversals, reusable discoveries, branch/PR/release state changes, or follow-up work that future agents need. Log useful experiments even when the code was reverted; skip casual Q&A, trivial one-off commands, and pure scratch work with no future coordination value.

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
