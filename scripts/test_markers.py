#!/usr/bin/env python3
"""Регресс-тесты метрик. Без pytest: чистые assert, запуск `python scripts/test_markers.py`.

Фиксируют классы ошибок, которые уже случались, чтобы не вернулись:
- «данные/данных» (data) НЕ должны ловиться как канцелярит «данный» (был ложный
  бан на ML/статистических текстах);
- «данный метод» (определитель) ДОЛЖЕН ловиться;
- длинное тире считается, дефис — нет;
- AI-текст и человеческий текст уверенно разделяются по метрикам.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from humanizer_metrics import analyze
from humanizer_metrics.markers import scan_hard_bans, scan_markers

passed = 0


def check(cond: bool, msg: str) -> None:
    global passed
    assert cond, f"FAIL: {msg}"
    passed += 1


def ban_names(text: str) -> set[str]:
    return {h.marker for h in scan_hard_bans(text)}


# --- «данные» (data) не канцелярит ---------------------------------------
check("Данный/Данная/Данное" not in ban_names("Модель учится на размеченных данных."),
      "«данных» (data) не должно быть HARD BAN")
check("Данный/Данная/Данное" not in ban_names("Качество данных важнее архитектуры."),
      "«данных» (data, род.) не должно быть HARD BAN")
check("Данный/Данная/Данное" in ban_names("Данный метод хорош."),
      "«данный» (определитель) должен ловиться")
check("Данный/Данная/Данное" in ban_names("В данной ситуации это работает."),
      "«данной» (определитель) должен ловиться")

# --- тире -----------------------------------------------------------------
check("Длинное тире" in ban_names("Это длинное тире — маркер."), "длинное тире ловится")
check("Длинное тире" not in ban_names("Это дефис-маркер, всё ок."), "дефис не ловится как тире")
check(analyze("Текст — с тире.").rhythm.em_dash == 1, "em_dash считается")
check(analyze("Текст с дефисом-словом.").rhythm.em_dash == 0, "дефис не считается em_dash")

# --- базовые HARD BANS ----------------------------------------------------
check("В современном мире" in ban_names("В современном мире всё иначе."), "пустое открытие")
check("Является" in ban_names("Python является языком."), "«является» ловится")
check(len(scan_markers("осуществление реализация внедрение")) >= 1, "канцелярит-маркеры ловятся")

# --- разделение AI vs человек по метрикам --------------------------------
ai = analyze("В современном мире технология является инструментом. "
             "Стоит отметить, что данный подход открывает новые горизонты.")
human = analyze("Я попробовал три раза. Не вышло. Потом понял, в чём дело: забыл про кэш.")
check(ai.hard_ban_count > human.hard_ban_count, "у AI больше HARD BANS, чем у человека")
check(human.rhythm.cv_len > ai.rhythm.cv_len, "у человека ритм рванее (CV выше)")


if __name__ == "__main__":
    print(f"OK — {passed} проверок прошли.")
