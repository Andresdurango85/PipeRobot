# 0006. Apache-2.0 license

- Status: Accepted
- Date: 2026-10-26

## Context

The repo is public and is the seed of a possible company. LeRobot, the main dependency, is
Apache-2.0.

## Decision

License the repo under Apache-2.0 (`LICENSE`, `license = "Apache-2.0"` in `pyproject.toml`).

## Alternatives considered

- MIT: shorter, but no explicit patent grant or patent-retaliation clause.
- GPL / AGPL: copyleft hurts adoption by companies, which are the target market.
- No license (all rights reserved): public but unusable by others, so no community.

## Consequences

- Anyone can use, modify and sell it, including in closed products, as long as they keep the notices.
- Andrés keeps the copyright: future code can be licensed differently (open core), but what was
  published stays Apache-2.0.
- Accepting outside contributions while keeping relicensing options would need a CLA.
