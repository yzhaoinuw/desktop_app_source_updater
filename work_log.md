# Work Log

Prepend new session notes to the top of this file.

Rotation policy: the live log holds at most the **5 most recent unique calendar dates**. When a new date would push the file past 5 unique dates, move the oldest 5 dates as a chunk into a new file at `work_log_archive/work_log_<earliest>_to_<latest>.md`. The live file always holds at most 5 unique dates; each archive file always holds exactly 5.

If today's date already has a `## YYYY-MM-DD` header at the top, add a new `###` session subsection under it rather than starting a second `## YYYY-MM-DD` header for the same date.

Update this log at the end of any substantive work session unless the user explicitly asks not to document it. Substantive work includes file edits, meaningful validation or debugging, technical decisions or reversals, reusable discoveries, branch/PR/release state changes, or follow-up work that future agents need. Log useful experiments even when the code was reverted; skip casual Q&A, trivial one-off commands, and pure scratch work with no future coordination value.

## 2026-08-05

### Prepared the 0.3.0 PyPI release and made the README findable (claude-opus-5, default mode)

- **Executed both threads handed off earlier today.** Everything in the repo is
  done; the upload is blocked only on the maintainer creating a PyPI account.
  The maintainer chose 0.3.0 over republishing 0.2.0, and chose to stop before
  any upload.
- **Merged `dev` into `main`** (`8f0a106`, the How This Compares section). The
  branch had been waiting since 2026-08-03; the README becomes the PyPI project
  page, so it had to land first.
- **Bumped to 0.3.0** in `pyproject.toml` and `CITATION.cff` (`version` and
  `date-released`). Version lives in exactly those two files — nothing in the
  package declares `__version__`, so `importlib.metadata` is the only runtime
  source.
- **Added the package-page metadata**: `[project.urls]` with Homepage,
  Repository, Documentation, and Issues; `keywords` matching the GitHub topics;
  and classifiers for development status, audience, OS, topic, and Python 3.13.
- **Modernized the license metadata to PEP 639.** `license = { text = "MIT" }`
  and the `License :: OSI Approved :: MIT License` classifier are both
  deprecated, and setuptools warned about them four times per build; the table
  form is slated for removal in February 2027. Replaced with
  `license = "MIT"` plus `license-files = ["LICENSE"]`, which needed
  `setuptools>=77` in `[build-system]` (was `>=68`). The wheel now carries
  `License-Expression: MIT` and bundles `LICENSE` under `dist-info/licenses/`.
  Doing this before the first upload matters because a PyPI version can never
  be re-uploaded.
- **Fixed two relative README links** (`CITATION.cff`, `LICENSE`) that would
  have 404'd on PyPI, where relative links resolve against PyPI rather than
  GitHub. Rendered the README through PyPI's own `readme_renderer` to confirm
  the rest: all 22 in-page anchors resolve, because the renderer prefixes both
  heading ids and body hrefs with `user-content-` consistently, and both badges
  survive its HTML sanitization. Preview written to the session scratchpad, not
  committed.
- **Rewrote Installation** to lead with `pip install desktop-app-source-updater`
  and recommend an exact `==0.3.0` pin, since `UpdateConfig`'s field order is a
  public contract and a launcher frozen into a packaged app cannot be corrected
  after the fact. Kept the `git+https://` form as the commit/tag-pinning
  fallback. The Agent Adoption Prompt now hands adopters the version pin.
- **Made the README findable.** It previously contained neither "PyInstaller"
  nor "frozen" anywhere. Added a second opening paragraph naming PyInstaller as
  the case this was built for without implying a dependency, and a Common
  Questions section with three question-shaped headings, each linking into the
  section that answers it.
- **Added a PyPI release recipe to `AGENTS.md`** under Git and Releases, and
  corrected the field-order note to say adopters pin by version *or* commit.
- Confirmed the name is still unclaimed on both indexes. Note for whoever
  checks next: `curl` against `pypi.org/project/<name>/` now returns **200 with
  a bot-challenge page**, not 404, so it no longer distinguishes taken from
  free. Use the JSON API — `pypi.org/pypi/<name>/json` returns
  `{"message": "Not Found"}` — which is what confirmed both PyPI and TestPyPI.
- Verification:
  - Run on macOS with miniconda Python 3.13.11; `build` and `twine` were
    installed into a scratchpad venv rather than the conda base.
  - `python -m build`: clean, zero warnings after the PEP 639 change.
  - `twine check --strict dist/*`: PASSED for both the wheel and the sdist.
  - Wheel installed into a fresh venv: `desktop-app-source-update-asset` is on
    the path and `--help` runs; `importlib.metadata.version` reports `0.3.0`;
    all 11 public names still export.
  - `python -m unittest discover -s tests`: 41 tests, OK.
  - `python -m compileall -q desktop_app_source_updater`: passed.
  - `python -m desktop_app_source_updater.build_update_asset --help`: passed.
  - README link audit: 2 relative links found and fixed, 22/22 anchors resolve.

### Handed off two threads: PyPI publishing and README findability (claude-fable-5)

- **No code changed in this session.** The work was done in `project_ideas`,
  which plans the promotion of this repo; this entry exists so the next session
  here knows why two new threads appeared in `next_steps.md` and what decided
  them.
- **The maintainer decided to publish this package to PyPI**, settling the
  distribution question that `Distribution And Release Polish` had left open
  and moving it ahead of the rest of the promotion work. The argument: this
  package's audience arrives by asking a question, and increasingly asks an AI
  assistant rather than a search engine. What an assistant fetches while
  answering is ordinary web search one step removed, so the goal is to exist on
  the pages such a search returns — and when the answer to a question is "use
  this library," a package page is what both a person and an assistant look
  for. `pip install desktop-app-source-updater` is also an instruction an
  assistant can repeat, where "clone this repo" is not. The name was free on
  PyPI as of 2026-08-05.
- **Found that the README on `main` never uses the word "PyInstaller," or
  "frozen," anywhere.** The GitHub description does, and the unmerged `dev`
  section mentions it twice, but the page itself does not. That is the most
  likely word in the question a person types when they need this package, and
  both search engines and AI assistants match the wording of a question against
  the text of a page. Recorded as its own thread rather than folded into the
  PyPI one, because it is free and it improves everything that links here.
- **Flagged `origin/dev` as still unmerged.** One commit
  (`8f0a106 Add a How This Compares section to the README`), waiting since
  2026-08-03 for the maintainer to look at the rendered page; nothing else
  differs from `main`. It should land before a PyPI upload, since the README
  becomes the project page there.
- Deliberately **not** handed off: the Reddit and blog-article ideas from the
  same plan. The maintainer put them on hold to keep the next session's scope
  to publishing and the README.
- Verification:
  - `git log origin/main..origin/dev` — one commit, `8f0a106`.
  - Case-insensitive grep for "pyinstaller" and "frozen" in `main`'s
    `README.md` — zero hits each.
  - `pypi.org` returns 404 for both `desktop-app-source-updater` and
    `desktop_app_source_updater`, so the name is unclaimed.
  - `treaty validate .` — green.

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
