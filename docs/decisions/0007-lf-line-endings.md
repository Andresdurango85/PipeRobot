# 0007. LF line endings on every machine

- Status: Accepted
- Date: 2026-10-26

## Context

Git on the Windows laptop converts line endings to CRLF on checkout. The home PC and the Linux CI
runner may behave differently, which causes noisy diffs and can break golden-file comparisons.

## Decision

`.gitattributes` sets `* text=auto eol=lf`: every text file is LF in the repo and in every working
copy. Golden files are written with `newline="\n"`.

## Alternatives considered

- Rely on each machine's `core.autocrlf`: depends on per-machine config nobody remembers to set.

## Consequences

- Identical files on both machines and in CI; golden tests compare byte for byte.
