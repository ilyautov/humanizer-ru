#!/usr/bin/env python3
"""Сверка живых каталогов с репозиторием: что реально видит пользователь.

Версия бампается в 17 файлах репо, но пользователь ставит скилл не из репо, а
из npm, из GitHub Release, с сайта и из карточки skills.sh. Эти поверхности
живут своей жизнью: npm публикует CI по тегу и может упасть, Pages деплоится с задержкой,
сторонние индексаторы кэшируют SKILL.md. Скрипт спрашивает каждую поверхность
и сравнивает с версией в `.claude-plugin/plugin.json`.

Статусы: OK, DRIFT (расходится), UNAVAILABLE (сеть или сервис не ответили,
это не вердикт). Поверхности двух типов:
- жёсткие (npm, PyPI, реестр MCP, Release, ZIP, сайт, правила сканера на
  сайте): DRIFT валит прогон, потому что чинится нашими руками;
- мягкие (skills.sh, ClawHub, HOL): DRIFT только предупреждение, кэш
  индексатора или ручная публикация нам не подчиняются, но знать о них надо.

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
import time
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
PYPI_JSON = "https://pypi.org/pypi/ru-humanizer/json"
MCP_NAME = "io.github.ilyautov/humanizer-ru"
# Поиск по подстроке отдаёт и чужие карточки с тем же именем пакета, поэтому
# в ответе берётся только запись с точным namespace и пометкой isLatest.
MCP_REGISTRY = "https://registry.modelcontextprotocol.io/v0.1/servers?search=ilyautov&limit=100"
CLAWHUB_PAGE = "https://clawhub.ai/ilyautov/humanizer-ru"
HOL_BADGE = ("https://hol.org/api/registry/badges/plugin"
             "?slug=ilya-utov%2Fhumanizer-ru&metric=status&style=flat")
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


def fetch(url: str, *, head: bool = False, timeout: int = TIMEOUT) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="HEAD" if head else "GET")
    req.add_header("User-Agent", "humanizer-ru-live-check")
    if "api.github.com" in url and os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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


def parse_pypi_version(body: bytes) -> str:
    return str(json.loads(body).get("info", {}).get("version", ""))


def parse_mcp_registry_version(body: bytes, name: str = MCP_NAME) -> str:
    """Версия нашей карточки, помеченной isLatest. Чужие карточки пропускаются."""
    for entry in json.loads(body).get("servers", []):
        if entry.get("server", {}).get("name") != name:
            continue
        official = entry.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
        if official.get("isLatest"):
            return str(entry["server"].get("version", ""))
    return ""


def check_npm(version: str) -> Check:
    try:
        _, body = fetch(NPM_LATEST)
        return compare("npm humanizer-ru", version, json.loads(body)["version"], hard=True,
                       note="публикует publish-npm.yml по тегу v*, смотрите его запуск")
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


def check_pypi(version: str) -> Check:
    try:
        _, body = fetch(PYPI_JSON)
        return compare("PyPI ru-humanizer", version, parse_pypi_version(body), hard=True,
                       note="публикует publish-pypi.yml по релизу, смотрите его запуск")
    except Exception as e:  # noqa: BLE001
        return unavailable("PyPI ru-humanizer", version, True, e)


def fetch_with_retry(url: str, attempts: int = 3, timeout: int = 60) -> tuple[int, bytes]:
    """Реестр MCP отвечает то за 20 секунд, то 500: три попытки до вердикта."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fetch(url, timeout=timeout)
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500 and e.code != 429:
                break  # 4xx повтором не лечится, кроме 429 (лимит)
            if i + 1 < attempts:
                time.sleep(3)
        except Exception as e:  # noqa: BLE001
            last = e
            if i + 1 < attempts:
                time.sleep(3)
    assert last is not None
    raise last


def check_mcp_registry(version: str) -> Check:
    try:
        _, body = fetch_with_retry(MCP_REGISTRY)
        return compare(f"реестр MCP {MCP_NAME}", version, parse_mcp_registry_version(body),
                       hard=True, note="публикует publish-registry.yml после PyPI")
    except Exception as e:  # noqa: BLE001
        return unavailable(f"реестр MCP {MCP_NAME}", version, True, e)


def check_clawhub() -> Check:
    # У страницы нет стабильного API версии, поэтому проверяется только то,
    # что карточка существует. Версию сверяет запуск clawhub.yml.
    try:
        status, _ = fetch(CLAWHUB_PAGE, head=True)
        return compare("ClawHub, карточка", "200", str(status), hard=False,
                       note="публикуется через clawhub.yml по релизу или вручную")
    except urllib.error.HTTPError as e:
        return Check("ClawHub, карточка", "DRIFT", "200", str(e.code), False,
                     "карточки нет, запустите clawhub.yml")
    except Exception as e:  # noqa: BLE001
        return unavailable("ClawHub, карточка", "200", False, e)


def check_hol() -> Check:
    try:
        _, body = fetch(HOL_BADGE)
        slug = str(json.loads(body).get("message", ""))
        return compare("HOL, запись плагина", "ilya-utov/humanizer-ru", slug, hard=False,
                       note="реестр hol.org не отдаёт нашу запись")
    except Exception as e:  # noqa: BLE001
        return unavailable("HOL, запись плагина", "ilya-utov/humanizer-ru", False, e)


def run() -> list[Check]:
    v = local_version()
    return [check_npm(v), check_pypi(v), check_mcp_registry(v), check_release(v), check_zip(),
            check_site(v), check_site_rules(), check_skills_sh(v), check_clawhub(), check_hol()]


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
