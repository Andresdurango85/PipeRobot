# Knowledge base

Verified facts, gotchas and how-tos, one file per topic. This is where "it took an hour to find
out" goes, so nobody (human or agent) pays that hour twice.

## Rules

- One fact per bullet, written so it can be checked: what, where, and with which version.
- End each entry with its provenance: `_(verified YYYY-MM-DD, <tool/version>, <source>)_`.
- When a fact stops being true, strike it out (`~~old fact~~`) and add the new fact with its date
  below it; don't silently delete history.
- Decisions go in [`../decisions/`](../decisions/README.md); link to them, don't restate them.
- Public repo: no secrets, tokens, employer names or machine-specific paths.

## Topics

| File | What it covers |
| --- | --- |
| [lerobot.md](lerobot.md) | LeRobot 0.6 APIs, dataset format, install notes |
| [datasets.md](datasets.md) | Public SO-101 datasets: what they contain and their pitfalls |
| [ci.md](ci.md) | GitHub Actions, runners, Hub access from CI |
| [isaac.md](isaac.md) | Isaac Sim, Isaac Lab, Isaac Lab-Arena: platforms and NVIDIA's SO-101 course |
