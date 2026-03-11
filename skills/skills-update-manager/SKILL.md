---
name: skills-update-manager
description: This skill should be used when the user asks to "check whether my skills are up to date", "compare local skills with latest GitHub version", "summarize skill differences", "update skills to latest version", "sync local skills from manifest", or "audit skill updates before applying".
version: 0.1.0
tags: [Skills, Update, Diff, GitHub]
---

# Skills Update Manager

Provide a safe and repeatable workflow to check local skills, compare against latest GitHub manifest, summarize change impact, and update local skill folders with backup and rollback.

## Purpose

Solve a common problem: local skills are copied once and then become stale, while upstream repositories continue adding features and fixes.

Use this skill to:
- Detect whether local skills are outdated.
- Produce clear diffs between local and latest versions.
- Apply updates safely with backup and restore path.
- Keep a machine-readable source record for each updated skill.

## Prerequisites

- Ensure Python 3.10+ is available.
- Ensure local skills are stored under `~/.claude/skills` (default) or provide `--skills-root`.
- Ensure upstream repository publishes `catalog/skills-manifest.json`.
- Prefer release tags (`--ref vX.Y.Z`) for production-grade updates.

## Files in This Skill

- `scripts/manage_skills.py` - CLI for check, diff, and update.
- `references/manifest-spec.md` - Manifest schema and field definitions.
- `references/release-playbook.md` - Maintainer release flow.
- `examples/sample-manifest.json` - Minimal manifest example.

## Workflow

### 1) Check Status

Run check against manifest.

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/skills-update-manager/scripts/manage_skills.py" check \
  --repo lingtongliao/re-skills \
  --ref main
```

Interpret status quickly:
- `up-to-date`: local version and file hashes match manifest.
- `outdated`: local version is lower than remote version.
- `missing`: local skill folder does not exist.
- `modified`: local files differ from manifest even when version matches.
- `ahead-local`: local version is higher than manifest version.

Use JSON output when downstream automation is needed:

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/skills-update-manager/scripts/manage_skills.py" check \
  --repo lingtongliao/re-skills \
  --ref main \
  --json
```

### 2) Summarize Differences

Run diff for all skills or a specific skill.

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/skills-update-manager/scripts/manage_skills.py" diff \
  --repo lingtongliao/re-skills \
  --ref main
```

Limit scope to one skill:

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/skills-update-manager/scripts/manage_skills.py" diff \
  --repo lingtongliao/re-skills \
  --ref main \
  --skill skills-update-manager
```

Show patch preview for `SKILL.md` to quickly inspect user-visible behavior changes:

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/skills-update-manager/scripts/manage_skills.py" diff \
  --repo lingtongliao/re-skills \
  --ref main \
  --skill skills-update-manager \
  --show-patch
```

### 3) Plan Update (Dry Run)

Preview update actions without touching local files.

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/skills-update-manager/scripts/manage_skills.py" update \
  --repo lingtongliao/re-skills \
  --ref main
```

Dry run is default. It reports what will be updated and why.

### 4) Apply Update

Apply update with backup.

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/skills-update-manager/scripts/manage_skills.py" update \
  --repo lingtongliao/re-skills \
  --ref main \
  --apply
```

Behavior during apply:
- Create backup for existing local skill directory.
- Download files listed in manifest.
- Verify SHA-256 for every downloaded file.
- Replace local skill directory only after download and hash verification succeed.
- Write `.skill-source.json` in each updated skill directory.

## Recommended Operating Modes

### Stable Mode

Use release tag to avoid accidental breaking changes:

```bash
--ref v1.2.0
```

### Fast Mode

Use branch head for rapid iteration:

```bash
--ref main
```

Only use fast mode for personal experimentation or internal testing.

## Safety Rules

- Run `check` and `diff` before `update --apply`.
- Avoid `--apply` directly against unknown repositories.
- Keep backup directory for at least one full work cycle.
- Prefer updating one skill at a time for high-risk changes.
- Do not force-update when local status is `ahead-local`; inspect manually first.

## Troubleshooting

### Manifest Not Found

- Verify `--repo` and `--ref`.
- Confirm file exists at `catalog/skills-manifest.json`.
- For custom path, pass `--manifest-path`.

### Hash Mismatch

- Remote file changed after manifest generation.
- Re-generate manifest and retry.
- Prefer using release tag to lock exact content.

### Local Modified State

- `modified` indicates local drift.
- Run `diff` and preserve local customizations before apply.

## Maintainer Notes

Generate manifest before publishing:

```bash
python scripts/generate_manifest.py --repo lingtongliao/re-skills --ref main
```

For complete release steps, follow `references/release-playbook.md`.

## Additional Resources

- `references/manifest-spec.md` - Schema and compatibility rules.
- `references/release-playbook.md` - GitHub release and tag flow.
- `examples/sample-manifest.json` - Practical manifest template.
