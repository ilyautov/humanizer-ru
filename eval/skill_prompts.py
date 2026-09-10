"""Default rewrite route for offline evals; audit references are conditional."""

from pathlib import Path


def load_edit_prompt(skill: Path) -> str:
    files = {"SKILL.md": (skill / "SKILL.md").read_text(encoding="utf-8")}
    feedback = skill / "edit-log.md"
    if feedback.is_file():
        files["edit-log.md"] = feedback.read_text(encoding="utf-8")
    return "\n\n".join(f"Файл {name}:\n{body}" for name, body in files.items())
