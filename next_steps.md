# Next Steps

Use this checklist alongside `work_log.md`. Keep "Currently Hot" limited to
threads that are actually in flight or likely to be resumed soon.

## Currently Hot

- [Downstream adoption validation](#downstream-adoption-validation-codex-gpt-5):
  prove the updater in at least two real desktop apps before broad adoption.

## Downstream Adoption Validation (Codex GPT-5)

Status: pending

The package has unit coverage for the runtime updater and release-asset builder,
but it still needs field validation inside real desktop app launch flows. The
first known source is `C:\Users\yzhao\python_projects\fp_analysis`, where the
prototype originated.

Current field evidence: the frozen `sleep_scoring` v0.16.5 executable can query
the real GitHub latest-release endpoint from a fresh package extraction. The
first compatible `app_src` update still needs to prove the apply path from that
baseline.

Remaining work:

- Wire the updater into the `fp_analysis` desktop launcher with app-specific
  `UpdateConfig` values.
- Build a source update asset from real `fp_analysis` Git refs using repeated
  `--from-ref` values when appropriate.
- Verify that startup update behavior works for a clean compatible install, a
  skipped-release jump, and a local-edit mismatch.
- Repeat the same adoption check in one additional desktop app.
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

Status: paused until downstream adoption evidence exists

Potential follow-up after field validation: decide whether to distribute this
package through editable Git installs, GitHub release assets, or a package
index. Also decide whether to add a formatter/linter or CI workflow once the
library shape stabilizes.
