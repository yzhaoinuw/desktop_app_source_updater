# Next Steps

Use this checklist alongside `work_log.md`. Keep "Currently Hot" limited to
threads that are actually in flight or likely to be resumed soon.

## Currently Hot

- [Downstream adoption validation](#downstream-adoption-validation-codex-gpt-5):
  prove the updater in at least two real desktop apps before broad adoption.
- [Self-updating updater](#self-updating-updater-claude-opus-5): decided and
  designed; gated on the second field apply. Groundwork has landed.

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

## Self-Updating Updater (Claude Opus 5)

Status: decided in favor, designed, and deliberately not started. The two pieces
that are useful regardless of when the switch flips landed on 2026-08-06.

**The problem.** This package ships frozen inside the packaged app next to the
launcher, so an updater fix cannot arrive through a source update — it needs a
full packaged release. That is a hole in the project's own premise, and it bites
hardest at the worst moment: a broken updater is exactly when a cheap fix path is
most wanted. This is the same fact already noted in the pin-drift item above,
stated as a thread of its own.

**The design** is written up in
[README.md → Updating the Updater Itself](README.md#updating-the-updater-itself):
vendor the package directory into the updateable source tree, add it to
`allowed_payload_paths`, and let the existing machinery update it. Four
considerations are recorded there — frozen-copy shadowing, the one-launch-behind
property, the risk of breaking the update channel, and schema forward
compatibility. Read that section before starting; do not re-derive it.

**Landed 2026-08-06, independent of the decision:**

- `.py` payloads are parsed before anything is written, so an asset carrying a
  syntax error fails the whole update instead of installing a file that matches
  its manifest hash and only fails at import time.
- `TestSelfUpdateSafetyContract` pins the no-deferred-imports contract that makes
  self-replacement safe. Verified by mutation: injecting a function-level import
  into `core.py` fails the test.

**The gate: do not start until `fp_analysis` has applied its first real source
update in the field.** The definition of done above is two apps applying a
code-only update; one has. Giving the updater authority over its own code before
its ordinary path is proven twice is backwards.

**When the gate opens, fold this into the full packaged release the pin
reconciliation and the schema-2 baseline already require.** All three need the
same release; doing them separately spends three.

**The standing cost, worth restating so it is not rediscovered as an objection:**
a broken updater still requires a full packaged release. What changes is that a
cheap channel gains the ability to cause one. That is the trade, and it was
accepted knowingly.

**One caveat on the reasoning.** The case rests partly on low churn — no code
changed between 0.2.0 and 0.3.0 — but this package is about a month old and both
adoptions are still in trial, so it is likely in the highest-churn period it will
ever see. That cuts both ways: the value of cheap updater fixes is highest now,
and so is the risk of building a self-update channel on a codebase still moving.
Revisit if churn stays high after the gate opens.

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

The maintainer added the matching publisher on PyPI the same day (owner
`yzhaoinuw`, repository `desktop_app_source_updater`, workflow `release.yml`,
environment `pypi`), so releasing should now be
`git tag vX.Y.Z && git push origin vX.Y.Z`.

**The OIDC handshake itself is still unexercised**, because nothing
package-relevant changed after v0.3.0 and manufacturing a version purely to test
the pipeline would spend a PyPI version permanently. The next real release is the
first true test. If the publisher entry is wrong, the failure is loud and cheap:
the `publish` job fails at upload, no version number is consumed, and re-running
the same workflow run after fixing the PyPI entry is enough. Nothing needs
re-tagging.

The 0.3.0 upload showed the manual token step is where the friction actually was,
between the missing TTY under a `!`-prefixed command and a stubbed `.pypirc`
silently beating the interactive prompt.
