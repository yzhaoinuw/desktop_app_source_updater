# Next Steps

Use this checklist alongside `work_log.md`. Keep "Currently Hot" limited to
threads that are actually in flight or likely to be resumed soon.

## Currently Hot

- [Downstream adoption validation](#downstream-adoption-validation-codex-gpt-5):
  prove the updater in at least two real desktop apps before broad adoption.

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
- Pin `desktop-app-source-updater==0.3.0` in each app's next full package —
  0.3.0 is on PyPI as of 2026-08-05, so the `git+https://` direct reference is no
  longer the normal way to depend on this package. No code changed between 0.2.0
  and 0.3.0, so this is a dependency-declaration change with no behavioral risk
  and no `UpdateConfig` field-order concern. Also supply an app-specific per-user
  `check_state_file`, migrate normal discovery to `latest_release_url`, and wire
  explicit/package-gate checks with `force_check=True`.
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

Status: the distribution question is closed; the tooling question is still
paused.

The distribution half of this thread — Git installs, release assets, or a
package index — was decided in favor of a package index and **shipped on
2026-08-05**: 0.3.0 is on PyPI, tagged, released, and archived on Zenodo. See
the work log entries for that date.

Still paused, and genuinely not urgent: whether to add a formatter, a linter, or
a CI workflow.

The one thing that would make the next release meaningfully easier is **Trusted
Publishing**, which removes API tokens from the process entirely — PyPI is
configured to trust a specific repository and workflow, and the workflow uploads
without a stored secret. It needs a GitHub Actions workflow to exist, and this
project has none. Worth doing before the release after next, when the manual
token dance would otherwise repeat; the 0.3.0 upload showed that step is where
the friction actually is.
