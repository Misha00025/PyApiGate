# Contributing

## Versioning Rules

Project is in `0.x.y` pre-release phase.

| Increment | When |
|-----------|------|
| **Patch** (`0.x.z`) | Bug fixes, minor improvements, new small features, refactoring, tests, documentation |
| **Minor** (`0.y.0`) | Significant changes: new functionality that changes the whole way things work, **breaking changes** (the most important criterion), major architectural overhaul |

### Rules

- A version bump to `0.y.0` (minor) is **required** when there are breaking changes that break backward compatibility — even if the code change itself seems small
- A version bump to `0.x.z` (patch) is fine for adding features, as long as nothing existing breaks
- Tags follow the existing style: `0.1.0`, `0.1.1`, `0.2.0` (no `v` prefix)
- Tag after merging into `master`
- Each tag gets a GitHub Release with a brief changelog

## Branching

- `master` — stable, protected
- Feature/fix branches — from `master`, merged via PR

## PR Checklist

- [ ] `python scripts/validate_config.py` passes
- [ ] `pytest tests/ -v` passes
- [ ] Documentation updated if adding/changing user-facing features
