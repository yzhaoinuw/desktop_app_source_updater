# Work Log

Prepend new session notes to the top of this file.

Rotation policy: the live log holds at most the **5 most recent unique calendar dates**. When a new date would push the file past 5 unique dates, move the oldest 5 dates as a chunk into a new file at `work_log_archive/work_log_<earliest>_to_<latest>.md`. The live file always holds at most 5 unique dates; each archive file always holds exactly 5.

If today's date already has a `## YYYY-MM-DD` header at the top, add a new `###` session subsection under it rather than starting a second `## YYYY-MM-DD` header for the same date.

Update this log at the end of any substantive work session unless the user explicitly asks not to document it. Substantive work includes file edits, meaningful validation or debugging, technical decisions or reversals, reusable discoveries, branch/PR/release state changes, or follow-up work that future agents need. Log useful experiments even when the code was reverted; skip casual Q&A, trivial one-off commands, and pure scratch work with no future coordination value.

## 2026-08-01

### Added real-world adopter links to the README (Codex GPT-5, default mode)

- Added a dedicated README section linking to the `sleep_scoring` and
  `fp_analysis` repositories as maintained examples of launcher-based source
  updates.
- Described each app's actual updateable runtime path and kept the examples in
  the primary adoption flow immediately after Usage.
- Verification:
  - Confirmed both GitHub repository URLs from their local `origin` remotes.
  - Inspected both active launchers and the `fp_analysis` update configuration.
  - README contents-link check: all 11 links resolved and both adopter links
    were present.
  - `C:\Users\yzhao\python_projects\agent_collab_treaty\.venv\Scripts\treaty.exe validate .`: passed.
  - `git diff --check`: passed.

### Reorganized the README around adoption workflow (Codex GPT-5, default mode)

- Replaced the opening conceptual essays with a concise package description,
  linked content overview, installation instructions, and launcher-first usage
  example.
- Reorganized configuration, asset building, publishing, and integration tests
  into a direct adoption path; moved baseline variants, Python config merging,
  safety behavior, network checks, troubleshooting, and the agent prompt into
  clearly named later reference sections.
- Reduced the README from 442 to 369 lines while preserving the package's
  source-update and compatibility contracts.
- Rotated the previous five work-log dates into
  `work_log_archive/work_log_2026-07-01_to_2026-07-30.md`.
- Verification:
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m unittest discover -s tests -v`: 41 tests passed.
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m compileall -q desktop_app_source_updater`: passed.
  - `C:\Users\yzhao\miniconda3\envs\fp_analysis_dist\python.exe -m desktop_app_source_updater.build_update_asset --help`: passed.
  - README contents-link check: all 10 links resolved to section headings.
