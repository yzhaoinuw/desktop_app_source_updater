# Work Log

Prepend new session notes to the top of this file.

Rotation policy: the live log holds at most the **5 most recent unique calendar dates**. When a new date would push the file past 5 unique dates, move the oldest 5 dates as a chunk into a new file at `work_log_archive/work_log_<earliest>_to_<latest>.md`. The live file always holds at most 5 unique dates; each archive file always holds exactly 5.

If today's date already has a `## YYYY-MM-DD` header at the top, add a new `###` session subsection under it rather than starting a second `## YYYY-MM-DD` header for the same date.

Update this log at the end of any substantive work session unless the user explicitly asks not to document it. Substantive work includes file edits, meaningful validation or debugging, technical decisions or reversals, reusable discoveries, branch/PR/release state changes, or follow-up work that future agents need. Log useful experiments even when the code was reverted; skip casual Q&A, trivial one-off commands, and pure scratch work with no future coordination value.

## 2026-08-06

### Groundwork and design for a self-updating updater (claude-opus-5, default mode)

Maintainer's question: the updater ships as a frozen dependency inside the
adopting app, so an updater fix needs a full packaged release — can it update
itself? Yes. The enabler is that this package is pure Python, stdlib-only, with
no compiled parts, so nothing forces it to live inside the bundle. Decided in
favor, **deliberately did not start it**, and landed only the two pieces that pay
off regardless of when it happens.

- **`.py` payloads are now parsed before anything is written**
  (`_validate_python_payload` in `core.py`, called from
  `_prepare_update_payloads`). An asset carrying a syntax error fails the whole
  update with every installed file untouched. The reason this is worth its own
  check: a file with a syntax error still matches its manifest hash, so a broken
  installation looks pristine to the next update and only fails at import time.
  - Parses raw bytes, not decoded text, so a PEP 263 encoding declaration is
    honored the way the interpreter will honor it — decoding as UTF-8 first would
    reject a legitimate latin-1 payload. There is a test for that case.
  - Catches `ValueError`, `RecursionError`, and `MemoryError` alongside
    `SyntaxError`. Null bytes raise `ValueError`, not `SyntaxError`, and
    `run_startup_update` converts only `UpdateError` into a result — anything
    else would crash the launcher on the startup path. `python_config.py:255`
    already had this defensive shape; followed it.
  - The `python-config-merge` path already compiled its merged output, so this
    closes the gap for ordinary replace-strategy files.
- **`TestSelfUpdateSafetyContract` pins the no-deferred-imports contract.** Self
  replacement is safe only because the runtime modules are fully loaded before
  the apply path runs: the old code finishes from memory, the new code takes
  effect next launch. A function-level import inside the apply path would execute
  *after* the files on disk had been replaced, loading new code into a process
  running old code — intermittently, depending on which files a release touched.
  Checks `__init__.py`, `core.py`, `python_config.py`; excludes
  `build_update_asset.py`, which is a maintainer-side CLI that never runs in an
  installed app. Also rejects `__import__` and `importlib.import_module`, which
  defer a load the same way and are invisible to the import-statement check.
- **Design written up in `README.md` → "Updating the Updater Itself"**, marked
  explicitly as a design rather than a shipped pattern. Four considerations, of
  which the first is the one most likely to be missed: **a frozen copy silently
  shadows the vendored source copy**, because PyInstaller puts its importer into
  `sys.meta_path` ahead of the ordinary path finder. Getting that wrong
  reproduces the exact bug the change is meant to remove, and it looks like it
  works. The other three: the one-launch-behind property, the standing risk of
  breaking the update channel, and that an updater upgrade must never ride in the
  same asset as a manifest schema bump.
- **New `next_steps.md` thread, gated.** Do not start until `fp_analysis` has
  applied its first real source update in the field — the definition of done is
  two apps applying a code-only update and only one has. Then fold it into the
  full packaged release that the pin reconciliation and the schema-2 baseline
  already require, since all three want the same release.
