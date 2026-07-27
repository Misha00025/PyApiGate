# Contributing

## Versioning Rules (SemVer 2.0)

Project is in `0.x.y` pre-release phase.

| Increment | When |
|-----------|------|
| **Patch** (`0.x.z`) | Bug fixes, documentation, refactoring, tests — no new user-facing functionality |
| **Minor** (`0.y.0`) | New functionality: new engine features, config changes, breaking changes, documentation overhaul |

### Rules

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
- [ ] No `C#` or `get_user_id` references introduced
