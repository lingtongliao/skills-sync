#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import difflib
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_MANIFEST_PATH = "catalog/skills-manifest.json"
DEFAULT_SKILLS_ROOT = Path.home() / ".claude" / "skills"
DEFAULT_BACKUP_ROOT = Path.home() / ".claude" / "skills-backup"
USER_AGENT = "skills-update-manager/0.1.0"
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


@dataclasses.dataclass
class SkillReport:
    name: str
    status: str
    local_version: str | None
    remote_version: str
    missing_files: list[str]
    changed_files: list[str]
    extra_files: list[str]


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_version_from_text(text: str) -> str | None:
    lines = text.splitlines()
    if not lines:
        return None
    if lines[0].strip() != "---":
        return None

    for line in lines[1:200]:
        if line.strip() == "---":
            return None
        if line.startswith("version:"):
            raw = line.split(":", 1)[1].strip()
            return raw.strip("\"'")
    return None


def extract_local_version(skill_dir: Path) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    return extract_version_from_text(read_text(skill_md))


def parse_semver(version: str | None) -> tuple[int, int, int] | None:
    if not version:
        return None
    match = SEMVER_RE.match(version.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def compare_versions(local_version: str | None, remote_version: str) -> int | None:
    local = parse_semver(local_version)
    remote = parse_semver(remote_version)
    if not local or not remote:
        return None
    if local < remote:
        return -1
    if local > remote:
        return 1
    return 0


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_posix(path: Path) -> str:
    return path.as_posix()


def fetch_bytes(url: str, timeout: int) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def load_manifest(args: argparse.Namespace) -> tuple[dict[str, Any], str, Path | None]:
    if args.manifest_file:
        manifest_file = Path(args.manifest_file).expanduser().resolve()
        manifest = json.loads(read_text(manifest_file))
        return manifest, str(manifest_file), manifest_file

    manifest_url = args.manifest_url
    if not manifest_url:
        if not args.repo:
            raise ValueError(
                "Missing source: provide --manifest-file, --manifest-url, or --repo"
            )
        manifest_url = f"https://raw.githubusercontent.com/{args.repo}/{args.ref}/{args.manifest_path.lstrip('/')}"

    manifest = json.loads(fetch_bytes(manifest_url, args.timeout).decode("utf-8"))
    return manifest, manifest_url, None


def validate_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest.get("skills"), list):
        raise ValueError("Manifest 'skills' must be an array")
    for skill in manifest["skills"]:
        if (
            "name" not in skill
            or "version" not in skill
            or "skill_root" not in skill
            or "files" not in skill
        ):
            raise ValueError("Each skill requires name/version/skill_root/files")
        if not isinstance(skill["files"], list):
            raise ValueError(f"Skill '{skill['name']}' files must be an array")


def choose_skills(
    manifest: dict[str, Any], selected: list[str]
) -> list[dict[str, Any]]:
    skills = manifest.get("skills", [])
    if not selected:
        return skills

    index = {entry["name"]: entry for entry in skills}
    missing = [name for name in selected if name not in index]
    if missing:
        raise ValueError(f"Skill not found in manifest: {', '.join(missing)}")
    return [index[name] for name in selected]


def manifest_rel_path(skill_entry: dict[str, Any], repo_path: str) -> str:
    skill_root = skill_entry["skill_root"].rstrip("/") + "/"
    if not repo_path.startswith(skill_root):
        raise ValueError(
            f"Path '{repo_path}' does not belong to skill_root '{skill_entry['skill_root']}'"
        )
    return repo_path[len(skill_root) :]


def iter_local_files(skill_dir: Path) -> set[str]:
    if not skill_dir.exists():
        return set()
    result: set[str] = set()
    for file in skill_dir.rglob("*"):
        if not file.is_file():
            continue
        if "__pycache__" in file.parts:
            continue
        if file.suffix in {".pyc", ".pyo"}:
            continue
        rel = to_posix(file.relative_to(skill_dir))
        if rel == ".skill-source.json":
            continue
        result.add(rel)
    return result


