# Next Steps

Use this checklist alongside `work_log.md`. Keep "Currently Hot" limited to
threads that are actually in flight or likely to be resumed soon.

## Currently Hot

- [Publish to PyPI](#publish-to-pypi-claude-fable-5): make the package
  `pip install`-able. Handed off 2026-08-05.
- [Make the README findable](#make-the-readme-findable-claude-fable-5): the
  README never says "PyInstaller." Handed off 2026-08-05.
- [Downstream adoption validation](#downstream-adoption-validation-codex-gpt-5):
  prove the updater in at least two real desktop apps before broad adoption.

## Publish To PyPI (claude-fable-5)

Status: handed off 2026-08-05, not started. Decided by the maintainer; the
alternatives in [Distribution And Release Polish](#distribution-and-release-polish)
are settled by this.

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

Remaining work:

- **Merge the `dev` branch first.** `origin/dev` is one commit ahead of
  `origin/main` (`8f0a106 Add a How This Compares section to the README`) and
  nothing else differs. It has been waiting since 2026-08-03 for the
  maintainer's look at the rendered page. The README becomes the PyPI project
  page, so this should land before the upload rather than after.
- **Add the metadata that a package page needs.** `pyproject.toml` already has
  the name, version, MIT license, classifiers, and an empty dependency list.
  Missing: a `[project.urls]` table (Homepage, Repository, Issues,
  Documentation) — this is what fills the sidebar links on the PyPI page and is
  a large part of why a package page is worth having — and `keywords`, which
  should carry the same terms as the GitHub topics (`pyinstaller`,
  `auto-update`, `updater`, `desktop-app`, `github-releases`).
- **Decide the version to publish.** Recommendation: bump to `0.3.0` and cut a
  matching GitHub Release, so the README changes and the new metadata ship
  together, the Zenodo archive picks the release up and keeps the DOI in step,
  and the `0.2.0` tag stays as the honest record of the pre-PyPI state. A PyPI
  version can never be re-uploaded, so any metadata correction after the fact
  costs a version number either way. Publishing `0.2.0` as-is is the
  alternative if the maintainer prefers the PyPI version to match what is
  already archived.
- **Check how the README renders as the project page.** `readme = "README.md"`
  means PyPI renders it as the long description. Relative links resolve against
  PyPI, not GitHub, so any relative link to a file in the repo breaks there;
  in-page anchors and the absolute badge URLs are fine. Run
  `python -m build` then `twine check dist/*`.
- **Upload to TestPyPI first**, install from it into a clean environment, and
  confirm the console script `desktop-app-source-update-asset` is on the path.
  Then upload to PyPI.
- **Update the README's Installation section afterward.** It currently opens
  with "Until the package is published on PyPI, install it from GitHub" — that
  sentence and the `git+https://` recipe become the fallback, not the headline.
  Keep the direct-reference form documented, because pinning by commit is still
  how downstream apps adopt this package (see the `UpdateConfig` field-order
  contract in `AGENTS.md`).
- **Update `CITATION.cff`** (`version`, `date-released`) as part of the release,
  the same way the other repos do it.

What only the maintainer can do: create the PyPI account if there is not one,
and either issue an API token for a manual `twine upload` or configure Trusted
Publishing for a GitHub Actions workflow. The token route is simpler for a
first manual upload; Trusted Publishing is worth it only once releases are
automated, and this project has no CI workflow yet.

Definition of done:

- `pip install desktop-app-source-updater` works from a clean environment.
- The PyPI page shows the README with working links and a sidebar pointing at
  the repository and issues.
- The README no longer apologizes for not being on PyPI.

## Make The README Findable (claude-fable-5)

Status: handed off 2026-08-05, not started. Free to do, and it improves the
value of everything else — the PyPI page, the forum post, and any later
article all send readers to this README.

**The specific finding that prompted this, checked 2026-08-05: the README on
`main` does not contain the word "PyInstaller" anywhere. Nor "frozen."** The
GitHub description says PyInstaller and the unmerged `dev` section mentions it
twice, but the page itself never does. PyInstaller is the single most likely
word in the question someone types when they need this package. Search engines
and AI assistants both work by matching the wording of a question against the
text of a page, so a page that never uses the term will not be returned for it,
no matter how well it solves the problem.

Remaining work:

- **Say "PyInstaller" in the opening paragraph**, naming it as the case this
  was built for while keeping the accurate general claim — the package is
  framework-agnostic and works for any Python desktop app that ships a stable
  launcher beside plain source. Do not overcorrect into implying a PyInstaller
  dependency; there is none, which is why the repo is deliberately not tagged
  `dash` or tied to a packager.
- **Add a short question-and-answer block near the top**, above or just below
  Content Overview, with the questions as headings in the words people actually
  use, each answered in two or three sentences with a link into the section
  that covers it. The answers already exist in the README; this is rephrasing,
  not new material. The three to start with:
  - "How do I update a PyInstaller app without rebuilding it?"
  - "Can I keep my `.py` files outside the frozen bundle and update only
    those?"
  - "Do I need code signing or an update server?" (the honest answer is no to
    both, and the trade-off is already written in Update Scope and Safety and
    in the `dev` branch's How This Compares section)
- Keep the Content Overview list in sync with any new headings.

Definition of done:

- Someone who searches for the phrase in any of those three questions would
  find a page that visibly answers it.
- No claim in the new text overstates what the package does; the safety limits
  and the no-signing trade-off stay as prominent as they are now.

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
