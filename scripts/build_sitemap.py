#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Карта сайта: lastmod считается по git, а не правится руками.

Дата, которую правит человек, отстаёт молча. Здесь она отстала на два месяца:
четыре страницы правились 12.09, а карта обещала 07.07, и поисковик читал её
как «с июля ничего не менялось» на самом посещаемом нашем сайте.

    python3 scripts/build_sitemap.py            # записать
    python3 scripts/build_sitemap.py --check    # сверить, ничего не трогая
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = "https://humanizer-ru.aifrontier.tech"
# Частота и приоритет это подсказка обходчику, а не факт из файла, поэтому
# живут здесь. Порядок тот же, что был в карте, собранной руками.
PAGES = [
    ("index.html", "/", "monthly", "1.0"),
    ("ai-detektory-na-russkom.html", "/ai-detektory-na-russkom.html", "monthly", "0.9"),
    ("52-priznaka-ai-teksta.html", "/52-priznaka-ai-teksta.html", "monthly", "0.9"),
    ("kak-ubrat-sledy-neyroseti.html", "/kak-ubrat-sledy-neyroseti.html", "monthly", "0.8"),
    ("antiplagiat-i-neyroset.html", "/antiplagiat-i-neyroset.html", "monthly", "0.7"),
    ("proverit-tekst-na-neyroset.html", "/proverit-tekst-na-neyroset.html", "weekly", "0.9"),
    ("kancelyarit.html", "/kancelyarit.html", "monthly", "0.8"),
    ("gumanizator-teksta.html", "/gumanizator-teksta.html", "monthly", "0.7"),
    # Политику конфиденциальности каталог коннекторов Claude проверяет на
    # доступность, поэтому в карте она обязана быть, пусть и последней.
    ("privacy.html", "/privacy.html", "monthly", "0.3"),
]


def last_commit(rel: str) -> str:
    out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", f"docs/{rel}"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.strip() or "1970-01-01"


def build() -> str:
    missing = [rel for rel, *_ in PAGES if not (DOCS / rel).exists()]
    if missing:
        raise SystemExit(f"в docs нет страниц из списка: {', '.join(missing)}")
    body = "\n".join(
        f"  <url>\n    <loc>{SITE}{url}</loc>\n"
        f"    <lastmod>{last_commit(rel)}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n    <priority>{pri}</priority>\n  </url>"
        for rel, url, freq, pri in PAGES
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    target = DOCS / "sitemap.xml"
    fresh = build()
    if a.check:
        if not target.exists() or target.read_text(encoding="utf-8") != fresh:
            print("карта сайта разошлась с датами коммитов", file=sys.stderr)
            sys.exit(1)
        print("карта сайта совпадает с датами коммитов")
        return
    target.write_text(fresh, encoding="utf-8")
    print(f"записано: docs/sitemap.xml ({len(PAGES)} адресов)")


if __name__ == "__main__":
    main()