def evaluate_skill(skill_entry: dict[str, Any], skills_root: Path) -> SkillReport:
    name = skill_entry["name"]
    remote_version = str(skill_entry["version"])
    local_dir = skills_root / name
    local_version = extract_local_version(local_dir)

    if not local_dir.exists():
        return SkillReport(
            name=name,
            status="missing",
            local_version=None,
            remote_version=remote_version,
            missing_files=[
                manifest_rel_path(skill_entry, file_entry["path"])
                for file_entry in skill_entry["files"]
            ],
            changed_files=[],
            extra_files=[],
        )

    missing_files: list[str] = []
    changed_files: list[str] = []
    expected_rel: set[str] = set()

    for file_entry in skill_entry["files"]:
        repo_path = file_entry["path"]
        rel = manifest_rel_path(skill_entry, repo_path)
        expected_rel.add(rel)
        local_file = local_dir / Path(rel)
        if not local_file.exists():
            missing_files.append(rel)
            continue
        if sha256_file(local_file) != file_entry.get("sha256"):
            changed_files.append(rel)

    extra_files = sorted(iter_local_files(local_dir) - expected_rel)
    compare_result = compare_versions(local_version, remote_version)

    if compare_result == -1:
        status = "outdated"
    elif compare_result == 1:
        status = "ahead-local"
    elif missing_files:
        status = "incomplete"
    elif changed_files or extra_files:
        status = "modified"
    elif compare_result is None:
        status = "unversioned-match"
    else:
        status = "up-to-date"

    return SkillReport(
        name=name,
        status=status,
        local_version=local_version,
        remote_version=remote_version,
        missing_files=sorted(missing_files),
        changed_files=sorted(changed_files),
        extra_files=extra_files,
    )


