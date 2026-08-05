# Next Steps

Use this checklist alongside `work_log.md`. Keep "Currently Hot" limited to
threads that are actually in flight or likely to be resumed soon.

## Currently Hot

- [Publish to PyPI](#publish-to-pypi-claude-fable-5): everything is built and
  verified; the upload itself is blocked on the maintainer's PyPI account.
- [Downstream adoption validation](#downstream-adoption-validation-codex-gpt-5):
  prove the updater in at least two real desktop apps before broad adoption.

## Publish To PyPI (claude-fable-5)

Status: **prepared 2026-08-05, blocked on the maintainer.** Everything in the
repository is done and verified; what remains needs a PyPI account, which only
the maintainer can create. Decided by the maintainer; the alternatives in
[Distribution And Release Polish](#distribution-and-release-polish) are settled
by this.

Why now, and why it is ahead of the other promotion work: this package's
audience mostly arrives by asking a question, and increasingly they ask an AI
assistant rather than a search engine. When the answer to a question is "use
this library," both people and assistants look for a package page, and
`pip install desktop-app-source-updater` is an instruction an assistant can
repeat in an answer, where "clone this GitHub repo" is not. A package page is
also indexed well and republished by aggregators, so one upload creates several
findable pages. The full reasoning is in `project_ideas`, in
`updater_and_cookbook_promotion_drafts.md`, section 3.

The name `desktop-app-source-updater` was free on PyPI as of 2026-08-05
(pypi.org returns 404 for both spellings). Re-check before assuming — names are
not reserved.

Done on 2026-08-05, on `main`:

- **Merged `dev`.** `8f0a106 Add a How This Compares section to the README` is
  on `main`; the branch is now fully merged.
- **Added the metadata a package page needs.** `[project.urls]` (Homepage,
  Repository, Documentation, Issues), `keywords` matching the GitHub topics,
  and classifiers for audience, OS, topic, and Python 3.13.
- **Bumped to `0.3.0`** in `pyproject.toml`, with `version` and
  `date-released` updated in `CITATION.cff`.
- **Modernized the license metadata to PEP 639** — `license = "MIT"` plus
  `license-files`, and dropped the deprecated
  `License :: OSI Approved :: MIT License` classifier. The old
  `license = { text = "MIT" }` table is deprecated and slated for removal in
  February 2027; setuptools warned about both forms on every build. Needed
  `setuptools>=77` in `[build-system]`. The build is now warning-free.
- **Fixed the two relative README links** (`CITATION.cff` and `LICENSE`) that
  would have 404'd on the PyPI page, since relative links there resolve against
  PyPI rather than GitHub. All 22 in-page anchors survive PyPI's renderer,
  which prefixes both heading ids and body hrefs with `user-content-`
  consistently. Both badges survive its HTML sanitization.
- **Rewrote the Installation section** to lead with
  `pip install desktop-app-source-updater`, keep the `git+https://` form as the
  commit/tag-pinning fallback, and recommend an exact `==0.3.0` pin because of
  the `UpdateConfig` field-order contract. The Agent Adoption Prompt now hands
  adopters the version pin instead of the Git reference.
- **Added a PyPI release recipe to `AGENTS.md`** under Git and Releases.
- **Closed the "Make the README findable" thread** in the same pass, since the
  README is the PyPI project page and the two threads touched the same file.
  The README on `main` previously never used the word "PyInstaller" or
  "frozen." It now names PyInstaller in the second paragraph as the case this
  was built for — while keeping the accurate general claim, because there is no
  PyInstaller dependency — and carries a Common Questions section answering
  "How do I update a PyInstaller app without rebuilding it?", "Can I keep my
  `.py` files outside the frozen bundle and update only those?", and "Do I need
  code signing or an update server?" Each answer links into the section that
  covers it, and the no-signing trade-off stays as prominent as before.

What is left, and why it is blocked: **the maintainer needs a PyPI account.**
Nothing else stands in the way — `python -m build` and
`twine check --strict dist/*` both pass, and installing the built wheel into a
clean venv puts `desktop-app-source-update-asset` on the path and reports
version `0.3.0`.

Once the account exists, issue an API token and run, from a clean tree:

```powershell
python -m build
python -m twine check --strict dist/*
python -m twine upload --repository testpypi dist/*   # optional dry run
python -m twine upload dist/*
```

Trusted Publishing is the better long-term answer but needs a GitHub Actions
workflow to exist, and this project has none yet; see
[Distribution And Release Polish](#distribution-and-release-polish).

Then finish the release: tag `v0.3.0` and cut the matching GitHub Release so
Zenodo archives it and the concept DOI stays in step.

Definition of done:

- `pip install desktop-app-source-updater` works from a clean environment.
- The PyPI page shows the README with working links and a sidebar pointing at
  the repository and issues.
- The `v0.3.0` tag and GitHub Release exist and Zenodo has picked them up.

## Downstream Adoption Validation (Codex GPT-5)

Status: in progress

The package now has successful field evidence in one real desktop app:
`sleep_scoring` has applied lightweight source updates through v0.16.8. A
second adopting app is still needed before broad adoption; the next target is
`C:\Users\yzhao\python_projects\fp_analysis`, where the prototype originated.

Remaining work:

- Wire the updater into the `fp_analysis` desktop launcher with app-specific
  `UpdateConfig` values.
- Build a source update asset from real `fp_analysis` Git refs using repeated
  `--from-ref` values when appropriate.
- Verify that startup update behavior works for a clean compatible install, a
  skipped-release jump, and a local-edit mismatch.
- Pin the immutable updater 0.2.0 commit in each app's next full package, supply
  an app-specific per-user `check_state_file`, migrate normal discovery to
  `latest_release_url`, and wire explicit/package-gate checks with
  `force_check=True`.
- Pin a schema-2-compatible updater revision into a new full downstream package
  before testing Python config merge assets; existing frozen runtimes cannot
  acquire this feature through source-only updates.
- Record any app-specific environment variable names, launcher pattern changes,
  or README clarifications discovered during adoption.

Definition of done:

- Two downstream apps can apply code-only source updates without Git installed
  on the user machine.
- Dependency, packaging, local-data, deletion, and rename cases are confirmed to
  block or require packaged refreshes as intended.
- Any lessons from downstream adoption are reflected in `README.md`,
  `AGENTS.md`, and tests where useful.

## Background / Paused

### Distribution And Release Polish

Status: the distribution question is settled; the tooling question is still
paused.

The distribution half of this thread — Git installs, release assets, or a
package index — was decided by the maintainer on 2026-08-05 in favor of a
package index, and moved to [Publish to PyPI](#publish-to-pypi-claude-fable-5).
Field validation did not have to complete first: `sleep_scoring` has applied
source updates through v0.16.8, which is enough evidence to publish a 0.x
package.

Still paused, and genuinely not urgent: whether to add a formatter, a linter,
or a CI workflow. Worth revisiting if release automation gets built, since
Trusted Publishing on PyPI needs a workflow to exist.
