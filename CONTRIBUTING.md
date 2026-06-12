# Как контрибьютить в humanizer-ru

Спасибо, что хотите помочь. Самые ценные вклады: новые подтверждённые маркеры
AI-текста, найденные ложные срабатывания и тексты для eval-корпуса.

## Настройка окружения

```bash
git clone https://github.com/ilyautov/humanizer-ru.git
cd humanizer-ru
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Проверки перед PR

```bash
.venv/bin/python scripts/test_markers.py   # регресс-тесты метрик
.venv/bin/python scripts/lint_skill.py     # self-test SKILL.md против собственных правил
```

CI гоняет то же самое на каждый PR.

## Правила проекта

- **Источник правды — `skills/humanizer-ru/SKILL.md`.** Корневой `SKILL.md` —
  его байт-в-байт зеркало: после правки выполните
  `cp skills/humanizer-ru/SKILL.md SKILL.md`. Линт проверяет синхронизацию.
- **Маркер живёт в двух местах.** Новый бан или маркер сканера добавляется
  парой: текст в `SKILL.md` + запись в
  `skills/humanizer-ru/scripts/humanizer_metrics/markers.py` + регресс-тест в
  `scripts/test_markers.py`. Линт сверяет количество категорий.
- **Никаких длинных тире в одобренных примерах.** Бан «—» абсолютный, линт
  ловит нарушения.
- **Новый паттерн — с доказательством.** Пример живого текста, где маркер
  встречается у нейросети и не встречается у человека. Голые ощущения не
  принимаются: проверяйте на ложные срабатывания (формальный регистр,
  осмысленные триады и т.п.).

## Eval (опционально)

Полный прогон требует локальной Ollama с `gemma3:27b` (4b слеп, не используйте):

```bash
OLLAMA_MODEL=gemma3:27b .venv/bin/python eval/run_eval.py \
  --humanized eval/corpus/humanized --detectors --judge --faithfulness
```

Запуск без флагов перезапишет `eval/RESULTS.md` урезанной версией — не надо так.