def summarize_reports(reports: list[SkillReport]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        counts[report.status] = counts.get(report.status, 0) + 1
    return counts


def derive_remote_base_url(
    args: argparse.Namespace, manifest: dict[str, Any], manifest_source: str
) -> str | None:
    if args.manifest_file and not args.repo and not args.manifest_url:
        return None
    if args.repo:
        return f"https://raw.githubusercontent.com/{args.repo}/{args.ref}/"
    if manifest.get("repo") and manifest.get("ref"):
        return (
            f"https://raw.githubusercontent.com/{manifest['repo']}/{manifest['ref']}/"
        )
    if args.manifest_url:
        marker = args.manifest_path.lstrip("/")
        if args.manifest_url.endswith(marker):
            return args.manifest_url[: -len(marker)]
        if "/" in args.manifest_url:
            return args.manifest_url.rsplit("/", 1)[0] + "/"
    if manifest_source.startswith("http"):
        return None
    return None


def read_remote_file(
    file_entry: dict[str, Any],
    args: argparse.Namespace,
    remote_base_url: str | None,
    manifest_file: Path | None,
) -> bytes:
    explicit_url = file_entry.get("url")
    if explicit_url:
        return fetch_bytes(explicit_url, args.timeout)

    repo_path = file_entry["path"]
    if remote_base_url:
        return fetch_bytes(urljoin(remote_base_url, repo_path), args.timeout)

    if manifest_file is None:
        raise ValueError(f"No strategy to load remote file '{repo_path}'")

    repo_root = manifest_file.parent.parent
    file_path = (repo_root / repo_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Missing local source file '{file_path}'")
    return file_path.read_bytes()


def format_report(report: SkillReport) -> str:
    lines = [
        f"- {report.name}: {report.status}",
        f"  local={report.local_version or 'n/a'} remote={report.remote_version}",
        f"  missing={len(report.missing_files)} changed={len(report.changed_files)} extra={len(report.extra_files)}",
    ]
    if report.missing_files:
        lines.append(f"  missing files: {', '.join(report.missing_files[:8])}")
    if report.changed_files:
        lines.append(f"  changed files: {', '.join(report.changed_files[:8])}")
    if report.extra_files:
        lines.append(f"  extra files: {', '.join(report.extra_files[:8])}")
    return "\n".join(lines)


def check_command(args: argparse.Namespace) -> int:
    manifest, source, _ = load_manifest(args)
    validate_manifest(manifest)
    selected = choose_skills(manifest, args.skill)
    reports = [
        evaluate_skill(skill, Path(args.skills_root).expanduser()) for skill in selected
    ]

    if args.json:
        payload = {
            "manifest_source": source,
            "generated_at": utc_now(),
            "summary": summarize_reports(reports),
            "skills": [dataclasses.asdict(report) for report in reports],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Manifest source: {source}")
        for report in reports:
            print(format_report(report))
        print(f"Summary: {summarize_reports(reports)}")

    problem_status = {"outdated", "missing", "modified", "incomplete"}
    has_problem = any(report.status in problem_status for report in reports)
    return 2 if has_problem else 0


def build_skill_patch(
    skill_entry: dict[str, Any],
    local_dir: Path,
    args: argparse.Namespace,
    remote_base_url: str | None,
    manifest_file: Path | None,
    patch_lines: int,
) -> str | None:
    skill_md_entry = None
    for file_entry in skill_entry["files"]:
        if file_entry["path"].endswith("/SKILL.md"):
            skill_md_entry = file_entry
            break
    if skill_md_entry is None:
        return None

    rel = manifest_rel_path(skill_entry, skill_md_entry["path"])
    local_skill_md = local_dir / rel
    if not local_skill_md.exists():
        return "(local SKILL.md missing, patch unavailable)"

    local_text = local_skill_md.read_text(encoding="utf-8").splitlines(keepends=True)
    remote_text = (
        read_remote_file(skill_md_entry, args, remote_base_url, manifest_file)
        .decode("utf-8")
        .splitlines(keepends=True)
    )

    diff_lines = list(
        difflib.unified_diff(
            local_text,
            remote_text,
            fromfile=f"local/{skill_entry['name']}/SKILL.md",
            tofile=f"remote/{skill_entry['name']}/SKILL.md",
            n=2,
        )
    )
    if not diff_lines:
        return "(SKILL.md content is identical)"
    return "".join(diff_lines[:patch_lines])


def diff_command(args: argparse.Namespace) -> int:
    manifest, source, manifest_file = load_manifest(args)
    validate_manifest(manifest)
    selected = choose_skills(manifest, args.skill)
    skills_root = Path(args.skills_root).expanduser()
    remote_base_url = derive_remote_base_url(args, manifest, source)

    print(f"Manifest source: {source}")
    for skill in selected:
        report = evaluate_skill(skill, skills_root)
        print(format_report(report))
        if args.show_patch:
            try:
                patch = build_skill_patch(
                    skill,
                    skills_root / skill["name"],
                    args,
                    remote_base_url,
                    manifest_file,
                    args.patch_lines,
                )
                if patch:
                    print(patch)
            except Exception as exc:
                print(f"  patch error: {exc}")
    return 0


def backup_skill(local_dir: Path, backup_root: Path) -> Path | None:
    if not local_dir.exists():
        return None
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / f"{local_dir.name}-{timestamp}"
    backup_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(local_dir, backup_dir)
    return backup_dir


def download_skill_to_temp(
    skill_entry: dict[str, Any],
    args: argparse.Namespace,
    remote_base_url: str | None,
    manifest_file: Path | None,
    base_dir: Path,
) -> Path:
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f"skill-{skill_entry['name']}-", dir=str(base_dir))
    )
    for file_entry in skill_entry["files"]:
        content = read_remote_file(file_entry, args, remote_base_url, manifest_file)
        expected = file_entry.get("sha256")
        if expected and sha256_bytes(content) != expected:
            raise ValueError(f"SHA-256 mismatch for {file_entry['path']}")

        rel = manifest_rel_path(skill_entry, file_entry["path"])
        out_file = temp_dir / Path(rel)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(content)
    return temp_dir


def write_source_metadata(
    local_dir: Path,
    skill_entry: dict[str, Any],
    source: str,
    args: argparse.Namespace,
) -> None:
    data = {
        "name": skill_entry["name"],
        "version": skill_entry["version"],
        "manifest_source": source,
        "repo": args.repo,
        "ref": args.ref,
        "updated_at": utc_now(),
        "file_count": len(skill_entry["files"]),
    }
    (local_dir / ".skill-source.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_command(args: argparse.Namespace) -> int:
    manifest, source, manifest_file = load_manifest(args)
    validate_manifest(manifest)
    selected = choose_skills(manifest, args.skill)
    skills_root = Path(args.skills_root).expanduser()
    backup_root = Path(args.backup_root).expanduser()
    remote_base_url = derive_remote_base_url(args, manifest, source)

    reports = [evaluate_skill(skill, skills_root) for skill in selected]
    by_name = {report.name: report for report in reports}
    candidates: list[dict[str, Any]] = []
    for skill in selected:
        status = by_name[skill["name"]].status
        if status in {"missing", "outdated", "modified", "incomplete"}:
            candidates.append(skill)

    if not candidates:
        print("No update required.")
        return 0

    print(f"Manifest source: {source}")
    for skill in candidates:
        report = by_name[skill["name"]]
        print(
            f"- plan update {report.name}: status={report.status}, local={report.local_version}, remote={report.remote_version}"
        )

    if not args.apply:
        print("Dry run only. Add --apply to execute update.")
        return 0

    skills_root.mkdir(parents=True, exist_ok=True)
    failures = 0
    for skill in candidates:
        local_dir = skills_root / skill["name"]
        backup_dir = None
        temp_dir = None
        local_removed = False
        try:
            temp_dir = download_skill_to_temp(
                skill, args, remote_base_url, manifest_file, skills_root
            )
            backup_dir = backup_skill(local_dir, backup_root)
            if local_dir.exists():
                shutil.rmtree(local_dir)
                local_removed = True
            shutil.move(str(temp_dir), str(local_dir))
            write_source_metadata(local_dir, skill, source, args)
            print(f"Updated {skill['name']} -> {skill['version']}")
        except Exception as exc:
            failures += 1
            print(f"Failed to update {skill['name']}: {exc}")
            if temp_dir and Path(temp_dir).exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            if local_removed and backup_dir and Path(backup_dir).exists():
                shutil.copytree(backup_dir, local_dir)
                print(f"Restored from backup: {backup_dir}")

    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check, diff, and update local Claude skills from a manifest.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest-file", help="Local manifest file path")
    common.add_argument("--manifest-url", help="Manifest URL")
    common.add_argument("--repo", help="GitHub repo in owner/repo format")
    common.add_argument(
        "--ref", default="main", help="Git reference (branch/tag), default: main"
    )
    common.add_argument(
        "--manifest-path",
        default=DEFAULT_MANIFEST_PATH,
        help=f"Manifest path in repository, default: {DEFAULT_MANIFEST_PATH}",
    )
    common.add_argument(
        "--skills-root",
        default=str(DEFAULT_SKILLS_ROOT),
        help=f"Local skills root, default: {DEFAULT_SKILLS_ROOT}",
    )
    common.add_argument(
        "--skill",
        action="append",
        default=[],
        help="Specify one skill name, repeatable",
    )
    common.add_argument(
        "--timeout", type=int, default=20, help="HTTP timeout in seconds"
    )

    check_parser = subparsers.add_parser(
        "check", parents=[common], help="Check local skill status"
    )
    check_parser.add_argument("--json", action="store_true", help="Output JSON")
    check_parser.set_defaults(func=check_command)

    diff_parser = subparsers.add_parser(
        "diff", parents=[common], help="Summarize local-vs-remote differences"
    )
    diff_parser.add_argument(
        "--show-patch", action="store_true", help="Show unified patch for SKILL.md"
    )
    diff_parser.add_argument(
        "--patch-lines", type=int, default=120, help="Maximum patch lines to print"
    )
    diff_parser.set_defaults(func=diff_command)

    update_parser = subparsers.add_parser(
        "update", parents=[common], help="Update local skills from manifest"
    )
    update_parser.add_argument(
        "--apply", action="store_true", help="Apply update (default is dry-run)"
    )
    update_parser.add_argument(
        "--backup-root",
        default=str(DEFAULT_BACKUP_ROOT),
        help=f"Backup root directory, default: {DEFAULT_BACKUP_ROOT}",
    )
    update_parser.set_defaults(func=update_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
