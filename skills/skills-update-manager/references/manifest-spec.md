# Manifest Specification

## File Path

Default manifest path:

`catalog/skills-manifest.json`

## Top-Level Fields

- `manifest_version` (integer): schema version for parser compatibility.
- `generated_at` (ISO 8601 string): generation timestamp in UTC.
- `plugin` (object): plugin metadata (`name`, `version`).
- `repo` (string, optional): `owner/repo` for raw URL construction.
- `ref` (string, optional): branch or tag for raw URL construction.
- `skills` (array): list of skill entries.

## Skill Entry Fields

- `name` (string): local skill directory name.
- `version` (string): semantic version used for outdated checks.
- `skill_root` (string): repository root path to skill directory.
- `description` (string, optional): display text.
- `changelog` (string, optional): changelog path in repository.
- `files` (array): file descriptors under this skill.

## File Descriptor Fields

- `path` (string): repository-relative path.
- `sha256` (string): SHA-256 checksum of file content.
- `size` (integer): size in bytes.
- `url` (string, optional): explicit file URL. When absent, updater builds URL from repo/ref/path.

## Compatibility Rules

- Keep `manifest_version` stable for backward-compatible field additions.
- Bump `manifest_version` only when removing or reinterpreting existing fields.
- Add optional fields freely; unknown fields must be ignored by clients.
