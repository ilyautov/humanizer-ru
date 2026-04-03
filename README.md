# humanizer-ru

> [Русская версия](README.ru.md)

Claude Code / Cowork plugin that removes AI-generation markers from Russian text.

The English [humanizer](https://github.com/blader/humanizer) doesn't work for Russian. AI text markers are fundamentally different across the two languages. Em-dash overuse and copula avoidance mean nothing when the real problems are bureaucratic nominalization (канцелярит), English-to-Russian calques, and missing discourse particles.

## What's inside

37 AI-generation patterns specific to Russian, grouped into 8 categories: content (empty openings, vague authorities, inflated significance), linguistic (канцелярит, English calques, "является" overuse, syntactic monotony), stylistic (em-dash and bold abuse, context-adaptive quote marks), communicative (chatbot artifacts, sycophancy, fluff), morphological (case errors, dangling participles), tonal (emotional sterility, missing particles and irony), structural (disconnected paragraphs, hallucinations), and human touches (perfect grammar and over-polished typography as AI markers).

Plus 5 article formulas: engaging, expert, sales, news, storytelling.

Voice calibration: provide writing samples and the skill adapts to the author's style.

## Install

As a plugin (recommended):

```
/plugin install humanizer-ru
```

Or add the repo as a marketplace source:

```
/plugin marketplace add ilyautov/humanizer-ru
/plugin install humanizer-ru@ilyautov-plugins
```

As a standalone skill:

```bash
mkdir -p ~/.claude/skills/humanizer-ru
curl -o ~/.claude/skills/humanizer-ru/SKILL.md \
  https://raw.githubusercontent.com/ilyautov/humanizer-ru/main/skills/humanizer-ru/SKILL.md
```

## Usage

Just ask Claude in Russian:

```
Очеловечь этот текст: [paste text]
Перепиши, звучит как робот: [paste text]
```

Triggers: "очеловечь", "убери следы нейросети", "сделай живым", "звучит искусственно", "перепиши как человек".

## Example

Before:
> В современном мире искусственный интеллект играет всё более важную роль в различных сферах деятельности. Стоит отметить, что данная технология является мощным инструментом для оптимизации рабочих процессов.

After:
> За последний год я внедрил AI-инструменты в три проекта. Два ускорились вдвое. Третий развалился, потому что команда перестала проверять то, что выдаёт модель. AI работает, когда понимаешь его ограничения.

## Sources

Patterns based on 15+ Russian-language sources: Habr, vc.ru, Gramota.ru, Wikipedia (WikiProject AI Cleanup), HSE stylometry research, Dialog Conference (RuATD), TechInsider, Kokoc.com.

## License

MIT