- Judgment recorded for whoever picks this up: the case rests partly on the
  updater's low churn (no code changed between 0.2.0 and 0.3.0), but this package
  is a month old with both adoptions still in trial, so it is likely in its
  highest-churn period. That raises both the value and the risk. Not a reason to
  abandon the plan; a reason to re-check it when the gate opens.
- **Added `__version__` to the package**, found while walking the maintainer
  through what vendoring would look like in `sleep_scoring`. The package had no
  version marker anywhere in its source — the version lived only in
  `pyproject.toml:7`, which is a blocked path name and would not be vendored, so
  a vendored updater would have been completely unidentifiable in the field. On
  the critical path for the design and invisible until a bug report arrives.
  - `pyproject.toml` stays the static packaging source of truth rather than
    becoming `dynamic`, because `release.yml:22` reads it with `tomllib` to
    refuse a mismatched tag. Making it dynamic would have broken that check on a
    branch that is out for review.
  - `TestVersionConsistency` ties `__version__`, `pyproject.toml`, and
    `CITATION.cff` together, since AGENTS.md already requires updating the last
    two on release and this adds a third hand-edited copy of one string. Uses
    `tomllib` with a regex fallback: CI runs 3.10, which has no `tomllib`.
  - Verified by mutation: setting `__version__ = "9.9.9"` fails the test, then
    restored.
  - **Trap for anyone repeating that mutation check:** the restore appeared to
    fail, because `"9.9.9"` and `"0.3.0"` are the same byte length and the
    restore landed in the same second as the mutation, so the `.pyc`'s
    `(mtime, size)` invalidation key still matched and Python reused the stale
    9.9.9 module. The source file was correct the whole time. Run mutation
    checks with `python3 -B`, or clear `__pycache__` before re-verifying.
    This does **not** affect real updates: `os.replace` gives the applied file
    an mtime of now, while the file it replaces was written at install time, so
    the key differs. It only bites same-size edits seconds apart.
- Reusable point: grounding the design question in the actual adopter was worth
  more than reasoning about it abstractly. `sleep_scoring`'s spec already keeps
  `app_src` out of the bundle by filtering `a.pure`/`a.scripts`
  (`packaging/windows/app.spec:47-49`), so the "keep the updater unfrozen"
  mechanism is a proven in-repo pattern rather than something new — and
  `app.spec:36` currently forces the updater *into* the bundle via
  `hiddenimports`, which is exactly the shadowing hazard the README warns about.
  Its launcher also already wraps the updater import in `try/except ImportError`
  and continues startup, which is half of the recovery floor the design calls
  for. None of that was visible from this repo alone.
- Verification (macOS, `python3` 3.13):
  - `python3 -m unittest discover -s tests`: 49 tests, OK (was 41).
  - `python3 -m compileall -q desktop_app_source_updater`: clean.
  - Mutation check on the contract test: injected `import base64` into
    `_sha256_bytes` in `core.py`, confirmed
    `test_runtime_modules_have_no_deferred_imports` failed with `core.py:1111`,
    then restored the file from a scratchpad copy and confirmed the suite passes
    and the mutation is gone. A contract test that cannot fail is not a contract.

## 2026-08-05

### Wired Trusted Publishing and corrected a claim about the pins (claude-opus-5, default mode)

- **Added `.github/workflows/release.yml`.** Builds on a `v*` tag push, refuses
  to continue when the tag and `pyproject.toml` version disagree, and publishes
  via `pypa/gh-action-pypi-publish` with `id-token: write` — an OIDC token, no
  stored secret. `workflow_dispatch` builds and checks without uploading, since
  `publish` is gated on `startsWith(github.ref, 'refs/tags/v')`. Dry run
  `gh run 31063742071`: `build` success, `publish` correctly skipped.
