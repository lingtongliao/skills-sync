# Release Playbook

Use this flow to publish predictable updates for public users.

## 1. Update Version Numbers

- Update `.claude-plugin/plugin.json` version.
- Update each changed skill `SKILL.md` version.

## 2. Generate Manifest

```bash
python scripts/generate_manifest.py --repo owner/repo --ref main
```

Commit generated manifest.

## 3. Verify

- Run unit tests.
- Run updater dry-run against local manifest.
- Run updater apply against local manifest in a temporary skills root.

## 4. Create Release Tag

```bash
git tag -a vX.Y.Z -m "release: vX.Y.Z"
git push origin vX.Y.Z
```

## 5. Publish GitHub Release

- Create a release from `vX.Y.Z`.
- Include user-facing changelog.
- Mention migration notes if behavior changed.

## 6. Post-Release Validation

- Run `check` against `--ref vX.Y.Z` from a clean machine.
- Confirm `update --apply` works without manual patching.
