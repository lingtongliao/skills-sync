#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_version(skill_md: Path) -> str:
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Missing frontmatter in {skill_md}")
    for line in lines[1:200]:
        if line.strip() == "---":
            break
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise ValueError(f"Missing version field in {skill_md}")


def build_manifest(repo_root: Path, repo: str | None, ref: str) -> dict:
    plugin_json = repo_root / ".claude-plugin" / "plugin.json"
    plugin_data = json.loads(plugin_json.read_text(encoding="utf-8"))

    skills_dir = repo_root / "skills"
    entries = []
    changelog_file = repo_root / "CHANGELOG.md"
    changelog_path = "CHANGELOG.md" if changelog_file.exists() else None

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_root = skill_md.parent
        skill_name = skill_root.name
        files = []
        for file in sorted(skill_root.rglob("*")):
            if not file.is_file():
                continue
            if "__pycache__" in file.parts:
                continue
            if file.suffix in {".pyc", ".pyo"}:
                continue
            rel_path = file.relative_to(repo_root).as_posix()
            files.append(
                {
                    "path": rel_path,
                    "sha256": sha256_file(file),
                    "size": file.stat().st_size,
                }
            )

        entries.append(
            {
                "name": skill_name,
                "version": extract_version(skill_md),
                "skill_root": skill_root.relative_to(repo_root).as_posix(),
                "description": f"Managed skill: {skill_name}",
                "changelog": changelog_path,
                "files": files,
            }
        )

    now = (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "manifest_version": 1,
        "generated_at": now,
        "plugin": {
            "name": plugin_data.get("name", "unknown-plugin"),
            "version": plugin_data.get("version", "0.0.0"),
        },
        "repo": repo,
        "ref": ref,
        "skills": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate catalog/skills-manifest.json from local skill files"
    )
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument(
        "--output", default="catalog/skills-manifest.json", help="Output manifest path"
    )
    parser.add_argument("--repo", default=None, help="GitHub owner/repo")
    parser.add_argument("--ref", default="main", help="Git reference")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output = (repo_root / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(repo_root, args.repo, args.ref)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote manifest: {output}")
    print(f"Skills: {len(manifest['skills'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
