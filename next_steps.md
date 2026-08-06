# Next Steps

Use this checklist alongside `work_log.md`. Keep "Currently Hot" limited to
threads that are actually in flight or likely to be resumed soon.

## Currently Hot

- [Downstream adoption validation](#downstream-adoption-validation-codex-gpt-5):
  prove the updater in at least two real desktop apps before broad adoption.

## Downstream Adoption Validation (Codex GPT-5)

Status: in progress — one of the two apps has proven the apply path in the field.

**Track app-side work in the adopting repo, not here.** Both apps maintain their
own `next_steps.md`, and this thread drifted badly by duplicating their
checklists: on 2026-08-05 it still listed "wire the updater into the `fp_analysis`
launcher" as remaining work that had in fact landed on 2026-07-24, four days
before this thread's last edit. Keep only updater-level facts below, and link out
for the rest.

- `sleep_scoring` — [its own next_steps](https://github.com/yzhaoinuw/sleep_scoring/blob/main/next_steps.md),
  Lightweight Source Releases thread.
- `fp_analysis` — [its own next_steps](https://github.com/yzhaoinuw/fp_analysis/blob/main/next_steps.md),
  First Source-Update Release Trial thread.

Field evidence as of 2026-08-05, verified against both repos' published releases:

- **`sleep_scoring` has applied a real code-only source update.** Its v0.16.8
  release carries `sleep_scoring_app_update_v0.16.8.zip`. That is the one
  confirmed end-to-end apply in the field.
- **`fp_analysis` is fully integrated but has not yet applied one.** Its launcher,
  config, packaging spec, builder wrapper, and tests are all in place, and the
  v0.6.0 baseline package is published — but every `fp_analysis` release so far
  carries only a ~117 MB `*_full.zip`, with nothing matching its own
  `fp_analysis_app_update_` prefix. Its own repo tracks this as the remaining
  trial.

Remaining work at the updater level:

- **Reconcile the downstream pins, which have drifted and are inconsistent.**
  `sleep_scoring` pins two different things in the same repo: `pyproject.toml`
  uses `@main`, a moving target that now resolves to 0.3.0 and keeps moving,
  while `requirements.txt` pins commit `5eab40b` (2026-07-30). `fp_analysis` pins
  `85bb68e` (2026-07-28). Which updater a packaged build actually contains
  therefore depends on which file the build path reads.

  Both adopters construct `UpdateConfig` entirely with keyword arguments
  (`sleep_scoring` at `run_desktop_app.py:132`, `fp_analysis` in
  `startup_update_config.py`), so the positional field-order hazard in
  `AGENTS.md` does not currently apply to either — the real problem is
  reproducibility, not misbinding. A packaged release built from `@main` has no
  record of which updater it froze, and because the launcher and the updater both
  ship inside the frozen bundle, a wrong one cannot be corrected by a source
  update; it needs a full packaged release.

  Move all three to `desktop-app-source-updater==0.3.0` now that the package is
  on PyPI. No code changed between 0.2.0 and 0.3.0, so this is a
  dependency-declaration change with no behavioral risk, and it drops the Git
  requirement from downstream build environments.
- Pin a schema-2-compatible updater revision into a new full downstream package
  before testing Python config merge assets; existing frozen runtimes cannot
  acquire this feature through source-only updates.
- Record any app-specific environment variable names, launcher pattern changes,
  or README clarifications that adoption surfaces.

Definition of done:

- Two downstream apps have each applied a code-only source update in the field
  without Git installed on the user machine. One of two so far.
- Dependency, packaging, local-data, deletion, and rename cases are confirmed to
  block or require packaged refreshes as intended.
- Any lessons from downstream adoption are reflected in `README.md`,
  `AGENTS.md`, and tests where useful.

## Background / Paused

### Distribution And Release Polish

Status: the distribution question is closed; the tooling question is still
paused.

The distribution half of this thread — Git installs, release assets, or a
package index — was decided in favor of a package index and **shipped on
2026-08-05**: 0.3.0 is on PyPI, tagged, released, and archived on Zenodo. See
the work log entries for that date.

CI landed on 2026-08-05: `.github/workflows/tests.yml` runs the suite on Linux,
Windows, and macOS across Python 3.10 to 3.13, and builds and `twine check`s the
distribution on every push. All 12 matrix jobs passed on the first run. This
matters mainly because the PyPI page advertises those four Python versions and
`Operating System :: OS Independent`, and nothing had verified them — Linux had
never run these tests at all.

Still paused, and genuinely not urgent: whether to add a formatter or a linter.

**Trusted Publishing is wired on this side** as of 2026-08-05:
`.github/workflows/release.yml` builds on a `v*` tag push, refuses to continue
when the tag and `pyproject.toml` disagree, and publishes through
`pypa/gh-action-pypi-publish` with an OIDC token rather than a stored secret. A
manual run builds and checks without uploading, so the workflow can be exercised
without spending a version number; that dry run passed on 2026-08-05.

**It does not work until the maintainer adds the publisher on PyPI**, which only
they can do — <https://pypi.org/manage/project/desktop-app-source-updater/settings/publishing/>,
with owner `yzhaoinuw`, repository `desktop_app_source_updater`, workflow
`release.yml`, and environment `pypi`. The environment name must match the
workflow exactly or the upload is rejected. Until that entry exists, a tag push
builds fine and fails at the publish step.

Once configured, releasing is `git tag vX.Y.Z && git push origin vX.Y.Z`. The
0.3.0 upload showed the manual token step is where the friction actually was,
between the missing TTY under a `!`-prefixed command and a stubbed `.pypirc`
silently beating the interactive prompt.
