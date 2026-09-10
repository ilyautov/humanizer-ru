"""The conditional audit route must survive source and ZIP installation."""

from pathlib import Path
import tempfile
import unittest
import zipfile

from install_smoke import REQUIRED_FILES, validate_skill_surface, validate_zip


class AuditSurfaceTests(unittest.TestCase):
    def test_missing_audit_reference_fails_source_and_zip_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skill"
            archive_path = Path(tmp) / "skill.zip"
            root.mkdir()
            with zipfile.ZipFile(archive_path, "w") as archive:
                for name in REQUIRED_FILES:
                    if name == "references/audit.md":
                        continue
                    file = root / name
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text("fixture", encoding="utf-8")
                    archive.writestr("humanizer-ru/" + name, "fixture")
            self.assertTrue(any("references/audit.md" in e for e in validate_skill_surface(root)))
            self.assertTrue(any("references/audit.md" in e for e in validate_zip(archive_path)))


if __name__ == "__main__":
    unittest.main()
