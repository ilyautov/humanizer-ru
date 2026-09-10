"""The offline rewrite runner must receive the same default files as the skill."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class EditPromptTests(unittest.TestCase):
    def test_offline_runner_can_start(self):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("humanize_pass.py")),
                                 "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_offline_runner_passes_feedback_to_generation(self):
        try:
            import humanize_pass as runner
        except ImportError as exc:
            self.fail(f"offline runner cannot import: {exc}")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("CORE", encoding="utf-8")
            (skill / "edit-log.md").write_text("FEEDBACK", encoding="utf-8")
            cell = root / "cell.jsonl"
            cell.write_text(json.dumps({"machine_text": "Исходный текст для проверки."}) + "\n")
            with patch.object(runner, "SKILL", skill / "SKILL.md"), patch.object(
                    runner, "OUT", root), patch.object(runner.remote_backend, "parse_target",
                    return_value=(None, "test")), patch.object(runner, "generate",
                    return_value="Это проверочный русский текст без обращения к внешней модели.") as generate:
                self.assertEqual(runner.run(cell, "test", 1, 4096), 1)
            self.assertIn("CORE", generate.call_args.args[0])
            self.assertIn("FEEDBACK", generate.call_args.args[0])

    def loader(self):
        spec = importlib.util.find_spec("skill_prompts")
        self.assertIsNotNone(spec, "shared default-route prompt loader is missing")
        import skill_prompts
        return skill_prompts.load_edit_prompt

    def test_default_route_contains_full_skill_and_feedback_not_catalog(self):
        load = self.loader()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "references").mkdir()
            (root / "SKILL.md").write_text("CORE", encoding="utf-8")
            (root / "edit-log.md").write_text("FEEDBACK", encoding="utf-8")
            (root / "references/catalog.md").write_text("LEGACY CATALOG", encoding="utf-8")
            (root / "references/audit.md").write_text("AUDIT ONLY", encoding="utf-8")
            prompt = load(root)
            self.assertEqual(prompt, "Файл SKILL.md:\nCORE\n\nФайл edit-log.md:\nFEEDBACK")

    def test_feedback_is_optional_but_main_is_required(self):
        load = self.loader()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                load(root)
            (root / "SKILL.md").write_text("CORE", encoding="utf-8")
            self.assertEqual(load(root), "Файл SKILL.md:\nCORE")


if __name__ == "__main__":
    unittest.main()