- **Still needs the maintainer's one-time PyPI entry** at the project's
  publishing settings: owner `yzhaoinuw`, repo `desktop_app_source_updater`,
  workflow `release.yml`, environment `pypi`. Because the project already exists
  on PyPI this is a normal trusted publisher, not a "pending" one, and the
  environment name must match the workflow exactly.
- **Corrected an inaccurate claim I had put in `next_steps.md` earlier today.**
  I wrote that `sleep_scoring`'s `@main` pin was "exactly what the `UpdateConfig`
  field-order contract warns against, since a positional caller misbinds
  silently." That is wrong for both current adopters: `sleep_scoring`
  (`run_desktop_app.py:132`) and `fp_analysis` (`startup_update_config.py`) each
  construct `UpdateConfig` entirely with keyword arguments, so inserting a field
  would not misbind for them. The pin problem is real but it is about
  **reproducibility**, not misbinding — a package built from `@main` carries no
  record of which updater it froze, and since launcher and updater both live
  inside the frozen bundle, a wrong one needs a full packaged release to fix
  rather than a source update. Rewrote the bullet accordingly.
- Reusable point for future sessions: the field-order contract in `AGENTS.md` is
  a guard against a hazard no adopter is currently exposed to. That does not make
  it pointless — it is what keeps keyword-only usage from being accidental — but
  do not cite it as an active risk without checking how the adopter actually
  constructs the config.
- Verification:
  - `yaml.safe_load` on `release.yml` before pushing; confirmed the publish gate,
    `id-token: write`, and `environment: pypi`.
  - `gh run view 31063742071`: build success, publish skipped, as designed.
  - `grep -A 20 "UpdateConfig("` in both adopting repos: all keyword arguments.
  - `treaty validate .`: passed.

### Added CI and corrected a stale downstream thread (claude-opus-5, default mode)

- **Added `.github/workflows/tests.yml`** — the repo's first CI. Runs the suite
  on Linux, Windows, and macOS across Python 3.10–3.13, plus a `build` and
  `twine check --strict` job. All 12 matrix jobs and the package job passed on
  the first run (`gh run 31063168274`).
- **Why this and not the Trusted Publishing workflow first:** `pyproject.toml`
  advertises four Python versions and `Operating System :: OS Independent` on a
  now-public PyPI page, and nothing verified any of it — this package had only
  ever run on 3.13 here and one Windows conda env, and **Linux had never run the
  tests at all**. The OS classifier was one I added during the 0.3.0 prep, so it
  was an assertion made on the maintainer's behalf. CI turns it into a fact.
  Trusted Publishing saves a few minutes a few times a year; it is convenience,
  not correctness. It is also easier to add now that a workflow directory exists.
- The code turned out to be portable by construction — `os.replace`, explicit
  `utf-8` on every read, backslash normalization for path comparison, and no
  `sys.platform` branches anywhere — which is why the matrix went green with no
  fixes.
- **Corrected the Downstream Adoption Validation thread, which was materially
  wrong on `main`.** It listed "wire the updater into the `fp_analysis` launcher"
  as remaining work; that landed in `fp_analysis` on 2026-07-24 (`f4803dd`), and
  the durable-check adoption on 2026-07-28 (`2d7e640`) — the *same day* as this
  repo's last edit to that thread (`22475b7`). The bullet that commit *added*
  about `check_state_file`, `latest_release_url`, and `force_check` was already
  satisfied in `fp_analysis` on the day it was written.
- **Root cause, and the fix applied:** this repo was duplicating a checklist that
  the adopting repos already maintain. Both `sleep_scoring` and `fp_analysis`
  have their own `next_steps.md` — `fp_analysis`'s is accurate and even has a
  "First Source-Update Release Trial" thread covering the real remaining step.
  The thread here now records only updater-level facts and links out to each
  app's own checklist. One source of truth per fact.
