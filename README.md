# humanizer-ru

> [Русская версия](README.ru.md)

Claude Code / Cowork plugin. Kills AI smell in Russian text.

The English [humanizer](https://github.com/blader/humanizer) won't help you here. Russian AI markers are their own beast: bureaucratic noun-chains (канцелярит), calques from English syntax, missing particles like "же" and "ведь" that make Russian sound alive. None of that overlaps with English patterns.

## What you get

42 patterns across 9 categories, from канцелярит and calques to emotional sterility and suspiciously perfect typography. A list of hard-banned constructions that scream "GPT wrote this." Five article formulas (blog, expert, sales, news, storytelling). Voice calibration if you feed it your writing samples.

## Install

Plugin (recommended):

```
/plugin install humanizer-ru
```

Marketplace:

```
/plugin marketplace add ilyautov/humanizer-ru
/plugin install humanizer-ru@ilyautov-plugins
```

Manual:

```bash
mkdir -p ~/.claude/skills/humanizer-ru
curl -o ~/.claude/skills/humanizer-ru/SKILL.md \
  https://raw.githubusercontent.com/ilyautov/humanizer-ru/main/skills/humanizer-ru/SKILL.md
```

## Modes

**Full rewrite** (default). All 42 patterns, voice calibration, dual-pass audit. For text that needs to sound human.

**Audit**. Diagnosis only — returns a list of detected patterns with priority (A-D). Doesn't touch the text.
```
Проверь этот текст на AI-маркеры: [paste text]
```

**Targeted fix**. Works on a specific category only, leaves the rest alone.
```
Убери канцелярит: [paste text]
```

## Usage

Ask Claude in Russian:

```
Очеловечь этот текст: [paste text]
Перепиши, звучит как робот: [paste text]
```

Triggers: "очеловечь", "убери следы нейросети", "сделай живым", "звучит искусственно", "перепиши как человек".

## Before / After

**Full rewrite:**

> В современном мире искусственный интеллект играет всё более важную роль в различных сферах деятельности. Стоит отметить, что данная технология является мощным инструментом для оптимизации рабочих процессов.

becomes:

> За последний год я внедрил AI-инструменты в три проекта. Два ускорились вдвое. Третий развалился, потому что команда перестала проверять то, что выдаёт модель. AI работает, когда понимаешь его ограничения.

Five hard bans triggered in two sentences. That's typical.

**Audit mode** on the same text would return:

```
[A] Пустое открытие: "В современном мире..."
[A] HARD BAN: "является мощным инструментом"
[A] HARD BAN: "играет важную роль"
[A] HARD BAN: "Стоит отметить, что..."
[B] Канцелярит: "оптимизации рабочих процессов"
[B] Раздувание: "всё более важную роль в различных сферах"
```

## Sources

Patterns drawn from 15+ Russian sources: Habr, vc.ru, Gramota.ru, Wikipedia (WikiProject AI Cleanup), HSE stylometry research, Dialog Conference (RuATD), TechInsider, Kokoc.com.

## License

MIT
