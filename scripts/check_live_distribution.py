#!/usr/bin/env python3
"""Сверка живых каталогов с репозиторием: что реально видит пользователь.

Версия бампается в 17 файлах репо, но пользователь ставит скилл не из репо, а
из npm, из GitHub Release, с сайта и из карточки skills.sh. Эти поверхности
живут своей жизнью: npm publish делается руками, Pages деплоится с задержкой,
сторонние индексаторы кэшируют SKILL.md. Скрипт спрашивает каждую поверхность
и сравнивает с версией в `.claude-plugin/plugin.json`.

Статусы: OK, DRIFT (расходится), UNAVAILABLE (сеть или сервис не ответили,
это не вердикт). Поверхности двух типов:
- жёсткие (npm, Release, ZIP, сайт, правила сканера на сайте): DRIFT валит
  прогон, потому что чинится нашими руками;
- мягкие (skills.sh): DRIFT только предупреждение, кэш индексатора нам не
  подчиняется, но знать о нём надо.

Коды выхода: 0 всё сошлось, 1 есть жёсткий DRIFT, 2 только UNAVAILABLE.

  python scripts/check_live_distribution.py           # отчёт в консоль
  python scripts/check_live_distribution.py --json    # машинный конверт
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "ilyautov/humanizer-ru"
SITE = "https://humanizer-ru.aifrontier.tech"
NPM_LATEST = "https://registry.npmjs.org/humanizer-ru/latest"
RELEASE_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ZIP_LATEST = f"https://github.com/{REPO}/releases/latest/download/humanizer-ru.zip"
SKILLS_SH = "https://www.skills.sh/ilyautov/humanizer-ru/humanizer-ru"
TIMEOUT = 20

RE_SITE_VERSION = re.compile(r"<li>v(\d+\.\d+)</li>")
# Карточка skills.sh рендерит наш SKILL.md, заголовок в ней экранирован как <.
RE_SKILLS_SH_VERSION = re.compile(r"Humanizer-RU v(\d+\.\d+\.\d+)")


@dataclass
class Check:
    surface: str
    status: str  # OK | DRIFT | UNAVAILABLE
    expected: str
    actual: str
    hard: bool
    note: str = ""


def local_version() -> str:
    data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return data["version"]


def fetch(url: str, *, head: bool = False) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="HEAD" if head else "GET")
    req.add_header("User-Agent", "humanizer-ru-live-check")
    if "api.github.com" in url and os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status, b"" if head else resp.read()


def unavailable(surface: str, expected: str, hard: bool, err: Exception) -> Check:
    return Check(surface, "UNAVAILABLE", expected, "", hard, f"{type(err).__name__}: {err}")


def compare(surface: str, expected: str, actual: str, hard: bool, note: str = "") -> Check:
    return Check(surface, "OK" if actual == expected else "DRIFT", expected, actual, hard, note)


# --- Разбор ответов вынесен в чистые функции: их проверяет test_gates -----

def parse_site_version(html: str) -> str:
    m = RE_SITE_VERSION.search(html)
    return m.group(1) if m else ""


def parse_skills_sh_version(html: str) -> str:
    m = RE_SKILLS_SH_VERSION.search(html)
    return m.group(1) if m else ""


def check_npm(version: str) -> Check:
    try:
        _, body = fetch(NPM_LATEST)
        return compare("npm humanizer-ru", version, json.loads(body)["version"], hard=True,
                       note="публикуется руками из терминала: npm publish")
    except Exception as e:  # noqa: BLE001
        return unavailable("npm humanizer-ru", version, True, e)


def check_release(version: str) -> Check:
    try:
        _, body = fetch(RELEASE_LATEST)
        data = json.loads(body)
        tag = str(data.get("tag_name", "")).lstrip("v")
        assets = [a["name"] for a in data.get("assets", [])]
        note = "" if "humanizer-ru.zip" in assets else "в Release нет ассета humanizer-ru.zip"
        c = compare("GitHub Release latest", version, tag, hard=True, note=note)
        if c.status == "OK" and note:
            c.status = "DRIFT"
        return c
    except Exception as e:  # noqa: BLE001
        return unavailable("GitHub Release latest", version, True, e)


def check_zip() -> Check:
    try:
        status, _ = fetch(ZIP_LATEST, head=True)
        return compare("ZIP releases/latest/download", "200", str(status), hard=True)
    except urllib.error.HTTPError as e:
        return Check("ZIP releases/latest/download", "DRIFT", "200", str(e.code), True, "ссылка из README не отдаёт архив")
    except Exception as e:  # noqa: BLE001
        return unavailable("ZIP releases/latest/download", "200", True, e)


def check_site(version: str) -> Check:
    short = ".".join(version.split(".")[:2])
    try:
        _, body = fetch(f"{SITE}/")
        return compare("сайт, версия в подвале", short, parse_site_version(body.decode("utf-8", "replace")),
                       hard=True, note="Pages деплоится с main, задержка до нескольких минут")
    except Exception as e:  # noqa: BLE001
        return unavailable("сайт, версия в подвале", short, True, e)


def check_site_rules() -> Check:
    local = (ROOT / "docs" / "scan-rules.js").read_bytes()
    try:
        _, body = fetch(f"{SITE}/scan-rules.js")
        same = body == local
        return Check("сайт, правила сканера", "OK" if same else "DRIFT", "как в docs/scan-rules.js",
                     "совпадает" if same else f"{len(body)} байт против {len(local)} локально", True,
                     "" if same else "онлайн-аудит считает по другим правилам, чем скилл")
    except Exception as e:  # noqa: BLE001
        return unavailable("сайт, правила сканера", "как в docs/scan-rules.js", True, e)


def check_skills_sh(version: str) -> Check:
    try:
        _, body = fetch(SKILLS_SH)
        return compare("skills.sh, карточка", version, parse_skills_sh_version(body.decode("utf-8", "replace")),
                       hard=False, note="кэш индексатора, обновляется на их стороне")
    except Exception as e:  # noqa: BLE001
        return unavailable("skills.sh, карточка", version, False, e)


def run() -> list[Check]:
    v = local_version()
    return [check_npm(v), check_release(v), check_zip(), check_site(v), check_site_rules(), check_skills_sh(v)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    args = ap.parse_args()
    checks = run()
    hard_drift = [c for c in checks if c.status == "DRIFT" and c.hard]
    soft_drift = [c for c in checks if c.status == "DRIFT" and not c.hard]
    unavail = [c for c in checks if c.status == "UNAVAILABLE"]
    code = 1 if hard_drift else (2 if unavail else 0)

    if args.json:
        print(json.dumps({"local_version": local_version(), "exit_code": code,
                          "checks": [asdict(c) for c in checks]}, ensure_ascii=False, indent=1))
        return code

    print(f"=== check_live_distribution: локально v{local_version()} ===")
    for c in checks:
        mark = {"OK": "✓", "DRIFT": "!" if not c.hard else "✗", "UNAVAILABLE": "?"}[c.status]
        actual = c.actual or "нет ответа"
        line = f"  {mark} {c.surface}: {actual}"
        if c.status != "OK":
            line += f" (ждали {c.expected})"
        if c.note and c.status != "OK":
            line += f". {c.note}"
        print(line)
    if hard_drift:
        print(f"✗ расходятся {len(hard_drift)} поверхностей, пользователь получает не то, что в репо")
    elif unavail:
        print(f"? {len(unavail)} поверхностей не ответили, вердикта нет")
    else:
        print("OK — все поверхности отдают текущую версию" + (
            f"; мягкое отставание: {', '.join(c.surface for c in soft_drift)}" if soft_drift else ""))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
