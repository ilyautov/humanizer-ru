# humanizer-ru

> [Русская версия: основная](README.md)

Claude Code / Cowork plugin. Kills AI smell in Russian text. The English [humanizer](https://github.com/blader/humanizer) won't help here. Russian AI markers are their own beast: bureaucratic noun-chains (канцелярит), English-syntax calques, missing particles like "же" and "ведь" that make Russian sound alive.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-3.3.0-blueviolet)](https://github.com/ilyautov/humanizer-ru/releases)
[![Stars](https://img.shields.io/github/stars/ilyautov/humanizer-ru?style=social)](https://github.com/ilyautov/humanizer-ru/stargazers)
[![skills.sh](https://skills.sh/b/ilyautov/humanizer-ru)](https://skills.sh/ilyautov/humanizer-ru/humanizer-ru)

## What you get

52 patterns across 12 categories: канцелярит, English calques, emotional sterility, persuasion tricks, information rhythm, hedging specifics, plus the 2025-2026 stylistic fingerprints (jagged-meditation single-word sentences, pseudo-Socratic Q-A chains, decorative emoji per list item, pseudo-therapeutic register). 20 hard-banned constructions that scream "GPT wrote this", including em-dashes (detectors count their frequency). A research-backed section on how detectors actually work (perplexity, burstiness, morphology) with concrete numbers from DivEye, CoPA, PIFE, AINL-Eval 2025. Five article formulas. Voice calibration. Quad-pass audit with a "Skeleton" pass that reads only the first lines of list items to catch templated openings.

## Install

Three deployment channels: upload to Claude.ai web UI, roll out across an organization, or install into local agents (Claude Code, Cowork, API).

### 1. Claude.ai (Web UI)

1. Download the repo as a ZIP:
   `https://github.com/ilyautov/humanizer-ru/archive/refs/heads/main.zip`
2. Open Claude.ai → **Settings** → **Capabilities** → **Skills**.
3. Click **Upload skill** and select the ZIP.

If Claude.ai rejects the archive because of the nested `humanizer-ru-main` folder, clone and re-zip manually:

```bash
git clone https://github.com/ilyautov/humanizer-ru.git
zip -r humanizer-ru.zip humanizer-ru/
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
npx skills add ilyautov/humanizer-ru
```

The CLI drops `SKILL.md` into `~/.claude/skills/humanizer-ru/` and registers the skill on [skills.sh](https://skills.sh/ilyautov/humanizer-ru/humanizer-ru).

**API (`/v1/messages` and equivalents):** pass the skill via the `container.skills` parameter. See your client's docs.

**Manual:**

```bash
mkdir -p ~/.claude/skills/humanizer-ru
curl -o ~/.claude/skills/humanizer-ru/SKILL.md \
  https://raw.githubusercontent.com/ilyautov/humanizer-ru/main/skills/humanizer-ru/SKILL.md
```

Or via git clone:

```bash
git clone https://github.com/ilyautov/humanizer-ru.git ~/.claude/skills/humanizer-ru
```

## Modes

- **Full rewrite** (default): all 52 patterns, voice calibration, quad-pass audit.
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

## Sources

Patterns drawn from 15+ Russian-language sources (Habr, vc.ru, Gramota.ru, HSE stylometry research, Dialog Conference RuATD, TechInsider, Kokoc.com) plus 106 arxiv papers (Biber framework 2024-2025, DivEye 2025, CoPA EMNLP 2025, PIFE 2025, Antislop 2025, MASH 2025, AINL-Eval 2025) and Wikipedia AI Cleanup Project.

Full Russian documentation: [README.md](README.md).

## License

MIT