- **Verified field evidence directly from published releases rather than from
  this repo's notes.** `sleep_scoring` v0.16.8 carries a real
  `sleep_scoring_app_update_v0.16.8.zip`, so its apply path is genuinely proven.
  `fp_analysis` is fully integrated with its v0.6.0 baseline shipped, but every
  one of its releases carries only a ~117 MB `*_full.zip` — nothing matching its
  own `fp_analysis_app_update_` prefix, so it has never applied one. Definition
  of done is one of two apps, not two.
- **Found drifted and inconsistent downstream pins.** `sleep_scoring` pins two
  different things: `pyproject.toml` uses `@main` — a moving target that now
  resolves to 0.3.0 and will keep moving — while `requirements.txt` pins
  `5eab40b`. `fp_analysis` pins `85bb68e`. A moving `@main` reference is exactly
  what the `UpdateConfig` field-order contract warns against, since a positional
  caller misbinds silently instead of failing. Recorded as the top remaining item.
- Verification:
  - `gh run view 31063168274`: 12/12 matrix jobs plus `package`, all success.
  - Workflow YAML parsed with `yaml.safe_load` before pushing; grepped for
    3.11+/3.12+-only constructs (`tomllib`, `typing.Self`, `ExceptionGroup`,
    PEP 695 generics) — none present, so the 3.10 floor is real.
  - Adoption claims checked against `gh release view` asset lists in both
    adopting repos, and against `origin/main` in `fp_analysis` rather than the
    local checkout, which was 3 commits behind.
  - `treaty validate .`: passed.

### Published 0.3.0 to PyPI, tagged, and released (claude-opus-5, default mode)

- **The package is on PyPI**:
  <https://pypi.org/project/desktop-app-source-updater/>. `v0.3.0` is tagged at
  `25836b2`, the GitHub Release is published, and Zenodo archived it as record
  `21815913`; the concept DOI `10.5281/zenodo.21763329` now resolves to it. The
  `Publish to PyPI` thread in `next_steps.md` is closed and removed.
