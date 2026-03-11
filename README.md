# skill-sync

`skill-sync` is a Claude Code plugin that provides a reusable skill to:
- check whether local skills are latest,
- summarize differences with latest GitHub version,
- update local skills safely with backup and rollback.

## Repository Structure

```text
.claude-plugin/plugin.json
skills/skills-update-manager/
  SKILL.md
  scripts/manage_skills.py
  references/
  examples/
scripts/generate_manifest.py
catalog/skills-manifest.json
tests/
```

## Install for Local Development

1. Clone repository.
2. Load plugin in Claude Code with plugin directory mode.
3. Trigger with prompts like:
   - "检查我的skills是不是最新版本"
   - "对比本地skill和GitHub最新差异"
   - "更新我的skills到最新版本"

## User CLI Examples

Check all skills:

```bash
python "skills/skills-update-manager/scripts/manage_skills.py" check \
  --repo lingtongliao/skill-sync \
  --ref main
```

Show diff of a specific skill:

```bash
python "skills/skills-update-manager/scripts/manage_skills.py" diff \
  --repo lingtongliao/skill-sync \
  --ref main \
  --skill skills-update-manager \
  --show-patch
```

Apply update:

```bash
python "skills/skills-update-manager/scripts/manage_skills.py" update \
  --repo lingtongliao/skill-sync \
  --ref main \
  --apply
```

## Maintainer Commands

Generate manifest:

```bash
python scripts/generate_manifest.py --repo lingtongliao/skill-sync --ref main
```

Run tests:

```bash
python -m unittest discover -s tests
```

## Release Notes

Recommended release flow:
1. bump versions in `plugin.json` and changed `SKILL.md` files;
2. regenerate `catalog/skills-manifest.json`;
3. run tests;
4. create git tag `vX.Y.Z`;
5. publish GitHub Release.
