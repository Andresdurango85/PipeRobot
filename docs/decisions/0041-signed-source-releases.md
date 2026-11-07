# 0041. Signed source releases from a tag-triggered workflow

- Status: Accepted
- Date: 2026-11-06

## Context

The OpenSSF Best Practices form asks for a unique version per release and hand-written release
notes (`version_unique`, `release_notes`;
[answer sheet](../knowledge/openssf-best-practices.md)). Andrés chose a first release, `v0.1.0`,
signed. The repository has no tags or releases yet, and `pyproject.toml` already says `0.1.0`.

Scorecard v5.6.0's Signed-Releases check (`probes/releasesAreSigned`,
`probes/releasesHaveProvenance`, `checks/evaluation/signed_releases.go`) works as follows:

- It looks at the 5 most recent GitHub releases and skips any release with no uploaded assets.
  The automatic "Source code" archives are not assets.
- With no release that has assets, the check is inconclusive (-1) and does not count. That is
  today's state.
- A release with assets scores 10 if an asset name ends in `.intoto.jsonl` (provenance).
  Otherwise it scores 8 if one ends in `.asc`, `.minisig`, `.sig`, `.sign`, `.sigstore` or
  `.sigstore.json` (signature). Otherwise it scores 0.
- The check's score is the floor of the mean over those releases. It reads asset names only,
  not their contents.

Signed-Releases is a High-weight check, so it moves the overall score noticeably. Today's 7.3
would become about 6.8 with one unsigned release that has assets, about 7.4 with a signature
only, and about 7.5 with provenance.

`actions/attest`, already pinned in `certify.yml` at v4.2.2, generates SLSA build provenance
when it is given only `subject-path`. It signs the provenance with Sigstore through GitHub's OIDC
token and stores it in the attestation API. It also writes it to `bundle-path` as a JSON Sigstore
bundle: a DSSE envelope of the in-toto statement, plus the verification material (the
certificate and the transparency-log entry).

[ADR 0012](0012-dependency-vulnerability-triage.md) justifies two setuptools advisories by "we
build no packages". A release must not add a setuptools sdist or wheel.

## Decision

- **Artifact**: one source tarball, `piperobot-<tag>.tar.gz`, built with
  `git archive --format=tar --prefix=piperobot-<tag>/ <tag> | gzip -n -9`. It is deterministic
  for a given git version: file times are the commit's, and `gzip -n` drops the name and
  timestamp. No wheel, no sdist.
- **Signature and provenance assets** for the tarball:
  - `piperobot-<tag>.tar.gz.sigstore.json`: the Sigstore bundle from `actions/attest`. Verify it
    with `gh attestation verify <tarball> --bundle <file> --repo Andresdurango85/PipeRobot`.
  - `piperobot-<tag>.tar.gz.intoto.jsonl`: the bundle's DSSE envelope as one JSON line, which is
    the in-toto attestation format that SLSA tooling emits. It is the same signed provenance,
    not a second signature.
- **Workflow `release.yml`**:
  - It runs on `push` of tags `v*`, and on `workflow_dispatch` with a `tag` input.
  - It runs on hosted `ubuntu-26.04` only, with top-level `permissions: {}`.
  - It uses no caches and no `setup-uv`. Its actions are the ones already pinned in the repo,
    plus the `gh` CLI.
- **Its jobs**:
  1. `build` (`contents: read`) runs `.github/scripts/release_preflight.py check-tag`, which
     fails closed unless all of these hold:
     - the tag is `vX.Y.Z` and annotated;
     - its commit is reachable from `main`;
     - `pyproject.toml`'s version at that commit equals the tag;
     - `docs/releases/<tag>.md` exists there and is not blank.

     Then it builds the tarball.
  2. `attest` (`contents: read`, `id-token: write`, `attestations: write`) signs the tarball. It
     writes the two signature assets and verifies the bundle with `gh attestation verify
     --bundle` before anything is published.
  3. `publish` (`contents: write`), the only job that writes, runs `gh release create <tag>
     --verify-tag --notes-file docs/releases/<tag>.md` with the three assets. `gh` creates a
     draft, uploads the assets and then publishes, so the release is complete when it appears.
  4. `verify` (`contents: read`, `attestations: read`) downloads the published assets. It
     verifies the tarball against the attached bundle and against the attestation API, with the
     signer workflow pinned to `release.yml`, and checks that the envelope matches the bundle.
- **Release notes** are written by hand and committed as `docs/releases/<tag>.md` before the
  tag, and reviewed in a PR like any doc. A test checks that `pyproject.toml`'s version has its
  notes file.
- **Who tags**: the maintainer pushes an annotated tag on a merged `main` commit. No workflow
  creates tags.
- **Proposed, Andrés's call** (repository settings, not applied here):
  - a tag ruleset on `refs/tags/v*` that blocks deletion and moves, and lets only the maintainer
    create tags;
  - GitHub immutable releases, which lock a published release's assets and its tag and add
    GitHub's own release attestation.

## Alternatives considered

- **`slsa-github-generator`'s generic generator**: it writes `.intoto.jsonl` natively, but it
  must be called by tag, not by SHA, against the SHA-pinning rule
  ([0027](0027-self-hosted-runner-push-only-and-pinned-actions.md)). It is not in the
  repository's allowed actions, and it would add a second provenance system next to the
  attestation API that `certify.yml` uses.
- **Signature only (`.sigstore.json`)**: honest and simpler, but it scores 8. Extracting the
  envelope costs one small, tested script step.
- **A wheel or sdist** (`uv build`): nothing installs PipeRobot from an index yet, and it would
  weaken the setuptools reasoning in ADR 0012.
- **GitHub's automatic source archives**: they are not uploaded assets, so they cannot carry a
  signature or count for Scorecard. GitHub does not guarantee their bytes stay the same either.
- **Generated release notes**: the badge asks for a human summary, not `git log`.

## Consequences

- **Every release needs**: a notes file, a matching `pyproject.toml` version, and an annotated
  tag pushed by the maintainer. A failed check stops the run before anything is signed or
  published.
- **Re-running a failed release**: `workflow_dispatch` runs `release.yml` from `main` but checks
  out the tag for everything else, so it fixes a workflow bug, a transient failure, or a check
  that failed because `main` had not yet received the tagged commit. A wrong version, missing
  notes or a bug in `release_preflight.py` needs a new commit and a new tag. A lightweight tag
  is rejected: delete it and push an annotated one (`git tag -a`).
- **Score**: Signed-Releases goes from -1 to 10, read from the API after the first release.
  Later releases must keep their signature assets, or one unsigned release pulls the mean down.
- **Verification**: the tarball can be verified two ways, offline with the attached bundle and
  through the attestation API. The `.intoto.jsonl` envelope alone does not carry the
  certificate, so verify with the `.sigstore.json` bundle.
