#!/usr/bin/env python3
"""Пересборка assets/social-preview.png из актуальных счётчиков.

Раньше это был единственный ручной пункт релиза, который никто не выполнял:
счётчик внутри растра отстал на два релиза (52 при каталоге 58), а alt-текст
рядом уже говорил правду. Теперь картинка собирается из тех же источников, что
и остальные счётчики: число паттернов из каталога, число банов из markers.py.

Палитра и геометрия повторяют docs/style.css и прежний макет.

Запуск:
    python scripts/make_social_preview.py            # перерисовать
    python scripts/make_social_preview.py --check    # гейт: счётчик в файле свежий

Нужен Pillow (`pip install pillow`) и системный моноширинный шрифт с кириллицей
(на macOS Menlo, на Linux DejaVu Sans Mono).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

OUT = ROOT / "assets" / "social-preview.png"
# Сайт отдаёт свою копию по og:image, она обязана совпадать.
OUT_SITE = ROOT / "docs" / "social-preview.png"
CATALOG = ROOT / "skills" / "humanizer-ru" / "references" / "catalog.md"
STAMP = ROOT / "assets" / ".social-preview-counters"

# Палитра docs/style.css.
BG = (10, 13, 19)
BG_SOFT = (16, 21, 29)
BORDER = (35, 45, 60)
TEXT = (221, 229, 239)
TEXT_DIM = (148, 162, 180)
ACCENT = (122, 167, 255)
CTA = (255, 138, 61)
GOOD = (74, 222, 128)
BAD = (248, 113, 113)

FONT_CANDIDATES = (
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
)


def counters() -> tuple[int, int]:
    """Источники истины те же, что у bump_release.py."""
    from humanizer_metrics.markers import HARD_BANS

    text = CATALOG.read_text(encoding="utf-8")
    found: set[int] = set()
    # Заголовки паттернов бывают одиночные («**6.**») и диапазоном («**17-18.**»),
    # как в scripts/lint_skill.py.
    for m in re.finditer(r"^\*\*(\d{1,2})(?:-(\d{1,2}))?\.", text, re.MULTILINE):
        start = int(m.group(1))
        found.update(range(start, int(m.group(2) or start) + 1))
    patterns = max(n for n in range(1, 100) if all(k in found for k in range(1, n + 1)))
    return patterns, len(HARD_BANS)


def _font(path: str, size: int, bold: bool = False):
    from PIL import ImageFont

    try:  # у .ttc начертания лежат индексами: 0 обычное, 1 жирное
        return ImageFont.truetype(path, size, index=1 if bold and path.endswith(".ttc") else 0)
    except OSError:
        return ImageFont.truetype(path, size)


def draw(patterns: int, bans: int) -> None:
    from PIL import Image, ImageDraw

    font_path = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
    if font_path is None:
        raise SystemExit("[ошибка] не найден моноширинный шрифт с кириллицей")

    im = Image.new("RGB", (1280, 640), BG)
    d = ImageDraw.Draw(im)

    title = _font(font_path, 92, bold=True)
    sub = _font(font_path, 34)
    chip = _font(font_path, 24)
    diff = _font(font_path, 28)
    foot = _font(font_path, 22)

    # Заголовок: «humanizer», дефис, «ru» акцентом, следом квадрат-курсор.
    # Дефис рисуем сами: у Menlo в жирном начертании он длинный и читается как
    # тире, а тире у нас под запретом даже в собственном логотипе.
    x = 80
    d.text((x, 140), "humanizer", font=title, fill=TEXT)
    x += int(d.textlength("humanizer", font=title))
    dash_w = int(d.textlength("-", font=title))
    d.rounded_rectangle((x + dash_w * 0.28, 196, x + dash_w * 0.72, 204), radius=4, fill=TEXT)
    x += dash_w
    d.text((x, 140), "ru", font=title, fill=ACCENT)
    x += int(d.textlength("ru", font=title)) + 26
    d.rounded_rectangle((x, 165, x + 40, 220), radius=8, fill=CTA)

    d.text((80, 272), "Убирает следы нейросети из русского текста", font=sub, fill=TEXT_DIM)

    chips = [
        (f"{patterns} признаков", ACCENT),
        (f"{bans} запретов", TEXT_DIM),
        ("сканер в комплекте", TEXT_DIM),
        ("MIT", TEXT_DIM),
    ]
    x = 80
    for label, color in chips:
        w = int(d.textlength(label, font=chip)) + 40
        d.rounded_rectangle((x, 356, x + w, 410), radius=27, fill=BG_SOFT, outline=BORDER, width=2)
        d.text((x + 20, 370), label, font=chip, fill=color)
        x += w + 17

    d.text((80, 482), "- данный подход является эффективным", font=diff, fill=BAD)
    d.text((80, 525), "+ этот подход реально ускоряет работу", font=diff, fill=GOOD)

    footer = "Claude Code · Codex CLI · Cursor · Gemini CLI"
    d.text((1200 - int(d.textlength(footer, font=foot)), 578), footer, font=foot, fill=TEXT_DIM)

    im.save(OUT)
    im.save(OUT_SITE)
    STAMP.write_text(f"{patterns}/{bans}\n", encoding="utf-8")
    print(f"[ok] {OUT.relative_to(ROOT)} и {OUT_SITE.relative_to(ROOT)}: "
          f"{patterns} признаков, {bans} запретов")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="только проверить, что растр собран на текущих счётчиках")
    args = ap.parse_args()

    patterns, bans = counters()
    if args.check:
        want = f"{patterns}/{bans}"
        have = STAMP.read_text(encoding="utf-8").strip() if STAMP.exists() else "(нет отметки)"
        if have != want:
            print(f"[гейт] social-preview.png собран на {have}, а в каталоге {want}.\n"
                  "       Перерисуйте: python scripts/make_social_preview.py")
            return 1
        print(f"[гейт] ✓ social-preview.png собран на актуальных счётчиках ({want})")
        return 0

    draw(patterns, bans)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
