import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "skills-update-manager"
        / "scripts"
        / "manage_skills.py"
    )
    spec = importlib.util.spec_from_file_location("manage_skills", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module spec from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ManageSkillsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_extract_version_from_frontmatter(self):
        text = """---\nname: demo\nversion: 1.2.3\n---\nbody\n"""
        self.assertEqual(self.mod.extract_version_from_text(text), "1.2.3")

    def test_compare_versions(self):
        self.assertEqual(self.mod.compare_versions("1.0.0", "1.1.0"), -1)
        self.assertEqual(self.mod.compare_versions("2.0.0", "1.1.0"), 1)
        self.assertEqual(self.mod.compare_versions("1.1.0", "1.1.0"), 0)

    def test_evaluate_outdated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_skill = root / "demo-skill"
            local_skill.mkdir()
            (local_skill / "SKILL.md").write_text(
                "---\nname: demo-skill\nversion: 0.9.0\n---\n", encoding="utf-8"
            )

            sha = self.mod.sha256_file(local_skill / "SKILL.md")
            skill_entry = {
                "name": "demo-skill",
                "version": "1.0.0",
                "skill_root": "skills/demo-skill",
                "files": [
                    {
                        "path": "skills/demo-skill/SKILL.md",
                        "sha256": sha,
                    }
                ],
            }
            report = self.mod.evaluate_skill(skill_entry, root)
            self.assertEqual(report.status, "outdated")

    def test_evaluate_modified_by_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_skill = root / "demo-skill"
            local_skill.mkdir(parents=True)
            (local_skill / "SKILL.md").write_text(
                "---\nname: demo-skill\nversion: 1.0.0\n---\nlocal\n", encoding="utf-8"
            )
            skill_entry = {
                "name": "demo-skill",
                "version": "1.0.0",
                "skill_root": "skills/demo-skill",
                "files": [
                    {
                        "path": "skills/demo-skill/SKILL.md",
                        "sha256": "0" * 64,
                    }
                ],
            }
            report = self.mod.evaluate_skill(skill_entry, root)
            self.assertEqual(report.status, "modified")
            self.assertEqual(report.changed_files, ["SKILL.md"])


if __name__ == "__main__":
    unittest.main()
