"""Regression tests for evidence retention at the external CLI boundary."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from probe_installed_skill import run_probe
import probe_installed_skill as probe


class ProbeEvidenceTests(unittest.TestCase):
    def test_standalone_primary_and_selected_cases_have_complete_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instruction = root / "instruction.md"
            instruction.write_text("PRIMARY INSTRUCTION", encoding="utf-8")
            cases = root / "cases.json"
            expected = {"selected": {"text": "Исходник.", "source": "synthetic"}}
            cases.write_text(json.dumps(expected), encoding="utf-8")
            out = root / "output"
            argv = ["probe", "--skill-prompt", str(instruction), "--cases-only", str(cases),
                    "--output", str(out), "--repeats", "1"]
            response = {"is_error": False, "subtype": "success", "stop_reason": "end_turn",
                        "result": "Исходник."}
            with patch.object(sys, "argv", argv), patch.object(
                    probe.subprocess, "check_output", return_value="test-cli"), patch.object(
                    probe.subprocess, "run", return_value=subprocess.CompletedProcess(
                        ["claude"], 0, json.dumps(response), "")):
                try:
                    result = probe.main()
                except SystemExit as exc:
                    self.fail(f"standalone selected-case invocation rejected: {exc}")
            self.assertEqual(result, 0)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["inputs"], expected)
            self.assertEqual(manifest["files"], {"SKILL.md": "PRIMARY INSTRUCTION"})
            self.assertEqual(manifest["file_sha256"], {"SKILL.md": probe.digest("PRIMARY INSTRUCTION")})
            self.assertIsNone(manifest["skill_path"])
            self.assertEqual(manifest["skill_prompt_path"], str(instruction.resolve()))
            self.assertEqual(len(manifest["jobs"]), 2)
            packets = list((out / "blind").glob("*.json"))
            self.assertEqual(len(packets), 2)
            for path in packets:
                packet = json.loads(path.read_text())
                self.assertEqual(set(packet), {"id", "case", "source", "output"})
                self.assertEqual(packet["case"], "selected")

    def test_three_arms_have_isolated_instructions_and_same_task(self):
        old = {"SKILL.md": "OFFICIAL INSTRUCTION"}
        candidate = {"SKILL.md": "LOCAL EDIT INSTRUCTION"}
        expected = {"control": "", "skill": "OFFICIAL INSTRUCTION",
                    "candidate": "LOCAL EDIT INSTRUCTION"}
        for arm, marker in expected.items():
            prompt = probe.build_prompt(arm, old, "SOURCE", candidate_files=candidate)
            self.assertTrue(prompt.endswith(probe.TASK + "SOURCE"))
            for value in ("OFFICIAL INSTRUCTION", "LOCAL EDIT INSTRUCTION"):
                self.assertEqual(value in prompt, value == marker)

    def test_unknown_or_unconfigured_arm_is_rejected(self):
        for arm in ("typo", "candidate"):
            with self.assertRaises(ValueError):
                probe.build_prompt(arm, {"SKILL.md": "OLD"}, "SOURCE")

    def test_three_arm_jobs_are_balanced_unique_and_reproducible(self):
        jobs = probe.build_jobs({"one": {}, "two": {}}, 5, 42, True)
        self.assertEqual(jobs, probe.build_jobs({"one": {}, "two": {}}, 5, 42, True))
        self.assertEqual(len(jobs), 30)
        self.assertEqual(len({j["id"] for j in jobs}), 30)
        self.assertEqual({(j["case"], j["arm"], j["repeat"]) for j in jobs},
                         {(c, a, r) for c in ("one", "two")
                          for a in ("control", "skill", "candidate") for r in range(1, 6)})

    def test_comparison_uses_full_old_skill_only_in_control(self):
        old = {"SKILL.md": "OLD", "references/catalog.md": "OLD CATALOG", "edit-log.md": "OLD LOG"}
        new = {"SKILL.md": "NEW", "references/catalog.md": "NEW CATALOG", "edit-log.md": "NEW LOG"}
        control = probe.build_prompt("control", new, "SOURCE", old)
        candidate = probe.build_prompt("skill", new, "SOURCE", old)
        for value in old.values():
            self.assertIn(value, control)
            self.assertNotIn(value, candidate)
        for value in new.values():
            self.assertIn(value, candidate)
            self.assertNotIn(value, control)
        self.assertTrue(control.endswith(probe.TASK + "SOURCE"))
        self.assertTrue(candidate.endswith(probe.TASK + "SOURCE"))

    def test_default_control_still_has_no_skill(self):
        self.assertEqual(probe.build_prompt("control", {"SKILL.md": "NEW"}, "SOURCE"),
                         probe.TASK + "SOURCE")

    def run_case(self, *, response=None, error=None):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "raw").mkdir()
            (out / "blind").mkdir()
            with patch("probe_installed_skill.subprocess.run", return_value=response,
                       side_effect=error):
                run_probe({"id": "test", "case": "case", "arm": "control", "repeat": 1},
                          {}, {"case": {"text": "Исходник."}}, out, "test-model")
            record = json.loads((out / "raw/test.json").read_text())
            return record, (out / "blind/test.json").exists()

    def test_timeout_keeps_partial_evidence(self):
        record, blind = self.run_case(error=subprocess.TimeoutExpired(
            ["claude"], 180, output=b"partial stdout", stderr=b"partial stderr"))
        self.assertFalse(record["ok"])
        self.assertEqual(record["stdout"], "partial stdout")
        self.assertEqual(record["stderr"], "partial stderr")
        self.assertFalse(blind)

    def test_invalid_json_keeps_raw_output_without_blind_packet(self):
        record, blind = self.run_case(response=subprocess.CompletedProcess(
            ["claude"], 0, "not json", "diagnostic"))
        self.assertFalse(record["ok"])
        self.assertEqual(record["stdout"], "not json")
        self.assertFalse(blind)

    def test_incomplete_response_is_not_accepted(self):
        response = {"is_error": False, "subtype": "success", "stop_reason": "max_tokens",
                    "result": "Оборванный"}
        record, blind = self.run_case(response=subprocess.CompletedProcess(
            ["claude"], 0, json.dumps(response), ""))
        self.assertFalse(record["ok"])
        self.assertFalse(blind)

    def test_complete_response_creates_blind_packet(self):
        response = {"is_error": False, "subtype": "success", "stop_reason": "end_turn",
                    "result": "Полный ответ."}
        record, blind = self.run_case(response=subprocess.CompletedProcess(
            ["claude"], 0, json.dumps(response), ""))
        self.assertTrue(record["ok"])
        self.assertTrue(blind)


if __name__ == "__main__":
    unittest.main()
