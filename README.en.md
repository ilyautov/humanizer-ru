# humanizer-ru

> [Русская версия: основная](README.md)

Claude Code / Cowork plugin. Kills AI smell in Russian text. The English [humanizer](https://github.com/blader/humanizer) won't help here. Russian AI markers are their own beast: bureaucratic noun-chains (канцелярит), English-syntax calques, missing particles like "же" and "ведь" that make Russian sound alive.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-3.16.0-blueviolet)](https://github.com/ilyautov/humanizer-ru/blob/main/CHANGELOG.md)
[![Stars](https://img.shields.io/github/stars/ilyautov/humanizer-ru?style=social)](https://github.com/ilyautov/humanizer-ru/stargazers)
[![skills.sh](https://skills.sh/b/ilyautov/humanizer-ru)](https://skills.sh/ilyautov/humanizer-ru/humanizer-ru)

<p align="center">
  <a href="https://humanizer-ru.aifrontier.tech/">
    <img src="assets/social-preview.png" alt="humanizer-ru: removes AI tells from Russian text. 58 patterns, 20 hard bans, scanner included" width="720">
  </a>
</p>

📖 **Docs & write-ups (RU):** [humanizer-ru.aifrontier.tech](https://humanizer-ru.aifrontier.tech/): do AI detectors work on Russian, the 58 markers, plagiarism vs AI detection.

## What you get

58 patterns across 13 categories: канцелярит, English calques, emotional sterility, persuasion tricks, information rhythm, hedging specifics, plus the 2025-2026 stylistic fingerprints (jagged-meditation single-word sentences, pseudo-Socratic Q-A chains, decorative emoji per list item, pseudo-therapeutic register) and the 2026 formulas (inanimate subject, Title Case headings, mid-sentence truncation, negation triad). 20 hard-banned constructions that scream "GPT wrote this", including em-dashes (detectors count their frequency). A research-backed section on how detectors actually work (perplexity, burstiness, morphology) with verified numbers from DivEye, PIFE, AINL-Eval 2025 (every citation checked, see SOURCES.md). Five article formulas. Voice calibration. Quad-pass audit with a "Skeleton" pass that reads only the first lines of list items to catch templated openings.

## Install

Three deployment channels: upload to Claude.ai web UI, roll out across an organization, or install into local agents (Claude Code, Cowork, API).

### 1. Claude.ai (Web UI)

1. Download the packaged skill:
   [humanizer-ru.zip](https://github.com/ilyautov/humanizer-ru/releases/latest/download/humanizer-ru.zip)
2. Open Claude.ai → **Settings** → **Capabilities** → **Skills**.
3. Click **Upload skill** and select the ZIP.

Do not use `archive/refs/heads/main.zip`: the uploader expects `SKILL.md` at the top level of the archive, and in the repo archive it sits inside `humanizer-ru-main/skills/humanizer-ru/`. To build the archive yourself, zip the skill folder itself:

```bash
git clone https://github.com/ilyautov/humanizer-ru.git
cd humanizer-ru/skills
zip -r ../../humanizer-ru.zip humanizer-ru -x '*/__pycache__/*'
```

### 2. Organizations (Enterprise & Team)

Workspace admins can roll the skill out to the whole team via **Admin Console → Workspace Skills → Add skill**. Upload the same ZIP, no per-user installation needed.

### 3. Claude Code, Cowork, API (local agents)

**Plugin marketplace** (recommended):

```
/plugin marketplace add ilyautov/humanizer-ru
/plugin install humanizer-ru@ilyautov-plugins
```

**skills.sh CLI** (universal across Claude agents):

```bash
npx skills add https://github.com/ilyautov/humanizer-ru/tree/main/skills/humanizer-ru
```

The CLI drops `SKILL.md` into `~/.claude/skills/humanizer-ru/` and registers the skill on [skills.sh](https://skills.sh/ilyautov/humanizer-ru/humanizer-ru). Point at the full skill-folder path: the short `ilyautov/humanizer-ru` form resolves to the repo root, which has no `SKILL.md` (removed in v3.14.2), so the install either fails or pulls in the whole repository.

**API (`/v1/messages` and equivalents):** pass the skill via the `container.skills` parameter. See your client's docs.

**Manual:**

```bash
git clone --depth 1 https://github.com/ilyautov/humanizer-ru /tmp/humanizer-ru
mkdir -p ~/.claude/skills
cp -r /tmp/humanizer-ru/skills/humanizer-ru ~/.claude/skills/
```

Copy the whole folder, not just SKILL.md: the skill ships with a deterministic
scanner, `scripts/scan.py` (the machine half of Audit mode; needs
`pip install razdel pymorphy3`, and the skill gracefully falls back to a manual
audit without them).

### 4. Codex CLI (OpenAI)

Codex uses the same Agent Skills format, so no separate build is needed:

```bash
git clone --depth 1 https://github.com/ilyautov/humanizer-ru
mkdir -p ~/.codex/skills
cp -r humanizer-ru/skills/humanizer-ru ~/.codex/skills/
```

Or from inside Codex via `skill-installer` with the path
`ilyautov/humanizer-ru/skills/humanizer-ru`. Restart Codex after installing;
invoke with `$humanizer-ru` or let it auto-trigger. For a per-project install,
put the same folder under `.codex/skills/` in your repository.

### 5. Other agents (shared SKILL.md standard)

The Agent Skills format is now cross-platform, so humanizer-ru runs beyond the four packaged stacks above. Officially packaged and verified: Claude Code, Codex CLI, Cursor, Gemini CLI. Other agents read the same `SKILL.md`, no separate build needed.

| How it connects | Agents | What to do |
|---|---|---|
| Read `SKILL.md` natively | GitHub Copilot, Cline, Roo Code, Kilo Code, Goose, OpenCode, OpenWork, Kimi Code CLI, OpenClaw, OpenHuman, Hermes | Copy the `skills/humanizer-ru` folder into the agent's skills dir (e.g. `~/.hermes/skills/`, `~/.kimi/skills/`, `.agents/skills/`) |
| Installer conversion | Windsurf, Trae, Junie | Install via their skill installer, pointing at `ilyautov/humanizer-ru` |
| Manual paste | Zed, Aider, Continue.dev | Paste the `SKILL.md` body into the agent's rules or instructions file |

Generic path for native readers: drop the skill folder into the directory the agent scans (usually `<project root>/.agents/skills/` or `~/.config/agents/skills/`) and restart it. Same activation triggers.

> Several of these agents (OpenClaw, Kimi, Hermes) have public skill registries (ClawHub and similar). Listing there adds reach with no extra code: the format is shared.

## Modes

- **Full rewrite** (default): all 58 patterns, voice calibration, quad-pass audit.
- **Audit**: diagnosis only, returns detected patterns with priority A-D.
- **Targeted fix**: works on a specific category only.

## Usage

Ask Claude in Russian:

```
Очеловечь этот текст: [paste text]
Перепиши, звучит как робот: [paste text]
```

Triggers: "очеловечь", "убери следы нейросети", "сделай живым", "звучит искусственно", "перепиши как человек".

## Before / After

Before:
> В современном мире искусственный интеллект играет всё более важную роль в различных сферах деятельности. Стоит отметить, что данная технология является мощным инструментом для оптимизации рабочих процессов.

After:
> За последний год я внедрил AI-инструменты в три проекта. Два ускорились вдвое. Третий развалился, потому что команда перестала проверять то, что выдаёт модель. AI работает, когда понимаешь его ограничения.

Five hard bans triggered in two sentences. Typical.

## Do AI detectors work on Russian?

Short answer: poorly, and it matters.

GPTZero, Originality.ai, ZeroGPT and most popular AI-text detectors are trained mostly on English. On Russian they are unreliable and fail both ways:

- **False positives:** text written by a real human routinely gets flagged as "AI-generated". English perplexity thresholds aren't calibrated for Russian, and Russian's rich morphology inflates "unpredictability" on its own.
- **False negatives:** careful AI text passes as human.

Even the best Russian-specific detector (RuRoBERTa on the AINL-Eval 2025 benchmark) lands around 86% accuracy, and one verdict in seven is wrong. And detectors don't generalize across domains (verified, see [SOURCES.md](SOURCES.md)).

**What this means for humanizing.** Chasing "detector bypass" on Russian means tuning text to an unreliable, moving target. So humanizer-ru optimizes genuine text quality (removing bureaucratic noun-chains, calques and clichés, restoring author voice and live rhythm) rather than gaming a classifier. Those are measurable language properties (see [`eval/`](eval/)) independent of how bad any given detector is. Perplexity and burstiness rise as a side effect, which is what detectors try (and often fail) to measure. We run detectors against real human Russian texts in the harness and publish the false-positive rate: [eval/RESULTS.md](eval/RESULTS.md).

## Sources

Patterns drawn from 15+ Russian-language sources (Habr, vc.ru, Gramota.ru, HSE stylometry research, Dialog Conference RuATD, TechInsider, Kokoc.com), verified academic papers (DivEye, PIFE, MASH, Antislop, AINL-Eval, RuATD, NeurIPS 2025), and the Wikipedia AI Cleanup Project. Every citation and figure is checked against primary sources; unverified ones were removed. Full provenance: [SOURCES.md](SOURCES.md).

Changelog: [CHANGELOG.md](CHANGELOG.md). Metrics and eval harness: [`scripts/`](scripts/) and [`eval/`](eval/). Full Russian documentation: [README.md](README.md).

## Author

Ilya Utov. I write about AI and working with text on Telegram: [Under the Hood](https://t.me/gorilla_under_hood).

## License

MIT