- Sequence used: TestPyPI dry run
  (<https://test.pypi.org/project/desktop-app-source-updater/>), then tag and
  GitHub Release, then PyPI. Tagging before the PyPI upload was deliberate — the
  README's own `git+...@v0.3.0` install example is part of the PyPI project page,
  so publishing first would have shipped a page containing a command that
  errored. Building from the tagged tree also guarantees the uploaded sdist
  matches `v0.3.0` exactly.
- Verified from PyPI after upload: clean-venv `pip install` reports `0.3.0` with
  no dependencies, `desktop-app-source-update-asset` is on the path and runs, and
  the JSON API shows all four project URLs, 5 keywords, 10 classifiers,
  `License-Expression: MIT`, and a 16 KB `text/markdown` description.
- **Zero code changed between v0.2.0 and v0.3.0.** `desktop_app_source_updater/`
  does not appear in `git diff v0.2.0..HEAD` at all — this release is packaging
  metadata and documentation only, so downstream apps pinned to 0.2.0 can move
  up with no behavioral risk and no `UpdateConfig` field-order concern.
- **Self-inflicted 403 worth not repeating: never write a `~/.pypirc` with
  placeholder credentials.** I created one to save the maintainer a step, and
  twine reads that file *instead of* prompting — so it sent the literal string
  `PASTE_YOUR_TESTPYPI_TOKEN_HERE` as the token and TestPyPI returned 403
  Forbidden with no prompt shown. Deleting the file fixed it immediately. An
  absent `.pypirc` is strictly better than a stubbed one, because twine falls
  back to an interactive prompt.
- **Credentialed uploads cannot run through Claude Code's `!` prefix.** There is
  no TTY, so `getpass` raises `EOFError` and twine dies before uploading. They
  have to run in a real terminal. This cost a round trip before the `.pypirc`
  problem was even visible.
- **Dropped, then reinstated, the TestPyPI step.** After the 403 I proposed
  skipping TestPyPI to halve the account setup; the maintainer clarified the
  objection was to the broken instructions, not the step. TestPyPI did its job —
  it confirmed the project page renders correctly before anything irreversible
  reached PyPI.
- **Condensed the README opening from two paragraphs to one** at the
  maintainer's request, 85 words to 60. Kept every term the page needs to be
  found for — PyInstaller (twice, deliberately), frozen, GitHub Release,
  packaged, launcher — and folded the pain into the first sentence rather than
  giving it a paragraph. Cut the sentence about verifying and atomically
  replacing files; that claim now lives only in `## Update Scope and Safety` and
  the trust-model question, not in the search snippet.
- Consequence noted at the time: the TestPyPI page is one paragraph behind what
  will go to PyPI, and neither index accepts a re-upload of an existing version.
  Not worth a version bump, since the rendering pipeline was already validated.
- Verification:
  - `twine upload --repository testpypi dist/*`: succeeded from a real terminal.
  - `python -m build`: 0 warnings. `twine check --strict dist/*`: PASSED both.
  - README re-rendered through PyPI's `readme_renderer` after the opening
    rewrite: renders, 0 broken anchors.
  - `treaty validate .`: passed.
  - `git diff v0.2.0..HEAD --stat`: no files under `desktop_app_source_updater/`.

### Restructured the README around the adoption path (claude-opus-5, default mode)

- **Maintainer's read of the pushed README: it felt unfocused**, despite the
  Content Overview. Three specific objections, all acted on.
- **Moved Common Questions and How This Compares below Usage.** They had been
  sitting between the opening and Installation, breaking the path a new reader
  wants — install, wire it up, see it working. Position costs almost nothing for
  search: what gets matched is heading text and body text, and the snippet comes
  from the opening paragraph, where PyInstaller already appears. The page now
  reads Installation → Usage → Real-World Examples → Common Questions.
- **Folded How This Compares into Common Questions** as a fourth question,
  "How does this compare to PyUpdater and tufup?", which is closer to how people
  actually ask it and removes a second adjacent section.
- **Grouped the look-it-up material under a single `## Reference`** with six
  subsections: Release Checks, Multiple Installed Baselines, User-Editable
  Python Configuration, Verifying an Integration (was Test an Integration),
  Troubleshooting, Development. Top-level sections went from 17 to 13.
- **Kept Update Scope and Safety in the main flow** rather than moving it into
  Reference. It is not look-it-up material — it is what tells an adopter their
  change *cannot* ship as a source update, and burying it would make the package
  look more capable than it is. The maintainer agreed when this was raised.
- **Cut the agent adoption prompt from 21 lines to 7** and renamed the section
  to Adopting This in an App. The maintainer's point: a capable agent works out
  the install and integration from a short instruction, so enumerating every
  `UpdateConfig` field and every verification step in the prompt was wasted
  text. It now states the two things an agent cannot infer — pin the dependency,
  and call `run_startup_update` before the app's own source is imported.
- **Redundancy pass** over the rest: merged the two dependency-file code blocks
  into one commented block, collapsed the asset-filename explanation from two
  code blocks plus two paragraphs into one paragraph, folded the
  `check_state_file` path rule into its table row, and dropped the numbered
  restatement of what the Usage example already shows. Prose dropped 7% (1913 to
  1782 words excluding code blocks) with no content removed.
- Content Overview now lists all 12 sections with a one-line gloss on what is
  inside Reference, rather than 15 flat entries.
- Verification:
  - README audit script: 0 relative links, 14/14 in-page anchors resolve, every
    `##` section present in Content Overview.
  - Re-rendered through PyPI's `readme_renderer`: renders, zero broken anchors.
  - `python -m build`: 0 warnings. `twine check --strict dist/*`: PASSED both.
  - `treaty validate .`: passed. `git diff --check`: passed.

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
